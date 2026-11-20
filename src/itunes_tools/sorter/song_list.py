"""The song list: a Qt model holding the songs in sorting order, and a delegate that paints each row.

Each row shows a speaker icon when the song is playing, the album artwork, the title,
``artist – album``, and the per-song action buttons. Clicking an enabled button emits
``SongRowDelegate.rowActionTriggered``; *Send to a group* stays disabled until UC-7 (groups).

Model/view is used instead of one widget per row (``QListWidget.setItemWidget``) because it scales to
large playlists and supports drag and drop (UC-8) and groups (UC-7).
"""

from typing import Any, NamedTuple

from PySide6.QtCore import (
    QAbstractItemModel,
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QPersistentModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QFont, QFontMetrics, QHelpEvent, QIcon, QMouseEvent, QPainter, QPalette, QPixmap
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
from itunes_tools.common.widgets.artwork import load_artwork_pixmap
from itunes_tools.common.widgets.icons import text_colored_icon

SPEAKER_SIZE = 16
ARTWORK_SIZE = 48
ROW_PADDING = 4
BUTTON_SIZE = 24
BUTTON_SPACING = 4
ROW_HEIGHT = ARTWORK_SIZE + 2 * ROW_PADDING

# The model's custom data roles, next to Qt's DisplayRole (title) and DecorationRole (artwork).
ArtistRole = Qt.ItemDataRole.UserRole + 1
AlbumRole = Qt.ItemDataRole.UserRole + 2
SongRole = Qt.ItemDataRole.UserRole + 3
IsPlayingRole = Qt.ItemDataRole.UserRole + 4

ModelIndex = QModelIndex | QPersistentModelIndex


class RowAction(NamedTuple):
    """A button shown on every song row."""

    name: str
    tooltip: str
    icon: QStyle.StandardPixmap
    enabled: bool


PLAY_FROM_START = "play_from_start"
PLAY_LAST_SECONDS = "play_last_seconds"
SEND_TO_GROUP = "send_to_group"

ROW_ACTIONS = (
    RowAction(PLAY_FROM_START, "Play from the beginning", QStyle.StandardPixmap.SP_MediaPlay, True),
    RowAction(PLAY_LAST_SECONDS, "Play the last 10 seconds", QStyle.StandardPixmap.SP_MediaSeekForward, True),
    RowAction(SEND_TO_GROUP, "Send to a group (coming soon)", QStyle.StandardPixmap.SP_ArrowRight, False),
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
        self._playing_song_id: ItunesPersistentID | None = None

    def set_songs(self, songs: list[Song]) -> None:
        """Replace all songs. Views are told to reload everything."""
        self.beginResetModel()
        self._songs = list(songs)
        self._artwork_pixmaps.clear()
        self.endResetModel()

    def set_playing_song(self, song_id: ItunesPersistentID | None) -> None:
        """Mark the song shown as playing (``IsPlayingRole``), or none. Only the affected rows repaint."""
        old_row = self.playing_row()
        self._playing_song_id = song_id
        new_row = self.playing_row()
        for row in {old_row, new_row} - {None}:
            index = self.index(row)
            self.dataChanged.emit(index, index, [IsPlayingRole])

    def playing_row(self) -> int | None:
        """Return the row of the song marked as playing, or ``None`` if there is none in the list."""
        if self._playing_song_id is None:
            return None
        for row, song in enumerate(self._songs):
            if song.id == self._playing_song_id:
                return row
        return None

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
        if role == IsPlayingRole:
            return song.id == self._playing_song_id
        return None

    def _artwork_pixmap(self, song: Song) -> QPixmap:
        """Return the song's artwork scaled for a row, or an empty placeholder when there is none."""
        pixmap = self._artwork_pixmaps.get(song.id)
        if pixmap is None:
            pixmap = load_artwork_pixmap(self._artwork_cache, song, ARTWORK_SIZE)
            self._artwork_pixmaps[song.id] = pixmap
        return pixmap


class SongRowDelegate(QStyledItemDelegate):
    """Paints a song row: playing speaker, artwork, title, ``artist – album`` and the row action buttons."""

    rowActionTriggered = Signal(str, QModelIndex)
    """An enabled row button was clicked: the ``RowAction`` name and the row's index."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Recolouring icons is too slow to repeat for every painted row, so keep them.
        self._icons: dict[QStyle.StandardPixmap, QIcon] = {}

    def sizeHint(self, option: QStyleOptionViewItem, index: ModelIndex) -> QSize:
        # Width 0: the list view stretches each row to its own width, so no horizontal scrolling is needed.
        return QSize(0, ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex) -> None:
        style = option.widget.style() if option.widget is not None else QApplication.style()
        painter.save()

        # Background, including the selection and hover highlight of the current style.
        style.drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, option.widget)

        content = option.rect.adjusted(ROW_PADDING, ROW_PADDING, -ROW_PADDING, -ROW_PADDING)
        # The speaker column is always reserved, so the artwork does not move when a song starts playing.
        speaker_rect = QRect(content.left(), content.top(), SPEAKER_SIZE, content.height())
        if index.data(IsPlayingRole):
            speaker = self._icon(style, option.palette, QStyle.StandardPixmap.SP_MediaVolume)
            speaker.paint(painter, speaker_rect, Qt.AlignmentFlag.AlignCenter)

        artwork_rect = QRect(speaker_rect.right() + 1 + ROW_PADDING, content.top(), ARTWORK_SIZE, ARTWORK_SIZE)
        artwork: QPixmap = index.data(Qt.ItemDataRole.DecorationRole)
        # Center artwork that is not square inside the square slot.
        artwork_target = QRect(0, 0, artwork.width(), artwork.height())
        artwork_target.moveCenter(artwork_rect.center())
        painter.drawPixmap(artwork_target, artwork)

        button_rects = self.button_rects(option.rect)
        for action, button_rect in zip(ROW_ACTIONS, button_rects):
            mode = QIcon.Mode.Normal if action.enabled else QIcon.Mode.Disabled
            icon = self._icon(style, option.palette, action.icon)
            icon.paint(painter, button_rect, Qt.AlignmentFlag.AlignCenter, mode)

        text_left = artwork_rect.right() + 1 + 2 * ROW_PADDING
        text_right = button_rects[0].left() - 2 * ROW_PADDING
        text_rect = QRect(text_left, content.top(), max(0, text_right - text_left), content.height())
        self._paint_text(painter, option, index, text_rect)

        painter.restore()

    def _icon(self, style: QStyle, palette: QPalette, standard_pixmap: QStyle.StandardPixmap) -> QIcon:
        """Return a standard icon in the text colour (white on a dark background), created once."""
        icon = self._icons.get(standard_pixmap)
        if icon is None:
            icon = text_colored_icon(style, palette, standard_pixmap)
            self._icons[standard_pixmap] = icon
        return icon

    def button_rects(self, row_rect: QRect) -> list[QRect]:
        """Return the rectangle of each ``ROW_ACTIONS`` button, right-aligned and vertically centered."""
        top = row_rect.top() + (row_rect.height() - BUTTON_SIZE) // 2
        left = row_rect.right() - ROW_PADDING - len(ROW_ACTIONS) * (BUTTON_SIZE + BUTTON_SPACING)
        return [
            QRect(left + i * (BUTTON_SIZE + BUTTON_SPACING), top, BUTTON_SIZE, BUTTON_SIZE)
            for i in range(len(ROW_ACTIONS))
        ]

    def button_at(self, row_rect: QRect, position: QPoint) -> RowAction | None:
        """Return the row action whose button contains ``position``, or ``None``."""
        for action, button_rect in zip(ROW_ACTIONS, self.button_rects(row_rect)):
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
        """Trigger a row action when its enabled button is clicked with the left mouse button.

        Presses on an enabled button are consumed too, so clicking a button does not select the row.
        """
        click_types = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick)
        if event.type() in click_types and isinstance(event, QMouseEvent):
            action = self.button_at(option.rect, event.position().toPoint())
            if action is not None and action.enabled and event.button() == Qt.MouseButton.LeftButton:
                if event.type() == QEvent.Type.MouseButtonRelease:
                    self.rowActionTriggered.emit(action.name, model.index(index.row(), index.column()))
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
            action = self.button_at(option.rect, event.pos())
            if action is not None:
                QToolTip.showText(event.globalPos(), action.tooltip, view)
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
