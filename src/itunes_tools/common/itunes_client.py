import contextlib
import threading
from collections.abc import Iterator

import pythoncom
import pywintypes
import win32com.client

from itunes_tools.common.exceptions import (
    DuplicatePlaylistNameError,
    ItunesClientThreadError,
    ItunesComError,
    PlaylistNotFoundError,
)
from itunes_tools.common.logger import get_logger
from itunes_tools.common.models import ItunesPersistentID, Playlist, Song

logger = get_logger(__name__)


class ItunesClient:
    """A wrapper around the ``iTunes.Application`` COM object.

    The COM object is created lazily on first use and then reused.

    **Threading:** COM objects belong to the thread that created them, so a client is bound to the
    thread that first uses it and raises ``ItunesClientThreadError`` if called from any other thread.
    To do COM work in a worker thread, create a separate client inside that thread.
    """

    def __init__(self, prog_id: str = "iTunes.Application"):
        self._prog_id = prog_id
        self._com_app: win32com.client.CDispatch | None = None
        self._owner_thread_id: int | None = None

    def list_playlists(self) -> dict[str, ItunesPersistentID]:
        """Return a mapping of playlist names to persistent IDs.

        :raises DuplicatePlaylistNameError: if two or more playlists share a name.
        :raises ItunesComError: if a COM call to iTunes fails.
        """
        playlists: dict[str, ItunesPersistentID] = {}
        duplicate_names: set[str] = set()
        with _com_errors_as_client_errors("list playlists"):
            for playlist_com in self._itunes_app.LibrarySource.Playlists:
                if playlist_com.Name in playlists:
                    duplicate_names.add(playlist_com.Name)
                playlists[playlist_com.Name] = self._get_persistent_id(playlist_com)

        if duplicate_names:
            raise DuplicatePlaylistNameError(sorted(duplicate_names))
        return playlists

    def get_playlist_by_id(self, persistent_id: ItunesPersistentID) -> Playlist:
        """Return the playlist with the given persistent ID, including its tracks.

        :raises PlaylistNotFoundError: if no playlist has that ID.
        :raises ItunesComError: if a COM call to iTunes fails.
        """
        with _com_errors_as_client_errors("read a playlist"):
            playlists_com = self._itunes_app.LibrarySource.Playlists
            # Returns None when no playlist has this ID.
            playlist_com = playlists_com.ItemByPersistentID(persistent_id.high, persistent_id.low)
            if playlist_com is None:
                raise PlaylistNotFoundError(persistent_id)

            return Playlist(
                id=persistent_id,
                name=playlist_com.Name,
                tracks=[
                    Song(
                        id=self._get_persistent_id(track_com),
                        name=track_com.Name,
                        artist=track_com.Artist,
                        album=track_com.Album,
                        duration=track_com.Duration,
                    )
                    for track_com in playlist_com.Tracks
                ],
            )

    @property
    def _itunes_app(self) -> win32com.client.CDispatch:
        """Return the ``iTunes.Application`` COM object, starting iTunes or attaching to it on first use.

        :raises ItunesClientThreadError: if called from a thread other than the one that first used the client.
        """
        current_thread_id = threading.get_ident()
        if self._owner_thread_id is not None and self._owner_thread_id != current_thread_id:
            raise ItunesClientThreadError()

        com_app = self._com_app
        if com_app is None:
            # Each thread must initialise COM before using it. Safe to call more than once:
            # the main thread is already initialised when pythoncom is imported.
            pythoncom.CoInitialize()
            com_app = win32com.client.Dispatch(self._prog_id)
            self._com_app = com_app
            self._owner_thread_id = current_thread_id
            logger.debug("iTunes COM object version %s initialized", com_app.Version)
        return com_app

    def _get_persistent_id(self, com_object: win32com.client.CDispatch) -> ItunesPersistentID:
        high, low = self._itunes_app.GetITObjectPersistentIDs(com_object)
        return ItunesPersistentID(high=high, low=low)


@contextlib.contextmanager
def _com_errors_as_client_errors(action: str) -> Iterator[None]:
    """Re-raise ``pywintypes.com_error`` as ``ItunesComError``, keeping the original as the cause.

    :param action: What the client was doing, completing the sentence "while trying to ...".
    """
    try:
        yield
    except pywintypes.com_error as error:
        raise ItunesComError(action) from error
