"""The view of the song list: selection, drag and drop, and cut and paste of songs and groups (UC-8).

Selection follows the usual rules (click, Shift+click for a range, Ctrl+click to toggle), with one
restriction kept by ``SongSelectionModel``: **only songs are multi-selected**. A plain click selects a
group on its own; a group never joins a selection of several rows. So the selection is either one
group or one or more songs, and that is what a drag or a cut moves.

Dropped and pasted rows are moved by ``SongListModel.move_items``, in playlist order; groups go to the
top level only, since groups are never nested. Where a drop lands is decided by ``drop_target``.
"""

from PySide6.QtCore import (
    QItemSelection,
    QItemSelectionModel,
    QItemSelectionRange,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QDragMoveEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import QAbstractItemView, QTreeView, QWidget

from itunes_tools.sorter.song_list import IsGroupRole, ModelIndex, SongListModel
from itunes_tools.sorter.song_row_delegate import SongRowDelegate

# How long a collapsed group must be hovered during a drag before it expands, in milliseconds.
AUTO_EXPAND_DELAY = 700

DropIndicator = QAbstractItemView.DropIndicatorPosition
SelectionFlag = QItemSelectionModel.SelectionFlag


class SongTreeView(QTreeView):
    """Shows a ``SongListModel``: rows painted by ``SongRowDelegate``, songs and groups moved by drag and drop
    or by cut (Ctrl+X) and paste (Ctrl+V)."""

    messageRequested = Signal(str)
    """A message for the user, such as what was cut or pasted."""

    def __init__(self, model: SongListModel, parent: QWidget | None = None):
        super().__init__(parent)
        self.setModel(model)
        # The view created a plain selection model in setModel; replace it with the songs-only one.
        default_selection_model = self.selectionModel()
        self.setSelectionModel(SongSelectionModel(model, self))
        default_selection_model.deleteLater()

        self.setHeaderHidden(True)  # one column, nothing to label
        # No indentation or branch arrows: rows span the full width, so the selection fills the whole row.
        # SongRowDelegate paints the group arrows and indents the content of songs inside groups instead.
        self.setIndentation(0)
        self.setRootIsDecorated(False)
        self.row_delegate = SongRowDelegate(self)
        self.setItemDelegate(self.row_delegate)
        self.setMouseTracking(True)  # hover highlight

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
        self.setAutoExpandDelay(AUTO_EXPAND_DELAY)
        # Hidden songs of a collapsed group would otherwise be dragged or cut along unseen.
        self.collapsed.connect(self._deselect_songs_of_group)

        # The rows remembered by Cut until they are pasted. Persistent, so they follow other changes.
        self._cut_rows: list[QPersistentModelIndex] = []
        self.cut_action = self._add_shortcut_action("Cut", QKeySequence.StandardKey.Cut, self._on_cut_triggered)
        self.paste_action = self._add_shortcut_action("Paste", QKeySequence.StandardKey.Paste, self._on_paste_triggered)
        self.cancel_cut_action = self._add_shortcut_action(
            "Cancel cut", QKeySequence(Qt.Key.Key_Escape), self._on_cancel_cut_triggered
        )
        self.cancel_cut_action.setEnabled(False)  # only while something is cut, so Esc stays free otherwise

    def model(self) -> SongListModel:
        model = super().model()
        assert isinstance(model, SongListModel)
        return model

    def _add_shortcut_action(self, text: str, shortcut: QKeySequence | QKeySequence.StandardKey, slot) -> QAction:
        """Add an action triggered by ``shortcut`` while the list (not the toolbar or the player) has focus."""
        action = QAction(text, self)
        action.setShortcut(shortcut)
        action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        action.triggered.connect(slot)
        self.addAction(action)
        return action

    # --- Selection ----------------------------------------------------------------------------------

    def selected_rows(self) -> list[QModelIndex]:
        """Return the selected rows: one group, or songs."""
        return self.selectionModel().selectedRows()

    def selected_songs_for(self, index: ModelIndex) -> list[QModelIndex]:
        """Return the rows a row button of ``index`` acts on: the selection if ``index`` is in it, else ``index``."""
        selected = self.selected_rows()
        if any(row == index for row in selected):
            return selected
        return [QModelIndex(index)]

    @Slot(QModelIndex)
    def _deselect_songs_of_group(self, group_index: QModelIndex) -> None:
        song_count = self.model().rowCount(group_index)
        if song_count:
            songs = QItemSelection(
                self.model().index(0, 0, group_index), self.model().index(song_count - 1, 0, group_index)
            )
            self.selectionModel().select(songs, SelectionFlag.Deselect | SelectionFlag.Rows)

    # --- Drag and drop ------------------------------------------------------------------------------

    def drop_target(self, index: ModelIndex, indicator: DropIndicator) -> tuple[QModelIndex, int] | None:
        """Return where dragged rows land, as ``(parent, row to insert before)``, or ``None`` where they may not.

        :param index: The row under the mouse (invalid below the last row).
        :param indicator: Where the mouse is relative to that row, as Qt's drop indicator shows it.

        The dragged rows are the selection: songs, or one group.

        - Songs dropped above or below a row join that row's level (the top level or its group).
          Dropped onto a group row they are appended to the group; just below an expanded group's
          header they become its first songs.
        - A group lands at the top level only. Below a group's last song means after that group;
          other places inside a group, and onto a row, are refused.
        - Below the last row means the end of the list.
        """
        model = self.model()
        if not index.isValid() or indicator == DropIndicator.OnViewport:
            return QModelIndex(), model.rowCount()
        index = QModelIndex(index)
        parent = index.parent()
        is_group = bool(index.data(IsGroupRole))
        # A group's header is followed by its songs when expanded, so "below" it is inside the group.
        below_opens_group = is_group and self.isExpanded(index) and model.rowCount(index) > 0

        if self._dragging_group():
            if parent.isValid():
                if indicator == DropIndicator.BelowItem and index.row() == model.rowCount(parent) - 1:
                    return QModelIndex(), parent.row() + 1
                return None
            if indicator == DropIndicator.AboveItem:
                return QModelIndex(), index.row()
            if indicator == DropIndicator.BelowItem and not below_opens_group:
                return QModelIndex(), index.row() + 1
            return None

        if indicator == DropIndicator.OnItem:  # only groups accept drops onto them (SongListModel.flags)
            return index, model.rowCount(index)
        if indicator == DropIndicator.AboveItem:
            return parent, index.row()
        if is_group and self.isExpanded(index):
            return index, 0
        return parent, index.row() + 1

    def _dragging_group(self) -> bool:
        return any(row.data(IsGroupRole) for row in self.selected_rows())

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Let Qt place the drop indicator, then refuse places where the dragged rows may not land."""
        super().dragMoveEvent(event)
        if event.isAccepted() and self._event_drop_target(event) is None:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Move the selection to the drop place.

        The rows are moved here, not removed and inserted by Qt: Qt's drag code removes the dragged rows
        after a ``MoveAction``, so the drop reports ``IgnoreAction`` instead.
        """
        target = self._event_drop_target(event) if event.source() is self else None
        if target is None:
            event.ignore()
        else:
            target_parent, target_row = target
            self.model().move_items(self.selected_rows(), target_parent, target_row)
            event.setDropAction(Qt.DropAction.IgnoreAction)
            event.accept()
        # What QAbstractItemView.dropEvent does at the end of every drop.
        self.stopAutoScroll()
        self.setState(QAbstractItemView.State.NoState)
        self.viewport().update()

    def _event_drop_target(self, event: QDropEvent) -> tuple[QModelIndex, int] | None:
        return self.drop_target(self.indexAt(event.position().toPoint()), self.dropIndicatorPosition())

    # --- Cut and paste ------------------------------------------------------------------------------

    def paste_target(self, current: ModelIndex, pasting_group: bool) -> tuple[QModelIndex, int]:
        """Return where pasted rows go, as ``(parent, row to insert before)``: above the ``current`` row.

        Songs go above the current song, inside its group if it is in one, or above the current group's
        header at the top level. A group goes above the current row's top-level item. With no current
        row, both go to the end of the list.
        """
        model = self.model()
        if not current.isValid():
            return QModelIndex(), model.rowCount()
        if pasting_group:
            return QModelIndex(), model.top_level_row(current)
        current = QModelIndex(current)
        return current.parent(), current.row()

    @Slot()
    def _on_cut_triggered(self) -> None:
        rows = self.selected_rows()
        if not rows:
            self.messageRequested.emit("Nothing to cut: select songs or a group first.")
            return
        self._cut_rows = [QPersistentModelIndex(row) for row in rows]
        self.cancel_cut_action.setEnabled(True)
        self.messageRequested.emit(
            f"Cut {_describe(rows)}. Select a row and press Ctrl+V to move it above that row; Esc cancels."
        )

    @Slot()
    def _on_paste_triggered(self) -> None:
        # A cut group may have been deleted since.
        rows = [QModelIndex(row) for row in self._cut_rows if row.isValid()]
        if not rows:
            self.messageRequested.emit("Nothing to paste: cut songs or a group with Ctrl+X first.")
            return
        pasting_group = any(row.data(IsGroupRole) for row in rows)
        target_parent, target_row = self.paste_target(self.currentIndex(), pasting_group)
        description = _describe(rows)
        self.model().move_items(rows, target_parent, target_row)
        self._forget_cut()
        self.messageRequested.emit(f"Moved {description}.")

    @Slot()
    def _on_cancel_cut_triggered(self) -> None:
        self._forget_cut()
        self.messageRequested.emit("Cut cancelled.")

    def _forget_cut(self) -> None:
        self._cut_rows = []
        self.cancel_cut_action.setEnabled(False)


class SongSelectionModel(QItemSelectionModel):
    """A selection model that multi-selects songs only.

    Every selection change of the view passes through ``select``. Group rows are taken out of any
    selection that adds rows, except a group selected on its own while the old selection is cleared (a
    plain click). Adding songs to a selected group replaces the group. Deselecting is never changed.
    """

    def select(self, selection, command) -> None:  # type: ignore[override]  # covers both C++ overloads
        command = SelectionFlag(command)
        if isinstance(selection, (QModelIndex, QPersistentModelIndex)):
            index = QModelIndex(selection)
            selection = QItemSelection(index, index) if index.isValid() else QItemSelection()

        if not command & (SelectionFlag.Select | SelectionFlag.Toggle):
            super().select(selection, command)
            return

        songs = _without_groups(selection)
        if songs.isEmpty() and len(selection.indexes()) == 1:
            # A group alone: selected by a plain click, ignored by Ctrl+click or Shift+click.
            if command & SelectionFlag.Clear:
                super().select(selection, command)
            return
        if any(index.data(IsGroupRole) for index in self.selectedIndexes()):
            command |= SelectionFlag.Clear  # songs replace a selected group
        super().select(songs, command)


def _without_groups(selection: QItemSelection) -> QItemSelection:
    """Return ``selection`` without group rows, splitting ranges around them.

    Groups are top-level rows only, so only ranges at the top level need checking.
    """
    result = QItemSelection()
    for selection_range in selection:
        if selection_range.parent().isValid():
            result.append(selection_range)
            continue
        model = selection_range.model()
        run_start: int | None = None
        for row in range(selection_range.top(), selection_range.bottom() + 2):
            is_song = row <= selection_range.bottom() and not model.index(row, 0).data(IsGroupRole)
            if is_song and run_start is None:
                run_start = row
            elif not is_song and run_start is not None:
                result.append(
                    QItemSelectionRange(
                        model.index(run_start, selection_range.left()), model.index(row - 1, selection_range.right())
                    )
                )
                run_start = None
    return result


def _describe(rows: list[QModelIndex]) -> str:
    """Return ``the group 'X'`` or ``N songs`` for rows of a selection."""
    if len(rows) == 1 and rows[0].data(IsGroupRole):
        return f"the group {rows[0].data()!r}"
    return f"{len(rows)} {'song' if len(rows) == 1 else 'songs'}"
