"""Shared test doubles for the iTunes COM layer.

Unit tests never talk to a real iTunes. Two kinds of doubles are used:

* **Fakes** (``FakeItunesApp``, ``FakeComCollection``, ``SimpleNamespace`` tracks and playlists)
  provide behaviour. They implement only the COM surface ``ItunesClient`` uses, so a typo in a
  property name raises ``AttributeError`` instead of silently passing.
* **One mock** (``com_dispatch``) replaces ``win32com.client.Dispatch``, the single entry point to
  COM, so tests can verify how and when the COM application is created.
"""

from collections.abc import Callable, Iterable, Iterator
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


class FakeItunesApp:
    """Hand-written stand-in for the ``iTunes.Application`` COM object.

    Persistent IDs are not COM properties of tracks or playlists; the real application returns
    them from ``GetITObjectPersistentIDs``. The fake reads them from each fake object's
    ``persistent_ids`` attribute.
    """

    def __init__(self):
        self.Version = "12.13.0.0"
        self.LibrarySource = SimpleNamespace(Playlists=FakeComCollection([]))

    def GetITObjectPersistentIDs(self, com_object: SimpleNamespace) -> tuple[int, int]:
        return com_object.persistent_ids

    def set_playlists(self, *playlists: SimpleNamespace) -> None:
        """Test helper (not part of COM): replace the library's playlists."""
        self.LibrarySource.Playlists = FakeComCollection(playlists)


@pytest.fixture
def make_com_track() -> Callable[..., SimpleNamespace]:
    """Return a factory for fake ``IITTrack`` COM objects with sensible defaults."""

    def factory(
        high: int,
        low: int,
        name: str = "Song",
        artist: str = "Artist",
        album: str = "Album",
        duration: int = 180,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            persistent_ids=(high, low),
            Name=name,
            Artist=artist,
            Album=album,
            Duration=duration,
        )

    return factory


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
def fake_itunes(com_dispatch: MagicMock) -> FakeItunesApp:
    """Return the fake application that ``ItunesClient`` will receive from ``Dispatch``."""
    return com_dispatch.return_value
