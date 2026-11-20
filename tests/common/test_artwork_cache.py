import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, create_autospec

import pytest

from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.common.itunes_client import ItunesClient
from itunes_tools.common.models import ItunesPersistentID, Song

MODIFIED = datetime(2023, 7, 8, 20, 33, 28, tzinfo=UTC)


def make_song(low: int = 1, artwork_count: int = 1, modification_date: datetime = MODIFIED) -> Song:
    return Song(
        id=ItunesPersistentID(high=0, low=low),
        name="Song",
        artist="Artist",
        album="Album",
        album_artist="",
        genre="",
        year=0,
        track_number=0,
        disc_number=0,
        duration=180,
        date_added=MODIFIED,
        modification_date=modification_date,
        location=None,
        artwork_count=artwork_count,
    )


def set_mtime(path: Path, moment: datetime) -> None:
    os.utime(path, (moment.timestamp(), moment.timestamp()))


@pytest.fixture
def client() -> MagicMock:
    """A client mock whose ``export_artwork`` writes a PNG like the real one."""

    def export_artwork(track_id: ItunesPersistentID, destination_stem: Path) -> Path:
        destination = destination_stem.with_name(destination_stem.name + ".png")
        destination.write_bytes(b"image")
        return destination

    client = create_autospec(ItunesClient, instance=True)
    client.export_artwork.side_effect = export_artwork
    return client


def test_get_path_returns_cached_image(tmp_path):
    image = tmp_path / "0000000000000001.jpg"
    image.write_bytes(b"image")

    assert ArtworkCache(tmp_path).get_path(make_song()) == image


def test_get_path_returns_none_when_not_cached_or_folder_missing(tmp_path):
    assert ArtworkCache(tmp_path).get_path(make_song()) is None
    assert ArtworkCache(tmp_path / "missing").get_path(make_song()) is None


def test_get_path_returns_none_for_no_artwork_marker(tmp_path):
    (tmp_path / "0000000000000001.none").touch()

    assert ArtworkCache(tmp_path).get_path(make_song()) is None


def test_get_path_still_returns_outdated_image(tmp_path):
    image = tmp_path / "0000000000000001.png"
    image.write_bytes(b"old image")
    set_mtime(image, datetime(2020, 1, 1, tzinfo=UTC))

    assert ArtworkCache(tmp_path).get_path(make_song()) == image


def test_fill_exports_missing_artwork_and_creates_folder(tmp_path, client):
    folder = tmp_path / "cache"
    song = make_song()

    ArtworkCache(folder).fill([song], client)

    client.export_artwork.assert_called_once_with(song.id, folder / "0000000000000001")
    assert ArtworkCache(folder).get_path(song) == folder / "0000000000000001.png"


def test_fill_skips_up_to_date_entries(tmp_path, client):
    image = tmp_path / "0000000000000001.png"
    image.write_bytes(b"image")
    set_mtime(image, datetime(2024, 1, 1, tzinfo=UTC))

    ArtworkCache(tmp_path).fill([make_song()], client)

    client.export_artwork.assert_not_called()


def test_fill_replaces_outdated_entry(tmp_path, client):
    old_image = tmp_path / "0000000000000001.jpg"
    old_image.write_bytes(b"old image")
    set_mtime(old_image, datetime(2020, 1, 1, tzinfo=UTC))

    ArtworkCache(tmp_path).fill([make_song()], client)

    assert not old_image.exists()
    assert ArtworkCache(tmp_path).get_path(make_song()) == tmp_path / "0000000000000001.png"


def test_fill_records_songs_without_artwork_without_asking_itunes(tmp_path, client):
    ArtworkCache(tmp_path).fill([make_song(artwork_count=0)], client)

    client.export_artwork.assert_not_called()
    assert (tmp_path / "0000000000000001.none").exists()


def test_fill_records_no_artwork_when_export_finds_none(tmp_path, client):
    client.export_artwork.side_effect = None
    client.export_artwork.return_value = None

    ArtworkCache(tmp_path).fill([make_song()], client)

    assert (tmp_path / "0000000000000001.none").exists()
    assert ArtworkCache(tmp_path).get_path(make_song()) is None


def test_fill_rechecks_outdated_no_artwork_marker(tmp_path, client):
    marker = tmp_path / "0000000000000001.none"
    marker.touch()
    set_mtime(marker, datetime(2020, 1, 1, tzinfo=UTC))

    ArtworkCache(tmp_path).fill([make_song()], client)

    assert not marker.exists()
    assert ArtworkCache(tmp_path).get_path(make_song()) == tmp_path / "0000000000000001.png"
