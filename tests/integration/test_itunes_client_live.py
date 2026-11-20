"""Read-only checks of ``ItunesClient`` against a real iTunes.

Deselected by default; run with ``uv run pytest -m itunes``. ``Dispatch`` starts iTunes if it is
not already running. These tests must never change tracks, playlists or library settings.

Their job is to catch drift between the fakes in ``tests/conftest.py`` and what real COM returns.
"""

import pytest

from itunes_tools.common.itunes_client import ItunesClient
from itunes_tools.common.models import ItunesPersistentID

pytestmark = pytest.mark.itunes


@pytest.fixture(scope="module")
def live_client() -> ItunesClient:
    """One client per module, so iTunes is dispatched once."""
    return ItunesClient()


def test_list_playlists_returns_persistent_ids(live_client):
    playlists = live_client.list_playlists()

    assert playlists, "Expected at least the library playlist"
    for name, persistent_id in playlists.items():
        assert isinstance(name, str)
        assert isinstance(persistent_id, ItunesPersistentID)
