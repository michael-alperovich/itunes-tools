"""Read-only checks of ``ItunesClient`` against a real iTunes.

Deselected by default; run with ``uv run pytest -m itunes``. ``Dispatch`` starts iTunes if it is
not already running. These tests must never change tracks, playlists or library settings.

Their job is to catch drift between the fakes in ``tests/conftest.py`` and what real COM returns.
"""

import pytest

from itunes_tools.common.exceptions import PlaylistNotFoundError
from itunes_tools.common.itunes_client import ItunesClient
from itunes_tools.common.models import ItunesPersistentID

pytestmark = pytest.mark.itunes


@pytest.fixture(scope="module")
def live_client() -> ItunesClient:
    """One client per module, so iTunes is dispatched once."""
    return ItunesClient()


def test_listed_playlist_can_be_read_back_by_id(live_client):
    # Real persistent IDs must fit ItunesPersistentID (signed 32-bit halves) and ItemByPersistentID
    # must accept them. The last playlist is used because the first is the whole library, which is slow.
    playlists = live_client.list_playlists()
    assert playlists, "Expected at least the library playlist"
    name, persistent_id = list(playlists.items())[-1]

    playlist = live_client.get_playlist_by_id(persistent_id)

    assert playlist.id == persistent_id
    assert playlist.name == name


def test_unknown_playlist_id_raises_not_found(live_client):
    # Checks the fake's assumption that ItemByPersistentID returns None for an unknown ID.
    unknown_id = ItunesPersistentID(high=0x7FFFFFFF, low=0x7FFFFFFF)

    with pytest.raises(PlaylistNotFoundError):
        live_client.get_playlist_by_id(unknown_id)
