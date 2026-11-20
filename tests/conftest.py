"""Shared test doubles for the iTunes COM layer.

Unit tests never talk to a real iTunes. Two kinds of doubles are used:

* **Fakes** (``FakeItunesApp``, ``FakeComCollection``, ``SimpleNamespace`` tracks and playlists)
  provide behaviour. They implement only the COM surface ``ItunesClient`` uses, so a typo in a
  property name raises ``AttributeError`` instead of silently passing.
* **Mocks** replace the two pywin32 entry points: ``com_dispatch`` stands in for
  ``win32com.client.Dispatch``, so tests can verify how and when the COM application is created, and
  ``com_cast_to`` for ``win32com.client.CastTo``, returning the fake object unchanged because fakes
  already carry the members of the derived interfaces.
"""

from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
import win32com.client


class FakeComCollection:
    """Mimics an iTunes COM collection: iterable, ``Count``, 1-based ``Item``, and ``ItemByPersistentID``."""

    def __init__(self, items: Iterable[Any]):
        self._items = list(items)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._items)

    @property
    def Count(self) -> int:
        return len(self._items)

    def Item(self, index: int) -> Any:
        return self._items[index - 1]  # COM collections are 1-based

    def ItemByPersistentID(self, high: int, low: int) -> Any:
        """Return the item with these persistent ID halves, or ``None`` like the real collection."""
        for item in self._items:
            if item.persistent_ids == (high, low):
                return item
        return None

    def append(self, item: Any) -> None:
        """Test helper (not part of COM): add an item at the end."""
        self._items.append(item)


class FakeArtwork:
    """Mimics ``IITArtwork``: an image format and ``SaveArtworkToFile``."""

    def __init__(self, format: int = 2, content: bytes = b"fake image"):
        self.Format = format
        self.content = content
        self.saved_paths: list[str] = []

    def SaveArtworkToFile(self, path: str) -> None:
        self.saved_paths.append(path)
        Path(path).write_bytes(self.content)


class FakeItunesApp:
    """Hand-written stand-in for the ``iTunes.Application`` COM object.

    Persistent IDs are not COM properties of tracks or playlists; the real application returns
    them from ``GetITObjectPersistentIDs``. The fake reads them from each fake object's
    ``persistent_ids`` attribute.
    """

    def __init__(self):
        self.Version = "12.13.0.0"
        self.LibrarySource = SimpleNamespace(Playlists=FakeComCollection([]))
        self.LibraryPlaylist = SimpleNamespace(Tracks=FakeComCollection([]))
        self._created_playlist_count = 0

    def GetITObjectPersistentIDs(self, com_object: SimpleNamespace) -> tuple[int, int]:
        return com_object.persistent_ids

    def CreatePlaylist(self, name: str) -> SimpleNamespace:
        """Create an empty user playlist with ``AddTrack``, and add it to the library's playlists."""
        self._created_playlist_count += 1
        tracks = FakeComCollection([])
        playlist = SimpleNamespace(
            persistent_ids=(1000, self._created_playlist_count),
            Name=name,
            Tracks=tracks,
            AddTrack=tracks.append,
        )
        self.LibrarySource.Playlists.append(playlist)
        return playlist

    def set_playlists(self, *playlists: SimpleNamespace) -> None:
        """Test helper (not part of COM): replace the library's playlists."""
        self.LibrarySource.Playlists = FakeComCollection(playlists)

    def set_library_tracks(self, *tracks: SimpleNamespace) -> None:
        """Test helper (not part of COM): replace the tracks of the whole library."""
        self.LibraryPlaylist.Tracks = FakeComCollection(tracks)


# Real COM dates are timezone-aware ``pywintypes.datetime`` values in local time.
FAKE_DATE_ADDED = datetime(2022, 3, 7, 12, 39, 30, tzinfo=UTC)
FAKE_MODIFICATION_DATE = datetime(2023, 7, 8, 20, 33, 28, tzinfo=UTC)
FAKE_LOCATION = r"D:\Music\Artist\Album\Song.mp3"
TRACK_KIND_FILE = 1
TRACK_KIND_URL = 3


@pytest.fixture
def make_com_track() -> Callable[..., SimpleNamespace]:
    """Return a factory for fake track COM objects with sensible defaults.

    File tracks (the default kind) also carry the ``IITFileOrCDTrack`` members ``AlbumArtist`` and
    ``Location``; other kinds lack them, like the real ``IITTrack``.
    """

    def factory(
        high: int,
        low: int,
        name: str = "Song",
        artist: str = "Artist",
        album: str = "Album",
        duration: int = 180,
        album_artist: str = "Album Artist",
        genre: str = "Pop",
        year: int = 2020,
        track_number: int = 1,
        disc_number: int = 1,
        date_added: datetime = FAKE_DATE_ADDED,
        modification_date: datetime = FAKE_MODIFICATION_DATE,
        location: str = FAKE_LOCATION,
        kind: int = TRACK_KIND_FILE,
        artworks: Iterable[FakeArtwork] = (),
    ) -> SimpleNamespace:
        track = SimpleNamespace(
            persistent_ids=(high, low),
            Kind=kind,
            Name=name,
            Artist=artist,
            Album=album,
            Genre=genre,
            Year=year,
            TrackNumber=track_number,
            DiscNumber=disc_number,
            Duration=duration,
            DateAdded=date_added,
            ModificationDate=modification_date,
            Artwork=FakeComCollection(artworks),
        )
        if kind == TRACK_KIND_FILE:
            track.AlbumArtist = album_artist
            track.Location = location
        return track

    return factory


@pytest.fixture
def make_artwork() -> type[FakeArtwork]:
    """Return the ``FakeArtwork`` class, for ``make_com_track(artworks=[...])`` (conftest is not importable)."""
    return FakeArtwork


@pytest.fixture
def make_com_playlist() -> Callable[..., SimpleNamespace]:
    """Return a factory for fake ``IITPlaylist`` COM objects."""

    def factory(high: int, low: int, name: str = "Playlist", tracks: Iterable[SimpleNamespace] = ()) -> SimpleNamespace:
        return SimpleNamespace(
            persistent_ids=(high, low),
            Name=name,
            Tracks=FakeComCollection(tracks),
        )

    return factory


@pytest.fixture
def com_dispatch(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace ``win32com.client.Dispatch`` so no real iTunes is started.

    :return: The ``Dispatch`` mock. Its ``return_value`` is a ``FakeItunesApp``.
    """
    dispatch = MagicMock(name="Dispatch", return_value=FakeItunesApp())
    monkeypatch.setattr(win32com.client, "Dispatch", dispatch)
    return dispatch


@pytest.fixture
def com_cast_to(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace ``win32com.client.CastTo`` with a mock that returns the fake object unchanged.

    :return: The ``CastTo`` mock, so tests can check which interfaces were requested.
    """
    cast_to = MagicMock(name="CastTo", side_effect=lambda com_object, interface_name: com_object)
    monkeypatch.setattr(win32com.client, "CastTo", cast_to)
    return cast_to


@pytest.fixture
def fake_itunes(com_dispatch: MagicMock, com_cast_to: MagicMock) -> FakeItunesApp:
    """Return the fake application that ``ItunesClient`` will receive from ``Dispatch``."""
    return com_dispatch.return_value
