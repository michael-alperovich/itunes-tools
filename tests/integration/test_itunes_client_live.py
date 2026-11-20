"""Read-only checks of ``ItunesClient`` against a real iTunes.

Deselected by default; run with ``uv run pytest -m itunes``. ``Dispatch`` starts iTunes if it is
not already running. These tests must never change tracks, playlists or library settings.

Their job is to catch drift between the fakes in ``tests/conftest.py`` and what real COM returns.
"""

import pytest

from itunes_tools.common.exceptions import PlaylistNotFoundError
from itunes_tools.common.itunes_client import ItunesClient
from itunes_tools.common.models import ItunesPersistentID, Playlist

pytestmark = pytest.mark.itunes


@pytest.fixture(scope="module")
def live_client() -> ItunesClient:
    """One client per module, so iTunes is dispatched once."""
    return ItunesClient()


@pytest.fixture(scope="module")
def live_playlist(live_client) -> Playlist:
    """The last listed playlist that has songs; the first playlist is the whole library, which is slow."""
    for persistent_id in reversed(list(live_client.list_playlists().values())):
        playlist = live_client.get_playlist_by_id(persistent_id)
        if playlist.tracks:
            return playlist
    pytest.skip("No playlist with songs")


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


def test_real_songs_survive_json_dump_and_validation(live_playlist):
    # Checks that real COM values (local-time pywintypes dates, paths) become plain, round-trippable types.
    dumped = live_playlist.model_dump(mode="json")

    assert Playlist.model_validate(dumped) == live_playlist


def test_file_tracks_have_existing_locations(live_playlist):
    # Checks that the CastTo to IITFileOrCDTrack works on real tracks.
    locations = [song.location for song in live_playlist.tracks if song.location is not None]

    assert locations, "Expected at least one song with a file"
    assert all(location.is_file() for location in locations)


def test_export_artwork_writes_an_image(live_client, live_playlist, tmp_path):
    songs_with_artwork = [song for song in live_playlist.tracks if song.artwork_count > 0]
    if not songs_with_artwork:
        pytest.skip("No song with artwork in the playlist")

    exported = live_client.export_artwork(songs_with_artwork[0].id, tmp_path / "cover")

    assert exported is not None
    assert exported.parent == tmp_path
    assert exported.stat().st_size > 0
