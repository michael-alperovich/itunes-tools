import contextlib
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pythoncom
import pywintypes
import win32com.client

from itunes_tools.common.exceptions import (
    DuplicatePlaylistNameError,
    ItunesClientThreadError,
    ItunesComError,
    PlaylistNameTakenError,
    PlaylistNotFoundError,
    TrackNotFoundError,
)
from itunes_tools.common.logger import get_logger
from itunes_tools.common.models import ItunesPersistentID, Playlist, Song

logger = get_logger(__name__)

# ``ITTrackKind`` values of tracks backed by a file, which implement ``IITFileOrCDTrack``.
TRACK_KINDS_WITH_FILE = (1, 2)  # ITTrackKindFile, ITTrackKindCD

# ``ITArtworkFormat`` values. Unknown formats still get saved; Qt detects the format from the content.
ARTWORK_FORMAT_EXTENSIONS = {1: ".jpg", 2: ".png", 3: ".bmp"}
UNKNOWN_ARTWORK_EXTENSION = ".img"


class ItunesClient:
    """A wrapper around the ``iTunes.Application`` COM object.

    The COM object is created lazily on first use and then reused.

    **Threading:** COM objects belong to the thread that created them, so a client is bound to the
    thread that first uses it and raises ``ItunesClientThreadError`` if called from any other thread.
    To do COM work in a worker thread, create a separate client inside that thread.

    **Interfaces:** when pywin32's generated type library cache exists, COM objects arrive as wrappers
    for their declared interface (``IITTrack``, ``IITPlaylist``), which hide members of derived
    interfaces such as ``IITFileOrCDTrack.Location`` or ``IITUserPlaylist.AddTrack``. The client
    therefore uses ``win32com.client.CastTo`` before touching those members.
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
                tracks=[self._song_from_com(track_com) for track_com in playlist_com.Tracks],
            )

    def create_playlist(self, name: str, track_ids: list[ItunesPersistentID]) -> Playlist:
        """Create a new playlist holding the given tracks in the given order.

        Everything is checked before the playlist is created, so a rejected call changes nothing.

        :param name: The new playlist's name. Must not be used by any existing playlist (exact match).
        :param track_ids: Persistent IDs of library tracks, in the order they should appear.
        :return: The new playlist, read back from iTunes.
        :raises ValueError: if ``name`` is empty or only whitespace.
        :raises PlaylistNameTakenError: if a playlist with this name already exists.
        :raises DuplicatePlaylistNameError: if the library already breaks the unique-name rule.
        :raises TrackNotFoundError: if any of the tracks is no longer in the library.
        :raises ItunesComError: if a COM call to iTunes fails. If this happens while adding tracks, the
            new playlist exists but may be incomplete; the error message says so.
        """
        if not name.strip():
            raise ValueError("A playlist name must not be blank")
        if name in self.list_playlists():
            raise PlaylistNameTakenError(name)

        with _com_errors_as_client_errors("create a playlist"):
            tracks_com = self._get_library_tracks_com(track_ids)
            # CreatePlaylist is declared to return IITPlaylist; AddTrack lives on IITUserPlaylist.
            playlist_com = win32com.client.CastTo(self._itunes_app.CreatePlaylist(name), "IITUserPlaylist")
            new_playlist_id = self._get_persistent_id(playlist_com)

        with _com_errors_as_client_errors(f"add songs to the new playlist {name!r}, which may now be incomplete"):
            for track_com in tracks_com:
                playlist_com.AddTrack(track_com)

        logger.info("Created playlist %r with %d songs", name, len(tracks_com))
        return self.get_playlist_by_id(new_playlist_id)

    def export_artwork(self, track_id: ItunesPersistentID, destination_stem: Path) -> Path | None:
        """Save the track's first artwork image to a file.

        :param track_id: Persistent ID of a library track.
        :param destination_stem: Path of the file to write, without extension. Its folder must exist.
            The extension is added from the image format (``.jpg``, ``.png``, ``.bmp`` or ``.img``).
        :return: The written file, or ``None`` if the track has no artwork.
        :raises TrackNotFoundError: if the track is no longer in the library.
        :raises ItunesComError: if a COM call to iTunes fails.
        """
        with _com_errors_as_client_errors("export album artwork"):
            [track_com] = self._get_library_tracks_com([track_id])
            if track_com.Artwork.Count == 0:
                return None
            artwork_com = track_com.Artwork.Item(1)  # COM collections are 1-based
            extension = ARTWORK_FORMAT_EXTENSIONS.get(artwork_com.Format, UNKNOWN_ARTWORK_EXTENSION)
            # iTunes rejects relative paths and forward slashes, so pass an absolute Windows path.
            destination = destination_stem.parent.absolute() / (destination_stem.name + extension)
            artwork_com.SaveArtworkToFile(str(destination))
        return destination

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

    def _get_library_tracks_com(self, track_ids: list[ItunesPersistentID]) -> list[win32com.client.CDispatch]:
        """Return the library's COM tracks for these IDs, in the same order.

        :raises TrackNotFoundError: listing every ID that is not in the library.
        """
        library_tracks_com = self._itunes_app.LibraryPlaylist.Tracks
        tracks_com = []
        missing_ids = []
        for track_id in track_ids:
            # Returns None when no track has this ID.
            track_com = library_tracks_com.ItemByPersistentID(track_id.high, track_id.low)
            if track_com is None:
                missing_ids.append(track_id)
            tracks_com.append(track_com)

        if missing_ids:
            raise TrackNotFoundError(missing_ids)
        return tracks_com

    def _song_from_com(self, track_com: win32com.client.CDispatch) -> Song:
        """Build a ``Song`` from an ``IITTrack`` COM object."""
        album_artist = ""
        location = None
        if track_com.Kind in TRACK_KINDS_WITH_FILE:
            file_track_com = win32com.client.CastTo(track_com, "IITFileOrCDTrack")
            album_artist = file_track_com.AlbumArtist
            # Location is an empty string when iTunes cannot find the file.
            if file_track_com.Location:
                location = Path(file_track_com.Location)

        return Song(
            id=self._get_persistent_id(track_com),
            name=track_com.Name,
            artist=track_com.Artist,
            album=track_com.Album,
            album_artist=album_artist,
            genre=track_com.Genre,
            year=track_com.Year,
            track_number=track_com.TrackNumber,
            disc_number=track_com.DiscNumber,
            duration=track_com.Duration,
            date_added=_to_utc_datetime(track_com.DateAdded),
            modification_date=_to_utc_datetime(track_com.ModificationDate),
            location=location,
            artwork_count=track_com.Artwork.Count,
        )


def _to_utc_datetime(com_datetime: datetime) -> datetime:
    """Convert a COM date (a timezone-aware ``pywintypes.datetime``) to a plain ``datetime`` in UTC.

    Plain datetimes keep model dumps free of pywin32 types.
    """
    return datetime.fromtimestamp(com_datetime.timestamp(), tz=UTC)


@contextlib.contextmanager
def _com_errors_as_client_errors(action: str) -> Iterator[None]:
    """Re-raise ``pywintypes.com_error`` as ``ItunesComError``, keeping the original as the cause.

    :param action: What the client was doing, completing the sentence "while trying to ...".
    """
    try:
        yield
    except pywintypes.com_error as error:
        raise ItunesComError(action) from error
