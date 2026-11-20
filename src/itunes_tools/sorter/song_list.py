"""The song list: a Qt model holding the songs in sorting order, and a delegate that paints each row.

Each row shows the album artwork, the title, ``artist – album``, and the per-song action buttons.
The buttons are only painted for now (disabled); clicking them is handled once UC-6 (quick play) and
UC-7 (groups) are implemented, through ``SongRowDelegate.button_rects`` and ``editorEvent``.

Model/view is used instead of one widget per row (``QListWidget.setItemWidget``) because it scales to
large playlists and supports drag and drop (UC-8) and groups (UC-7).
"""

from typing import Any, NamedTuple

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPersistentModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QHelpEvent, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
)

from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.common.models import ItunesPersistentID, Song

ARTWORK_SIZE = 48
ROW_PADDING = 4
BUTTON_SIZE = 24
BUTTON_SPACING = 4
ROW_HEIGHT = ARTWORK_SIZE + 2 * ROW_PADDING

# The model's custom data roles, next to Qt's DisplayRole (title) and DecorationRole (artwork).
ArtistRole = Qt.ItemDataRole.UserRole + 1
AlbumRole = Qt.ItemDataRole.UserRole + 2
SongRole = Qt.ItemDataRole.UserRole + 3

ModelIndex = QModelIndex | QPersistentModelIndex


class RowAction(NamedTuple):
    """A button shown on every song row."""

    name: str
    tooltip: str
    icon: QStyle.StandardPixmap


ROW_ACTIONS = (
    RowAction("play_from_start", "Play from the beginning", QStyle.StandardPixmap.SP_MediaPlay),
    RowAction("play_last_seconds", "Play the last 10 seconds", QStyle.StandardPixmap.SP_MediaSeekForward),
    RowAction("send_to_group", "Send to a group", QStyle.StandardPixmap.SP_ArrowRight),
)


class SongListModel(QAbstractListModel):
    """The songs being sorted, in sorting order.

    Artwork comes from the ``ArtworkCache`` (never from iTunes) and is loaded the first time a row
    asks for it, then kept as a scaled ``QPixmap``.
    """

    def __init__(self, artwork_cache: ArtworkCache, parent=None):
        super().__init__(parent)
        self._artwork_cache = artwork_cache
        self._songs: list[Song] = []
        self._artwork_pixmaps: dict[ItunesPersistentID, QPixmap] = {}

    def set_songs(self, songs: list[Song]) -> None:
        """Replace all songs. Views are told to reload everything."""
        self.beginResetModel()
        self._songs = list(songs)
        self._artwork_pixmaps.clear()
        self.endResetModel()

    def songs(self) -> list[Song]:
        """Return the songs in sorting order (a copy)."""
        return list(self._songs)

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:
        # A list model has rows only at the top level; Qt asks for children of each row too.
        if parent.isValid():
            return 0
        return len(self._songs)

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._songs):
            return None
        song = self._songs[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return song.name
        if role == Qt.ItemDataRole.DecorationRole:
            return self._artwork_pixmap(song)
        if role == ArtistRole:
            return song.artist
        if role == AlbumRole:
            return song.album
        if role == SongRole:
            return song
        return None

    def _artwork_pixmap(self, song: Song) -> QPixmap:
        """Return the song's artwork scaled for a row, or an empty placeholder when there is none."""
        pixmap = self._artwork_pixmaps.get(song.id)
        if pixmap is None:
            path = self._artwork_cache.get_path(song)
            pixmap = QPixmap(str(path)) if path is not None else QPixmap()
            if pixmap.isNull():  # no artwork, not cached yet, or an unreadable file
                pixmap = QPixmap(ARTWORK_SIZE, ARTWORK_SIZE)
                pixmap.fill(QColor("lightgray"))
            else:
                pixmap = pixmap.scaled(
                    ARTWORK_SIZE,
                    ARTWORK_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            self._artwork_pixmaps[song.id] = pixmap
        return pixmap


class SongRowDelegate(QStyledItemDelegate):
    """Paints a song row: artwork, title, ``artist – album`` and the row action buttons."""

    def sizeHint(self, option: QStyleOptionViewItem, index: ModelIndex) -> QSize:
        # Width 0: the list view stretches each row to its own width, so no horizontal scrolling is needed.
        return QSize(0, ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex) -> None:
        style = option.widget.style() if option.widget is not None else QApplication.style()
        painter.save()

        # Background, including the selection and hover highlight of the current style.
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)

        content = option.rect.adjusted(ROW_PADDING, ROW_PADDING, -ROW_PADDING, -ROW_PADDING)
        artwork_rect = QRect(content.left(), content.top(), ARTWORK_SIZE, ARTWORK_SIZE)
        artwork: QPixmap = index.data(Qt.ItemDataRole.DecorationRole)
        # Center artwork that is not square inside the square slot.
        artwork_target = QRect(0, 0, artwork.width(), artwork.height())
        artwork_target.moveCenter(artwork_rect.center())
        painter.drawPixmap(artwork_target, artwork)

        button_rects = self.button_rects(option.rect)
        for action, button_rect in zip(ROW_ACTIONS, button_rects):
            # Disabled until the actions are implemented (UC-6, UC-7).
            icon = style.standardIcon(action.icon)
            icon.paint(painter, button_rect, Qt.AlignmentFlag.AlignCenter, QIcon.Mode.Disabled)

        text_left = artwork_rect.right() + 1 + 2 * ROW_PADDING
        text_right = button_rects[0].left() - 2 * ROW_PADDING
        text_rect = QRect(text_left, content.top(), max(0, text_right - text_left), content.height())
        self._paint_text(painter, option, index, text_rect)

        painter.restore()

    def button_rects(self, row_rect: QRect) -> list[QRect]:
        """Return the rectangle of each ``ROW_ACTIONS`` button, right-aligned and vertically centered."""
        top = row_rect.top() + (row_rect.height() - BUTTON_SIZE) // 2
        left = row_rect.right() - ROW_PADDING - len(ROW_ACTIONS) * (BUTTON_SIZE + BUTTON_SPACING)
        return [
            QRect(left + i * (BUTTON_SIZE + BUTTON_SPACING), top, BUTTON_SIZE, BUTTON_SIZE)
            for i in range(len(ROW_ACTIONS))
        ]

    def helpEvent(
        self,
        event: QHelpEvent,
        view: QAbstractItemView,
        option: QStyleOptionViewItem,
        index: ModelIndex,
    ) -> bool:
        """Show the button's tooltip when hovering a row action button."""
        if event.type() == QHelpEvent.Type.ToolTip:
            for action, button_rect in zip(ROW_ACTIONS, self.button_rects(option.rect)):
                if button_rect.contains(event.pos()):
                    QToolTip.showText(event.globalPos(), f"{action.tooltip} (coming soon)", view)
                    return True
        return super().helpEvent(event, view, option, index)

    @staticmethod
    def _paint_text(painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex, rect: QRect) -> None:
        """Paint the title (bold) above ``artist – album``, each elided to fit ``rect``."""
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        text_role = QPalette.ColorRole.HighlightedText if is_selected else QPalette.ColorRole.Text
        painter.setPen(option.palette.color(text_role))

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
