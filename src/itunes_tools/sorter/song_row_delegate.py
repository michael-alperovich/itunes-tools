"""Paints the rows of the song list and turns clicks on their buttons into row actions.

A song row shows the album artwork, the title, ``artist – album``, a speaker icon when the song is
playing, and the song buttons (play, play the last seconds, move to a group). A group row (UC-7) shows an
expand/collapse arrow, the group's name and song count, and its buttons (rename, delete). Clicking a
button or the arrow emits ``SongRowDelegate.rowActionTriggered``.

The view draws no indentation or branch arrows of its own (``QTreeView.setIndentation(0)``), so every
row spans the full width: songs inside and outside groups line up, and the selection highlights the
whole row. That is why group rows paint their own arrow.
"""

from typing import NamedTuple

from PySide6.QtCore import QAbstractItemModel, QEvent, QModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFont, QFontMetrics, QHelpEvent, QIcon, QMouseEvent, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
)

from itunes_tools.common.widgets.icons import text_colored_icon
from itunes_tools.sorter.song_list import (
    ARTWORK_SIZE,
    AlbumRole,
    ArtistRole,
    GroupSongCountRole,
    IsGroupRole,
    IsPlayingRole,
    ModelIndex,
)

SPEAKER_SIZE = 16
ARROW_SIZE = 16
ROW_PADDING = 4
BUTTON_SIZE = 24
BUTTON_SPACING = 4
ROW_HEIGHT = ARTWORK_SIZE + 2 * ROW_PADDING
GROUP_ROW_HEIGHT = BUTTON_SIZE + 2 * ROW_PADDING


class RowAction(NamedTuple):
    """A button shown on every song row or every group row."""

    name: str
    tooltip: str
    icon: QStyle.StandardPixmap | str
    """A standard icon, or a text glyph where the style has no suitable one-colour icon (such as a pencil)."""


PLAY_FROM_START = "play_from_start"
PLAY_LAST_SECONDS = "play_last_seconds"
MOVE_TO_GROUP = "move_to_group"
RENAME_GROUP = "rename_group"
DELETE_GROUP = "delete_group"
TOGGLE_GROUP = "toggle_group"
"""Emitted for a click on a group's arrow; not a button, so not in ``GROUP_ACTIONS``."""

SONG_ACTIONS = (
    RowAction(PLAY_FROM_START, "Play from the beginning", QStyle.StandardPixmap.SP_MediaPlay),
    RowAction(PLAY_LAST_SECONDS, "Play the last 10 seconds", QStyle.StandardPixmap.SP_MediaSeekForward),
    RowAction(MOVE_TO_GROUP, "Move to a group", QStyle.StandardPixmap.SP_ArrowRight),
)

GROUP_ACTIONS = (
    RowAction(RENAME_GROUP, "Rename the group", "✎"),
    RowAction(DELETE_GROUP, "Delete the group; its songs stay in place", QStyle.StandardPixmap.SP_TitleBarCloseButton),
)


def row_actions(index: ModelIndex) -> tuple[RowAction, ...]:
    """Return the buttons of the row at ``index``: group buttons for a group, song buttons for a song."""
    return GROUP_ACTIONS if index.data(IsGroupRole) else SONG_ACTIONS


class SongRowDelegate(QStyledItemDelegate):
    """Paints song rows and group rows with their buttons, and reports button clicks."""

    rowActionTriggered = Signal(str, QModelIndex)
    """A row button was clicked: the ``RowAction`` name and the row's index."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Recolouring icons is too slow to repeat for every painted row, so keep them.
        self._icons: dict[QStyle.StandardPixmap, QIcon] = {}

    def sizeHint(self, option: QStyleOptionViewItem, index: ModelIndex) -> QSize:
        # Width 0: the view stretches each row to its own width, so no horizontal scrolling is needed.
        return QSize(0, GROUP_ROW_HEIGHT if index.data(IsGroupRole) else ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex) -> None:
        style = option.widget.style() if option.widget is not None else QApplication.style()
        painter.save()

        is_group = bool(index.data(IsGroupRole))
        if is_group:
            # A shaded band sets group headers apart from songs; selection and hover are drawn over it.
            painter.fillRect(option.rect, option.palette.color(QPalette.ColorRole.Button))
        # Background, including the hover highlight of the current style.
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)
        if option.state & QStyle.StateFlag.State_Selected:
            # The windows11 style draws no selection for tree view items, so fill the whole row here.
            painter.fillRect(option.rect, option.palette.color(QPalette.ColorRole.Highlight))

        actions = row_actions(index)
        button_rects = self.button_rects(option.rect, len(actions))
        for action, button_rect in zip(actions, button_rects):
            if isinstance(action.icon, str):
                self._paint_glyph(painter, option, action.icon, button_rect)
            else:
                icon = self._icon(style, option.palette, action.icon)
                icon.paint(painter, button_rect, Qt.AlignmentFlag.AlignCenter)

        content = option.rect.adjusted(ROW_PADDING, ROW_PADDING, -ROW_PADDING, -ROW_PADDING)
        if is_group:
            # QTreeView reports an expanded row with State_Open.
            is_expanded = bool(option.state & QStyle.StateFlag.State_Open)
            arrow = QStyle.StandardPixmap.SP_ArrowDown if is_expanded else QStyle.StandardPixmap.SP_ArrowRight
            arrow_rect = self.group_arrow_rect(option.rect)
            self._icon(style, option.palette, arrow).paint(painter, arrow_rect, Qt.AlignmentFlag.AlignCenter)

            text_left = arrow_rect.right() + 1 + ROW_PADDING
            text_right = button_rects[0].left() - 2 * ROW_PADDING
            text_rect = QRect(text_left, content.top(), max(0, text_right - text_left), content.height())
            self._paint_group_text(painter, option, index, text_rect)
        else:
            # The speaker slot left of the buttons is always reserved, so the text does not change its
            # width when a song starts playing.
            speaker_rect = QRect(
                button_rects[0].left() - ROW_PADDING - SPEAKER_SIZE, content.top(), SPEAKER_SIZE, content.height()
            )
            if index.data(IsPlayingRole):
                speaker = self._icon(style, option.palette, QStyle.StandardPixmap.SP_MediaVolume)
                speaker.paint(painter, speaker_rect, Qt.AlignmentFlag.AlignCenter)

            artwork_rect = QRect(content.left(), content.top(), ARTWORK_SIZE, ARTWORK_SIZE)
            self._paint_artwork(painter, index, artwork_rect)

            text_left = artwork_rect.right() + 1 + 2 * ROW_PADDING
            text_right = speaker_rect.left() - 2 * ROW_PADDING
            text_rect = QRect(text_left, content.top(), max(0, text_right - text_left), content.height())
            self._paint_song_text(painter, option, index, text_rect)

        painter.restore()

    @staticmethod
    def _paint_artwork(painter: QPainter, index: ModelIndex, rect: QRect) -> None:
        artwork: QPixmap = index.data(Qt.ItemDataRole.DecorationRole)
        # Center artwork that is not square inside the square slot.
        artwork_target = QRect(0, 0, artwork.width(), artwork.height())
        artwork_target.moveCenter(rect.center())
        painter.drawPixmap(artwork_target, artwork)

    @staticmethod
    def group_arrow_rect(row_rect: QRect) -> QRect:
        """Return the rectangle of a group row's expand/collapse arrow, at the left, vertically centered."""
        top = row_rect.top() + (row_rect.height() - ARROW_SIZE) // 2
        return QRect(row_rect.left() + ROW_PADDING, top, ARROW_SIZE, ARROW_SIZE)

    def _icon(self, style: QStyle, palette: QPalette, standard_pixmap: QStyle.StandardPixmap) -> QIcon:
        """Return a standard icon in the text colour (white on a dark background), created once."""
        icon = self._icons.get(standard_pixmap)
        if icon is None:
            icon = text_colored_icon(style, palette, standard_pixmap)
            self._icons[standard_pixmap] = icon
        return icon

    @classmethod
    def _paint_glyph(cls, painter: QPainter, option: QStyleOptionViewItem, glyph: str, rect: QRect) -> None:
        """Paint a text glyph button, as large as the button allows, in the text colour."""
        cls._set_text_pen(painter, option)
        font = QFont(option.font)
        font.setPixelSize(BUTTON_SIZE - 6)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, glyph)

    @staticmethod
    def button_rects(row_rect: QRect, button_count: int) -> list[QRect]:
        """Return the rectangle of each of ``button_count`` buttons, right-aligned and vertically centered."""
        top = row_rect.top() + (row_rect.height() - BUTTON_SIZE) // 2
        left = row_rect.right() - ROW_PADDING - button_count * (BUTTON_SIZE + BUTTON_SPACING)
        return [
            QRect(left + i * (BUTTON_SIZE + BUTTON_SPACING), top, BUTTON_SIZE, BUTTON_SIZE) for i in range(button_count)
        ]

    def button_at(self, index: ModelIndex, row_rect: QRect, position: QPoint) -> RowAction | None:
        """Return the action of the row at ``index`` whose button contains ``position``, or ``None``."""
        actions = row_actions(index)
        for action, button_rect in zip(actions, self.button_rects(row_rect, len(actions))):
            if button_rect.contains(position):
                return action
        return None

    def editorEvent(
        self,
        event: QEvent,
        model: QAbstractItemModel,
        option: QStyleOptionViewItem,
        index: ModelIndex,
    ) -> bool:
        """Trigger a row action when its button, or a group's arrow, is clicked with the left mouse button.

        Presses on a button or arrow are consumed too, so clicking one does not select the row.
        """
        click_types = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick)
        if event.type() in click_types and isinstance(event, QMouseEvent):
            position = event.position().toPoint()
            action = self.button_at(index, option.rect, position)
            action_name = action.name if action is not None else None
            if index.data(IsGroupRole) and self.group_arrow_rect(option.rect).contains(position):
                action_name = TOGGLE_GROUP
            if action_name is not None and event.button() == Qt.MouseButton.LeftButton:
                if event.type() == QEvent.Type.MouseButtonRelease:
                    # A plain QModelIndex, in case the view passed a persistent one.
                    self.rowActionTriggered.emit(action_name, model.index(index.row(), index.column(), index.parent()))
                return True
        return super().editorEvent(event, model, option, index)

    def helpEvent(
        self,
        event: QHelpEvent,
        view: QAbstractItemView,
        option: QStyleOptionViewItem,
        index: ModelIndex,
    ) -> bool:
        """Show the button's tooltip when hovering a row action button."""
        if event.type() == QHelpEvent.Type.ToolTip:
            action = self.button_at(index, option.rect, event.pos())
            if action is not None:
                QToolTip.showText(event.globalPos(), action.tooltip, view)
                return True
        return super().helpEvent(event, view, option, index)

    @staticmethod
    def _set_text_pen(painter: QPainter, option: QStyleOptionViewItem) -> None:
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        text_role = QPalette.ColorRole.HighlightedText if is_selected else QPalette.ColorRole.Text
        painter.setPen(option.palette.color(text_role))

    @classmethod
    def _paint_song_text(cls, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex, rect: QRect) -> None:
        """Paint the title (bold) above ``artist – album``, each elided to fit ``rect``."""
        cls._set_text_pen(painter, option)

        title_font = QFont(option.font)
        title_font.setBold(True)
        title_rect = QRect(rect.left(), rect.top(), rect.width(), rect.height() // 2)
        details_rect = QRect(rect.left(), title_rect.bottom() + 1, rect.width(), rect.height() - title_rect.height())

        title = index.data(Qt.ItemDataRole.DisplayRole)
        painter.setFont(title_font)
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
            QFontMetrics(title_font).elidedText(title, Qt.TextElideMode.ElideRight, rect.width()),
        )

        details = f"{index.data(ArtistRole)} – {index.data(AlbumRole)}"
        painter.setFont(option.font)
        painter.drawText(
            details_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            QFontMetrics(option.font).elidedText(details, Qt.TextElideMode.ElideRight, rect.width()),
        )

    @classmethod
    def _paint_group_text(cls, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex, rect: QRect) -> None:
        """Paint ``<name> (<n> songs)`` in bold, elided to fit ``rect``."""
        cls._set_text_pen(painter, option)
        font = QFont(option.font)
        font.setBold(True)
        song_count = index.data(GroupSongCountRole)
        text = f"{index.data(Qt.ItemDataRole.DisplayRole)} ({song_count} {'song' if song_count == 1 else 'songs'})"
        painter.setFont(font)
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, rect.width()),
        )
