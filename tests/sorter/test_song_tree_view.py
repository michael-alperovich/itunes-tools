import pytest
from PySide6.QtCore import QItemSelection, QItemSelectionModel, QModelIndex
from PySide6.QtWidgets import QAbstractItemView

from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.sorter.song_list import IsGroupRole, SongListModel
from itunes_tools.sorter.song_tree_view import SongTreeView
from itunes_tools.sorter.sorting_items import SongGroup

pytestmark = pytest.mark.usefixtures("qt_application")

SelectionFlag = QItemSelectionModel.SelectionFlag
CLICK = SelectionFlag.ClearAndSelect | SelectionFlag.Rows
CTRL_CLICK = SelectionFlag.Toggle | SelectionFlag.Rows
Above = QAbstractItemView.DropIndicatorPosition.AboveItem
Below = QAbstractItemView.DropIndicatorPosition.BelowItem
On = QAbstractItemView.DropIndicatorPosition.OnItem
OnViewport = QAbstractItemView.DropIndicatorPosition.OnViewport


@pytest.fixture
def view(tmp_path, make_song) -> SongTreeView:
    """A view of ``A, G[B, C], D, Empty[], E``, groups expanded."""
    a, b, c, d, e = (make_song(low, name) for low, name in enumerate("ABCDE", start=1))
    model = SongListModel(ArtworkCache(tmp_path))
    model.set_items([a, SongGroup(name="G", songs=[b, c]), d, SongGroup(name="Empty"), e])
    song_tree_view = SongTreeView(model)
    for row in range(model.rowCount()):
        song_tree_view.expand(model.index(row, 0))
    return song_tree_view


def top(view: SongTreeView, row: int) -> QModelIndex:
    return view.model().index(row, 0)


def child(view: SongTreeView, group_row: int, row: int) -> QModelIndex:
    return view.model().index(row, 0, top(view, group_row))


def selected_names(view: SongTreeView) -> list[str]:
    return sorted(index.data() for index in view.selected_rows())


def tree(view: SongTreeView) -> list[str | tuple[str, list[str]]]:
    model = view.model()
    result: list[str | tuple[str, list[str]]] = []
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        if index.data(IsGroupRole):
            result.append((index.data(), [model.index(r, 0, index).data() for r in range(model.rowCount(index))]))
        else:
            result.append(index.data())
    return result


# --- Selection --------------------------------------------------------------------------------------


def test_click_selects_a_group_alone(view):
    selection = view.selectionModel()
    selection.select(top(view, 0), CLICK)

    selection.select(top(view, 1), CLICK)

    assert selected_names(view) == ["G"]


def test_range_skips_group_headers(view):
    # Shift+click from A to D: Qt selects the top-level range and the expanded group's songs.
    selection = QItemSelection(top(view, 0), top(view, 2))
    selection.select(child(view, 1, 0), child(view, 1, 1))

    view.selectionModel().select(selection, CLICK)

    assert selected_names(view) == ["A", "B", "C", "D"]


def test_ctrl_click_on_a_group_is_ignored(view):
    selection = view.selectionModel()
    selection.select(top(view, 0), CLICK)

    selection.select(top(view, 1), CTRL_CLICK)

    assert selected_names(view) == ["A"]


def test_ctrl_click_on_a_song_replaces_a_selected_group(view):
    selection = view.selectionModel()
    selection.select(top(view, 1), CLICK)

    selection.select(top(view, 2), CTRL_CLICK)
    selection.select(child(view, 1, 0), CTRL_CLICK)

    assert selected_names(view) == ["B", "D"]


def test_ctrl_click_deselects_a_song(view):
    selection = view.selectionModel()
    selection.select(top(view, 0), CLICK)
    selection.select(top(view, 2), CTRL_CLICK)

    selection.select(top(view, 0), CTRL_CLICK)

    assert selected_names(view) == ["D"]


def test_select_all_selects_songs_only(view):
    view.selectAll()

    assert selected_names(view) == ["A", "B", "C", "D", "E"]


def test_collapsing_a_group_deselects_its_songs(view):
    selection = view.selectionModel()
    selection.select(top(view, 0), CLICK)
    selection.select(child(view, 1, 1), CTRL_CLICK)

    view.collapse(top(view, 1))

    assert selected_names(view) == ["A"]


def test_row_buttons_act_on_the_selection_only_from_a_selected_row(view):
    selection = view.selectionModel()
    selection.select(top(view, 0), CLICK)
    selection.select(top(view, 2), CTRL_CLICK)

    assert sorted(index.data() for index in view.selected_songs_for(top(view, 2))) == ["A", "D"]
    assert [index.data() for index in view.selected_songs_for(top(view, 4))] == ["E"]


# --- Drop targets ---------------------------------------------------------------------------------


def target(view: SongTreeView, index: QModelIndex, indicator) -> tuple[str | None, int] | None:
    """Return ``drop_target`` with the parent as its name (``None`` for the top level)."""
    result = view.drop_target(index, indicator)
    if result is None:
        return None
    parent, row = result
    return (parent.data() if parent.isValid() else None), row


def test_drop_targets_of_songs(view):
    view.selectionModel().select(top(view, 0), CLICK)

    assert target(view, top(view, 2), Above) == (None, 2)
    assert target(view, top(view, 2), Below) == (None, 3)
    assert target(view, child(view, 1, 1), Above) == ("G", 1)
    assert target(view, child(view, 1, 1), Below) == ("G", 2)
    assert target(view, top(view, 1), On) == ("G", 2)
    assert target(view, top(view, 1), Above) == (None, 1)
    assert target(view, top(view, 1), Below) == ("G", 0)  # expanded: first song of the group
    assert target(view, top(view, 3), Below) == ("Empty", 0)
    assert target(view, QModelIndex(), OnViewport) == (None, 5)


def test_below_a_collapsed_group_is_after_it(view):
    view.selectionModel().select(top(view, 0), CLICK)
    view.collapse(top(view, 1))

    assert target(view, top(view, 1), Below) == (None, 2)
    assert target(view, top(view, 1), On) == ("G", 2)


def test_drop_targets_of_a_group(view):
    view.selectionModel().select(top(view, 3), CLICK)  # the empty group

    assert target(view, top(view, 0), Above) == (None, 0)
    assert target(view, top(view, 0), Below) == (None, 1)
    assert target(view, top(view, 1), Above) == (None, 1)
    assert target(view, top(view, 1), Below) is None  # between G's header and its first song
    assert target(view, top(view, 1), On) is None  # no nesting
    assert target(view, child(view, 1, 0), Above) is None
    assert target(view, child(view, 1, 1), Below) == (None, 2)  # below G's last song: after G
    assert target(view, top(view, 3), Below) == (None, 4)  # an expanded but empty group
    assert target(view, QModelIndex(), OnViewport) == (None, 5)


# --- Cut and paste --------------------------------------------------------------------------------


@pytest.fixture
def messages(view) -> list[str]:
    collected: list[str] = []
    view.messageRequested.connect(collected.append)
    return collected


def set_current(view: SongTreeView, index: QModelIndex) -> None:
    view.selectionModel().setCurrentIndex(index, SelectionFlag.NoUpdate)


def test_cut_and_paste_songs_above_the_current_song(view, messages):
    selection = view.selectionModel()
    selection.select(top(view, 0), CLICK)
    selection.select(top(view, 4), CTRL_CLICK)
    view.cut_action.trigger()
    set_current(view, child(view, 1, 1))

    view.paste_action.trigger()

    assert tree(view) == [("G", ["B", "A", "E", "C"]), "D", ("Empty", [])]
    assert messages[-1] == "Moved 2 songs."
    view.paste_action.trigger()  # the cut is forgotten after pasting
    assert messages[-1].startswith("Nothing to paste")


def test_paste_songs_on_a_group_header_goes_above_the_group(view):
    view.selectionModel().select(top(view, 4), CLICK)
    view.cut_action.trigger()
    set_current(view, top(view, 3))

    view.paste_action.trigger()

    assert tree(view) == ["A", ("G", ["B", "C"]), "D", "E", ("Empty", [])]


def test_cut_and_paste_a_group_above_the_current_top_level_item(view, messages):
    view.selectionModel().select(top(view, 3), CLICK)
    view.cut_action.trigger()
    set_current(view, child(view, 1, 1))

    view.paste_action.trigger()

    assert tree(view) == ["A", ("Empty", []), ("G", ["B", "C"]), "D", "E"]
    assert messages[-1] == "Moved the group 'Empty'."


def test_paste_without_a_current_row_goes_to_the_end(view):
    view.selectionModel().select(top(view, 0), CLICK)
    view.cut_action.trigger()
    set_current(view, QModelIndex())

    view.paste_action.trigger()

    assert tree(view) == [("G", ["B", "C"]), "D", ("Empty", []), "E", "A"]


def test_cancel_cut(view, messages):
    view.selectionModel().select(top(view, 0), CLICK)
    view.cut_action.trigger()
    assert view.cancel_cut_action.isEnabled()

    view.cancel_cut_action.trigger()
    view.paste_action.trigger()

    assert not view.cancel_cut_action.isEnabled()
    assert messages[-2:] == ["Cut cancelled.", "Nothing to paste: cut songs or a group with Ctrl+X first."]
    assert tree(view)[0] == "A"


def test_cut_with_nothing_selected(view, messages):
    view.cut_action.trigger()

    assert messages == ["Nothing to cut: select songs or a group first."]
