import pytest
from PySide6.QtCore import QEvent, QModelIndex, QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QStyleOptionViewItem

from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.sorter.song_list import SongListModel
from itunes_tools.sorter.song_row_delegate import (
    BUTTON_SIZE,
    DELETE_GROUP,
    GROUP_ACTIONS,
    GROUP_ROW_HEIGHT,
    MOVE_TO_GROUP,
    PLAY_LAST_SECONDS,
    ROW_HEIGHT,
    SONG_ACTIONS,
    TOGGLE_GROUP,
    SongRowDelegate,
    row_actions,
)
from itunes_tools.sorter.sorting_items import SongGroup

pytestmark = pytest.mark.usefixtures("qt_application")

ROW = QRect(0, 0, 600, 56)


@pytest.fixture
def model(tmp_path, make_song) -> SongListModel:
    """A song at row 0, and a group holding one song at row 1."""
    model = SongListModel(ArtworkCache(tmp_path))
    model.set_items([make_song(1), SongGroup(name="G", songs=[make_song(2)])])
    return model


def test_delegate_places_the_buttons_inside_the_row_left_to_right():
    row = QRect(0, 100, 600, 56)

    rects = SongRowDelegate.button_rects(row, 3)

    assert len(rects) == 3
    assert all(row.contains(rect) and rect.width() == BUTTON_SIZE for rect in rects)
    assert [rect.left() for rect in rects] == sorted(rect.left() for rect in rects)


def test_songs_get_song_buttons_and_groups_get_group_buttons(model):
    group = model.index(1, 0)

    assert row_actions(model.index(0, 0)) == SONG_ACTIONS
    assert row_actions(model.index(0, 0, group)) == SONG_ACTIONS
    assert row_actions(group) == GROUP_ACTIONS
    assert MOVE_TO_GROUP in {action.name for action in SONG_ACTIONS}


def test_group_rows_are_lower_than_song_rows(model):
    delegate = SongRowDelegate()
    option = QStyleOptionViewItem()

    assert delegate.sizeHint(option, model.index(0, 0)) == QSize(0, ROW_HEIGHT)
    assert delegate.sizeHint(option, model.index(1, 0)) == QSize(0, GROUP_ROW_HEIGHT)


def test_button_at_finds_each_button_and_nothing_elsewhere(model):
    delegate = SongRowDelegate()
    index = model.index(0, 0)

    for action, rect in zip(SONG_ACTIONS, delegate.button_rects(ROW, len(SONG_ACTIONS))):
        assert delegate.button_at(index, ROW, rect.center()) == action
    assert delegate.button_at(index, ROW, QPoint(10, 10)) is None


def click_button(delegate: SongRowDelegate, index: QModelIndex, action_index: int) -> list[tuple[str, QModelIndex]]:
    """Release the left mouse button over a button of the row at ``index``; return the triggered actions."""
    option = QStyleOptionViewItem()
    option.rect = ROW
    button_count = len(row_actions(index))
    position = QPointF(delegate.button_rects(option.rect, button_count)[action_index].center())
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        position,
        position,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    triggered = []
    delegate.rowActionTriggered.connect(lambda name, triggered_index: triggered.append((name, triggered_index)))
    delegate.editorEvent(event, index.model(), option, index)
    return triggered


def test_clicking_a_song_button_triggers_its_action_for_the_row(model):
    song_in_group = model.index(0, 0, model.index(1, 0))

    assert click_button(SongRowDelegate(), song_in_group, 1) == [(PLAY_LAST_SECONDS, song_in_group)]


def test_clicking_a_group_button_triggers_the_group_action(model):
    group = model.index(1, 0)

    assert click_button(SongRowDelegate(), group, 1) == [(DELETE_GROUP, group)]


def test_clicking_a_group_arrow_toggles_the_group(model):
    delegate = SongRowDelegate()
    group = model.index(1, 0)
    option = QStyleOptionViewItem()
    option.rect = ROW
    position = QPointF(delegate.group_arrow_rect(ROW).center())
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        position,
        position,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    triggered = []
    delegate.rowActionTriggered.connect(lambda name, index: triggered.append((name, index)))

    delegate.editorEvent(event, model, option, group)
    delegate.editorEvent(event, model, option, model.index(0, 0))  # a song row has no arrow

    assert triggered == [(TOGGLE_GROUP, group)]
