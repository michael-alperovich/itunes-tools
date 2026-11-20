from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.common.models import ItunesPersistentID, Song
from itunes_tools.sorter.song_list import (
    ARTWORK_SIZE,
    BUTTON_SIZE,
    ROW_ACTIONS,
    AlbumRole,
    ArtistRole,
    SongListModel,
    SongRole,
    SongRowDelegate,
)

MODIFIED = datetime(2023, 7, 8, 20, 33, 28, tzinfo=UTC)


@pytest.fixture(scope="session", autouse=True)
def qt_application() -> Iterator[QApplication]:
    """A ``QApplication``, needed before creating pixmaps. One per process, so share it."""
    yield QApplication.instance() or QApplication([])


def make_song(low: int, name: str = "Song", artist: str = "Artist", album: str = "Album") -> Song:
    return Song(
        id=ItunesPersistentID(high=0, low=low),
        name=name,
        artist=artist,
        album=album,
        album_artist="",
        genre="",
        year=0,
        track_number=0,
        disc_number=0,
        duration=180,
        date_added=MODIFIED,
        modification_date=MODIFIED,
        location=None,
        artwork_count=0,
    )


def test_model_has_one_row_per_song_in_order(tmp_path):
    model = SongListModel(ArtworkCache(tmp_path))
    songs = [make_song(1, "First"), make_song(2, "Second")]

    model.set_songs(songs)

    assert model.rowCount() == 2
    assert [model.data(model.index(row)) for row in range(2)] == ["First", "Second"]
    assert model.songs() == songs


def test_model_exposes_artist_album_and_song_roles(tmp_path):
    model = SongListModel(ArtworkCache(tmp_path))
    song = make_song(1, artist="Queen", album="Jazz")
    model.set_songs([song])
    index = model.index(0)

    assert model.data(index, ArtistRole) == "Queen"
    assert model.data(index, AlbumRole) == "Jazz"
    assert model.data(index, SongRole) == song
    assert model.data(index, Qt.ItemDataRole.ToolTipRole) is None


def test_model_returns_a_placeholder_pixmap_when_artwork_is_not_cached(tmp_path):
    model = SongListModel(ArtworkCache(tmp_path))
    model.set_songs([make_song(1)])

    pixmap = model.data(model.index(0), Qt.ItemDataRole.DecorationRole)

    assert not pixmap.isNull()
    assert (pixmap.width(), pixmap.height()) == (ARTWORK_SIZE, ARTWORK_SIZE)


def test_model_scales_cached_artwork_to_the_row_size(tmp_path):
    image = QImage(200, 100, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    assert image.save(str(tmp_path / "0000000000000001.png"))
    model = SongListModel(ArtworkCache(tmp_path))
    model.set_songs([make_song(1)])

    pixmap = model.data(model.index(0), Qt.ItemDataRole.DecorationRole)

    assert (pixmap.width(), pixmap.height()) == (ARTWORK_SIZE, ARTWORK_SIZE // 2)


def test_set_songs_replaces_previous_songs(tmp_path):
    model = SongListModel(ArtworkCache(tmp_path))
    model.set_songs([make_song(1), make_song(2)])

    model.set_songs([make_song(3, "Only")])

    assert model.rowCount() == 1
    assert model.data(model.index(0)) == "Only"


def test_delegate_places_one_button_per_action_inside_the_row():
    row = QRect(0, 100, 600, 56)

    rects = SongRowDelegate().button_rects(row)

    assert len(rects) == len(ROW_ACTIONS)
    assert all(row.contains(rect) and rect.width() == BUTTON_SIZE for rect in rects)
    assert [rect.left() for rect in rects] == sorted(rect.left() for rect in rects)
