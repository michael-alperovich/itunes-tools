import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtWidgets import QStyleOptionViewItem

from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.sorter.song_list import (
    ARTWORK_SIZE,
    BUTTON_SIZE,
    PLAY_FROM_START,
    PLAY_LAST_SECONDS,
    ROW_ACTIONS,
    SEND_TO_GROUP,
    AlbumRole,
    ArtistRole,
    IsPlayingRole,
    SongListModel,
    SongRole,
    SongRowDelegate,
)

pytestmark = pytest.mark.usefixtures("qt_application")


def test_model_has_one_row_per_song_in_order(tmp_path, make_song):
    model = SongListModel(ArtworkCache(tmp_path))
    songs = [make_song(1, "First"), make_song(2, "Second")]

    model.set_songs(songs)

    assert model.rowCount() == 2
    assert [model.data(model.index(row)) for row in range(2)] == ["First", "Second"]
    assert model.songs() == songs


def test_model_exposes_artist_album_and_song_roles(tmp_path, make_song):
    model = SongListModel(ArtworkCache(tmp_path))
    song = make_song(1, artist="Queen", album="Jazz")
    model.set_songs([song])
    index = model.index(0)

    assert model.data(index, ArtistRole) == "Queen"
    assert model.data(index, AlbumRole) == "Jazz"
    assert model.data(index, SongRole) == song
    assert model.data(index, Qt.ItemDataRole.ToolTipRole) is None


def test_model_returns_a_placeholder_pixmap_when_artwork_is_not_cached(tmp_path, make_song):
    model = SongListModel(ArtworkCache(tmp_path))
    model.set_songs([make_song(1)])

    pixmap = model.data(model.index(0), Qt.ItemDataRole.DecorationRole)

    assert not pixmap.isNull()
    assert (pixmap.width(), pixmap.height()) == (ARTWORK_SIZE, ARTWORK_SIZE)


def test_model_scales_cached_artwork_to_the_row_size(tmp_path, make_song):
    image = QImage(200, 100, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    assert image.save(str(tmp_path / "0000000000000001.png"))
    model = SongListModel(ArtworkCache(tmp_path))
    model.set_songs([make_song(1)])

    pixmap = model.data(model.index(0), Qt.ItemDataRole.DecorationRole)

    assert (pixmap.width(), pixmap.height()) == (ARTWORK_SIZE, ARTWORK_SIZE // 2)


def test_set_songs_replaces_previous_songs(tmp_path, make_song):
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


def test_set_playing_song_marks_only_that_row_and_repaints_old_and_new_rows(tmp_path, make_song):
    model = SongListModel(ArtworkCache(tmp_path))
    songs = [make_song(1), make_song(2), make_song(3)]
    model.set_songs(songs)
    model.set_playing_song(songs[0].id)
    changed_rows = []
    model.dataChanged.connect(lambda top_left, bottom_right, roles: changed_rows.append(top_left.row()))

    model.set_playing_song(songs[2].id)

    assert model.playing_row() == 2
    assert [model.data(model.index(row), IsPlayingRole) for row in range(3)] == [False, False, True]
    assert sorted(changed_rows) == [0, 2]


def test_playing_row_is_none_without_a_playing_song_in_the_list(tmp_path, make_song):
    model = SongListModel(ArtworkCache(tmp_path))
    model.set_songs([make_song(1)])

    assert model.playing_row() is None
    model.set_playing_song(make_song(99).id)
    assert model.playing_row() is None


def test_button_at_finds_each_button_and_nothing_elsewhere():
    delegate = SongRowDelegate()
    row = QRect(0, 0, 600, 56)

    for action, rect in zip(ROW_ACTIONS, delegate.button_rects(row)):
        assert delegate.button_at(row, rect.center()) == action
    assert delegate.button_at(row, QPoint(10, 10)) is None


def test_only_the_play_buttons_are_enabled():
    enabled = {action.name: action.enabled for action in ROW_ACTIONS}

    assert enabled == {PLAY_FROM_START: True, PLAY_LAST_SECONDS: True, SEND_TO_GROUP: False}


def click_button(delegate: SongRowDelegate, model: SongListModel, action_index: int) -> list[tuple[str, int]]:
    """Release the left mouse button over a row button of the first row; return the triggered actions."""
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 600, 56)
    position = QPointF(delegate.button_rects(option.rect)[action_index].center())
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        position,
        position,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    triggered = []
    delegate.rowActionTriggered.connect(lambda name, index: triggered.append((name, index.row())))
    delegate.editorEvent(event, model, option, model.index(0))
    return triggered


def test_clicking_an_enabled_button_triggers_its_action_for_the_row(tmp_path, make_song):
    model = SongListModel(ArtworkCache(tmp_path))
    model.set_songs([make_song(1)])

    assert click_button(SongRowDelegate(), model, 1) == [(PLAY_LAST_SECONDS, 0)]


def test_clicking_a_disabled_button_triggers_nothing(tmp_path, make_song):
    model = SongListModel(ArtworkCache(tmp_path))
    model.set_songs([make_song(1)])

    assert click_button(SongRowDelegate(), model, 2) == []
