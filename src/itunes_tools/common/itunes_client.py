import typing

import win32com.client

from itunes_tools.common.logger import get_logger
from itunes_tools.common.models import ItunesPersistentID, Playlist, Song

logger = get_logger(__name__)


class ItunesClient:
    """A wrapper around the ``iTunes.Application`` COM object.

    Has lazy initialization and re-use of the first COM object.
    """

    def __init__(self, itunes_app: str = "iTunes.Application"):
        self._prog_id = itunes_app
        self._com_app: win32com.client.CDispatch | None = None

    @property
    def _itunes_app(self) -> win32com.client.CDispatch:
        """Return the ``iTunes.Application`` COM object, starting iTunes or attaching to it on first use."""
        if self._com_app is None:
            self._com_app = win32com.client.Dispatch(self._prog_id)
            logger.debug("iTunes COM object version %s initialized", self._com_app.Version)
        return typing.cast(win32com.client.CDispatch, self._com_app)

    def _get_object_id(self, obj: win32com.client.CDispatch) -> ItunesPersistentID:
        com_id = self._itunes_app.GetITObjectPersistentIDs(obj)
        return ItunesPersistentID(high=com_id[0], low=com_id[1])

    def list_playlists(self) -> dict[str, ItunesPersistentID]:
        """Return a mapping of Playlist names and COM IDs."""
        return {p.Name: self._get_object_id(p) for p in self._itunes_app.LibrarySource.Playlists}

    def get_playlist_by_id(self, com_id: ItunesPersistentID) -> Playlist:
        """Return the playlist with the given name."""
        try:
            playlist_com = next(
                filter(lambda p: self._get_object_id(p) == com_id, self._itunes_app.LibrarySource.Playlists)
            )
            return Playlist(
                id=com_id,
                name=playlist_com.Name,
                tracks=[Song(
                    id=self._get_object_id(s),
                    name=s.Name,
                    artist=s.Artist,
                    album=s.Album,
                    duration=s.Duration,
                ) for s in playlist_com.Tracks],
            )
        except StopIteration:
            raise ValueError(f"Playlist with ID {com_id} not found")
