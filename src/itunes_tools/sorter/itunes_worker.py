"""iTunes work done outside the UI thread, so the window stays responsive while iTunes is busy.

``ItunesWorker`` lives in its own ``QThread``. The window talks to it only through signals: a signal
connected to a slot of an object living in another thread is delivered through that thread's event loop
(a *queued connection*), so the slot runs in the worker thread. Calling a worker slot directly would
run it in the caller's thread instead, blocking the UI.
"""

from PySide6.QtCore import QObject, Signal, Slot

from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.common.exceptions import ItunesClientError
from itunes_tools.common.itunes_client import ItunesClient
from itunes_tools.common.logger import get_logger
from itunes_tools.common.models import ItunesPersistentID, Playlist

logger = get_logger(__name__)


def capture_playlist(client: ItunesClient, playlist_id: ItunesPersistentID, artwork_cache: ArtworkCache) -> Playlist:
    """Read a playlist with all its song metadata from iTunes and cache the songs' artwork.

    After this, the sorter can show and sort the playlist without iTunes.

    :raises ItunesClientError: if reading the playlist or exporting artwork fails.
    """
    playlist = client.get_playlist_by_id(playlist_id)
    artwork_cache.fill(playlist.tracks, client)
    return playlist


class ItunesWorker(QObject):
    """Runs iTunes jobs in the thread it was moved to.

    Every job ends with exactly one result signal (``playlistsListed``, ``playlistImported`` or
    ``playlistCommitted``) or ``failed``, so the window knows when it may start the next job.

    The ``ItunesClient`` is created on the first job, inside the worker thread, because a client is
    bound to the thread that first uses it.
    """

    playlistsListed = Signal(list)  # list[str], playlist names sorted for display
    playlistImported = Signal(object)  # Playlist
    playlistCommitted = Signal(object)  # Playlist, the new playlist read back from iTunes
    progress = Signal(str)  # a message for the user
    failed = Signal(str)  # a message for the user

    def __init__(self, artwork_cache: ArtworkCache, parent=None):
        super().__init__(parent)
        self._artwork_cache = artwork_cache
        self._client: ItunesClient | None = None
        self._playlist_ids: dict[str, ItunesPersistentID] = {}

    @Slot()
    def listPlaylists(self) -> None:
        """Emit the names of the iTunes playlists, or ``failed``."""
        self.progress.emit("Reading the playlist list from iTunes…")
        try:
            self._playlist_ids = self._get_client().list_playlists()
        except ItunesClientError as error:
            self.failed.emit(str(error))
            return
        except Exception:
            logger.exception("Unexpected error while listing playlists")
            self.failed.emit("Unexpected error while listing playlists; see the log for details.")
            return
        self.playlistsListed.emit(sorted(self._playlist_ids, key=str.casefold))

    @Slot(str)
    def importPlaylist(self, playlist_name: str) -> None:
        """Capture the named playlist (from the last ``listPlaylists``) and emit it, or ``failed``."""
        playlist_id = self._playlist_ids.get(playlist_name)
        if playlist_id is None:
            self.failed.emit(f"Playlist {playlist_name!r} is not in the last list read from iTunes.")
            return

        self.progress.emit(f"Importing {playlist_name!r} and its artwork from iTunes…")
        try:
            playlist = capture_playlist(self._get_client(), playlist_id, self._artwork_cache)
        except ItunesClientError as error:
            self.failed.emit(str(error))
            return
        except Exception:
            logger.exception("Unexpected error while importing playlist %r", playlist_name)
            self.failed.emit(f"Unexpected error while importing {playlist_name!r}; see the log for details.")
            return
        self.playlistImported.emit(playlist)

    @Slot(str, list)
    def commitPlaylist(self, playlist_name: str, track_ids: list[ItunesPersistentID]) -> None:
        """Create a new iTunes playlist with the tracks in the given order and emit it, or ``failed``.

        A name already used by another playlist is rejected by ``ItunesClient.create_playlist`` before
        anything is created.
        """
        self.progress.emit(f"Creating the playlist {playlist_name!r} in iTunes…")
        try:
            playlist = self._get_client().create_playlist(playlist_name, track_ids)
        except ItunesClientError as error:
            self.failed.emit(str(error))
            return
        except Exception:
            logger.exception("Unexpected error while creating playlist %r", playlist_name)
            self.failed.emit(f"Unexpected error while creating {playlist_name!r}; see the log for details.")
            return
        self.playlistCommitted.emit(playlist)

    def _get_client(self) -> ItunesClient:
        if self._client is None:
            self._client = ItunesClient()
        return self._client
