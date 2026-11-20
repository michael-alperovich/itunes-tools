"""The song list: a Qt tree model holding the sorting list, top-level songs and groups of songs (UC-7).

The tree has two levels. Top-level rows are songs or groups; a group's children are its songs, and
groups are never nested. Reading the tree top to bottom, with every group's songs in place (also when
the group is collapsed in the view), gives the true playlist order: ``songs()`` and the *flat
positions* used by playback.

Songs and groups change place through ``move_items`` (UC-8), which drag and drop, cut and paste and
*Move to group* all use.

Model/view is used instead of one widget per row (``QListWidget.setItemWidget``) because it scales to
large playlists and supports groups and drag and drop. ``SongRowDelegate`` paints the rows and
``SongTreeView`` shows them.
"""

from typing import Any

from PySide6.QtCore import QAbstractItemModel, QByteArray, QMimeData, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QPixmap

from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.common.models import ItunesPersistentID, Song
from itunes_tools.common.widgets.artwork import load_artwork_pixmap
from itunes_tools.sorter.sorting_items import SongGroup, SortingItem, flatten

ARTWORK_SIZE = 48

# The model's custom data roles, next to Qt's DisplayRole (song title or group name) and
# DecorationRole (song artwork).
ArtistRole = Qt.ItemDataRole.UserRole + 1
AlbumRole = Qt.ItemDataRole.UserRole + 2
SongRole = Qt.ItemDataRole.UserRole + 3
IsPlayingRole = Qt.ItemDataRole.UserRole + 4
IsGroupRole = Qt.ItemDataRole.UserRole + 5
GroupSongCountRole = Qt.ItemDataRole.UserRole + 6

ModelIndex = QModelIndex | QPersistentModelIndex

# ``internalId`` of a top-level index. A song inside a group carries its group's key instead.
TOP_LEVEL_ID = 0

# The drag data format of rows dragged within the song list.
ROWS_MIME_TYPE = "application/x-itunes-tools-rows"


class SongListModel(QAbstractItemModel):
    """The sorting list: songs and groups of songs, in sorting order.

    Each index records its parent in ``internalId``: ``TOP_LEVEL_ID`` for top-level rows, or the key of
    the group holding the song. A group's key is the identity (``id()``) of its ``SongGroup`` object,
    which the model owns and changes in place, so the key stays valid while rows above the group are
    inserted or removed; a key made from the group's row would point at another group after such a
    change, breaking the view's selection and current index.

    Artwork comes from the ``ArtworkCache`` (never from iTunes) and is loaded the first time a row
    asks for it, then kept as a scaled ``QPixmap``.
    """

    def __init__(self, artwork_cache: ArtworkCache, parent=None):
        super().__init__(parent)
        self._artwork_cache = artwork_cache
        self._items: list[SortingItem] = []
        # Top-level row of each group, by group key; rebuilt after every change of the top level.
        self._group_rows: dict[int, int] = {}
        self._artwork_pixmaps: dict[ItunesPersistentID, QPixmap] = {}
        self._playing_song_id: ItunesPersistentID | None = None

    # --- Content ------------------------------------------------------------------------------------

    def set_items(self, items: list[SortingItem]) -> None:
        """Replace the whole sorting list. Views are told to reload everything."""
        self.beginResetModel()
        # Own copies of the groups: the model changes them in place.
        self._items = [_copy_item(item) for item in items]
        self._update_group_rows()
        self._artwork_pixmaps.clear()
        self.endResetModel()

    def items(self) -> list[SortingItem]:
        """Return the sorting list (a copy; changing it does not change the model)."""
        return [_copy_item(item) for item in self._items]

    def songs(self) -> list[Song]:
        """Return every song in the true playlist order, group contents in place."""
        return flatten(self._items)

    def group_names(self) -> list[str]:
        """Return the names of all groups, top to bottom."""
        return [item.name for item in self._items if isinstance(item, SongGroup)]

    def group_row(self, name: str) -> int | None:
        """Return the top-level row of the group called ``name``, or ``None`` if there is none."""
        for row, item in enumerate(self._items):
            if isinstance(item, SongGroup) and item.name == name:
                return row
        return None

    def top_level_row(self, index: ModelIndex) -> int:
        """Return the top-level row holding ``index``: its own row, or its group's row for a song in a group.

        An invalid index (nothing current in the view) gives the row after the last one.
        """
        if not index.isValid():
            return len(self._items)
        if index.internalId() == TOP_LEVEL_ID:
            return index.row()
        return self._group_rows[index.internalId()]

    # --- Changing groups ----------------------------------------------------------------------------

    def insert_groups(self, top_row: int, names: list[str]) -> None:
        """Insert empty groups called ``names`` at ``top_row`` of the top level, in the given order.

        The caller makes sure that the names are not taken.
        """
        if not names:
            return
        self.beginInsertRows(QModelIndex(), top_row, top_row + len(names) - 1)
        self._items[top_row:top_row] = [SongGroup(name=name) for name in names]
        self._update_group_rows()
        self.endInsertRows()

    def rename_group(self, top_row: int, name: str) -> None:
        """Rename the group at ``top_row``. The caller makes sure that the name is not taken."""
        self._group_at(top_row).name = name
        index = self.index(top_row, 0)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])

    def delete_group(self, top_row: int) -> None:
        """Delete the group at ``top_row``; its songs take its place at the top level, in their order.

        The songs are moved, not removed and re-inserted, so a selected or playing song stays so.
        """
        group = self._group_at(top_row)
        song_count = len(group.songs)
        if song_count:
            self.beginMoveRows(self.index(top_row, 0), 0, song_count - 1, QModelIndex(), top_row + 1)
            self._items[top_row + 1 : top_row + 1] = group.songs
            group.songs = []
            self._update_group_rows()
            self.endMoveRows()

        self.beginRemoveRows(QModelIndex(), top_row, top_row)
        del self._items[top_row]
        self._update_group_rows()
        self.endRemoveRows()

    # --- Moving songs and groups (UC-8) -------------------------------------------------------------

    def move_items(self, indexes: list[ModelIndex], target_parent: ModelIndex, target_row: int) -> int:
        """Move the rows at ``indexes`` so that they stand together, in playlist order, before ``target_row``.

        This one method serves drag and drop, cut and paste, and *Move to group*.

        :param indexes: Songs (anywhere, in any order), or exactly one group.
        :param target_parent: A group, or an invalid index for the top level. Groups move only to the top
            level, since groups are never nested.
        :param target_row: The row of ``target_parent`` to insert before, counted before the move;
            ``rowCount(target_parent)`` appends.
        :return: How many rows actually moved; rows that already stand at their place are not moved.
        :raises ValueError: For a group together with other rows, or a group moved into a group.

        Rows move one at a time with ``beginMoveRows``, so persistent indexes (the view's selection and
        current row) follow them.
        """
        sources = self._sorted_sources(indexes)
        self._check_move(sources, target_parent)
        if not sources:
            return 0

        # The target group's row can change while top-level songs above it move, so keep the object.
        target_group = self._group_at(target_parent.row()) if target_parent.isValid() else None
        # Groups whose song count may change, by identity (equal groups compare equal as Pydantic models).
        touched_groups: dict[int, SongGroup] = {} if target_group is None else {id(target_group): target_group}
        # Moved rows that already stand right above the insertion point stay; the others go in front of
        # them. Without this, moving rows to where they already are would shuffle them around.
        target_source_rows = {source.row() for source in sources if source.parent() == target_parent}
        insert_row = target_row
        while insert_row - 1 in target_source_rows:
            insert_row -= 1

        moved_count = 0
        for source in sources:
            source_parent = QModelIndex(source.parent())
            source_row = source.row()
            source_group = self._group_at(source_parent.row()) if source_parent.isValid() else None
            same_parent = source_group is target_group
            # A row standing at the insertion point stays and the insertion point moves past it; Qt
            # refuses such no-op moves anyway.
            if same_parent and source_row == insert_row:
                insert_row += 1
                continue

            target_parent_index = self._index_of_group(target_group)
            if not self.beginMoveRows(source_parent, source_row, source_row, target_parent_index, insert_row):
                raise AssertionError(f"Qt refused to move row {source_row} to row {insert_row}")
            source_list = source_group.songs if source_group is not None else self._items
            target_list = target_group.songs if target_group is not None else self._items
            item = source_list.pop(source_row)
            if same_parent and source_row < insert_row:
                # Taking the row out shifted the insertion point up by one.
                target_list.insert(insert_row - 1, item)
            else:
                target_list.insert(insert_row, item)
                insert_row += 1
            self._update_group_rows()
            self.endMoveRows()

            moved_count += 1
            if source_group is not None:
                touched_groups[id(source_group)] = source_group

        if moved_count:
            # The song counts shown on the group rows may have changed.
            for group in touched_groups.values():
                self._emit_song_count_changed(group)
        return moved_count

    def _sorted_sources(self, indexes: list[ModelIndex]) -> list[QPersistentModelIndex]:
        """Return the valid ``indexes`` without duplicates, in playlist order, as persistent indexes."""
        unique: dict[tuple[int, int], QPersistentModelIndex] = {}
        for index in indexes:
            if not index.isValid():
                continue
            child_row = -1 if index.internalId() == TOP_LEVEL_ID else index.row()
            unique[(self.top_level_row(index), child_row)] = QPersistentModelIndex(index)
        return [unique[key] for key in sorted(unique)]

    def _check_move(self, sources: list[QPersistentModelIndex], target_parent: ModelIndex) -> None:
        """Raise ``ValueError`` unless ``sources`` and ``target_parent`` make a move ``move_items`` allows."""
        if target_parent.isValid():
            self._group_at(self.top_level_row(target_parent))  # raises for a song
            if target_parent.internalId() != TOP_LEVEL_ID:
                raise ValueError("the target of a move must be a group or the top level")
        group_count = sum(1 for source in sources if source.data(IsGroupRole))
        if group_count and len(sources) > 1:
            raise ValueError("only songs, or a single group, can be moved together")
        if group_count and target_parent.isValid():
            raise ValueError("a group cannot be moved into a group")

    def _index_of_group(self, group: SongGroup | None) -> QModelIndex:
        """Return the index of ``group``'s row, or an invalid index (the top level) for ``None``."""
        if group is None:
            return QModelIndex()
        return self.index(self._group_rows[id(group)], 0)

    # --- Drag and drop ------------------------------------------------------------------------------
    # Drags never leave the view, and the view moves its own selection with ``move_items`` on a drop
    # (``SongTreeView.dropEvent``). The model only tells Qt what may be dragged and dropped where, so it
    # implements neither ``dropMimeData`` nor ``removeRows``.

    def flags(self, index: ModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.ItemIsDropEnabled  # dropping below the last row: the end of the top level
        flags = super().flags(index) | Qt.ItemFlag.ItemIsDragEnabled
        if self.data(index, IsGroupRole):
            # Only groups accept a drop onto the row itself; on songs Qt offers only above and below.
            flags |= Qt.ItemFlag.ItemIsDropEnabled
        return flags

    def supportedDropActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction

    def mimeTypes(self) -> list[str]:
        return [ROWS_MIME_TYPE]

    def mimeData(self, indexes: list[QModelIndex]) -> QMimeData:  # type: ignore[override]
        """Return drag data that only marks the drag as one of this list's rows; the view knows which."""
        mime_data = QMimeData()
        mime_data.setData(ROWS_MIME_TYPE, QByteArray(b"rows"))
        return mime_data

    # --- Playback -----------------------------------------------------------------------------------

    def set_playing_song(self, song_id: ItunesPersistentID | None) -> None:
        """Mark the song shown as playing (``IsPlayingRole``), or none. Only the affected rows repaint."""
        old_index = self._index_of_song(self._playing_song_id)
        self._playing_song_id = song_id
        new_index = self._index_of_song(song_id)
        for index in (old_index, new_index):
            if index.isValid():
                self.dataChanged.emit(index, index, [IsPlayingRole])

    def playing_position(self) -> int | None:
        """Return the flat position (in ``songs()``) of the song marked as playing, or ``None``."""
        if self._playing_song_id is None:
            return None
        for position, song in enumerate(self.songs()):
            if song.id == self._playing_song_id:
                return position
        return None

    def index_at_position(self, position: int) -> QModelIndex:
        """Return the index of the song at flat ``position`` in ``songs()``, or an invalid index."""
        remaining = position
        for row, item in enumerate(self._items):
            if isinstance(item, SongGroup):
                if remaining < len(item.songs):
                    return self.index(remaining, 0, self.index(row, 0))
                remaining -= len(item.songs)
            else:
                if remaining == 0:
                    return self.index(row, 0)
                remaining -= 1
        return QModelIndex()

    # --- QAbstractItemModel -------------------------------------------------------------------------

    def index(self, row: int, column: int, parent: ModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if not parent.isValid():
            return self.createIndex(row, column, TOP_LEVEL_ID)
        # hasIndex has checked that parent is a group (only groups have rows below them).
        return self.createIndex(row, column, id(self._items[parent.row()]))

    def parent(self, child: ModelIndex) -> QModelIndex:  # type: ignore[override]  # hides QObject.parent()
        if not child.isValid() or child.internalId() == TOP_LEVEL_ID:
            return QModelIndex()
        return self.createIndex(self._group_rows[child.internalId()], 0, TOP_LEVEL_ID)

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:
        if not parent.isValid():
            return len(self._items)
        if parent.internalId() != TOP_LEVEL_ID:
            return 0  # songs in a group have no children
        item = self._items[parent.row()]
        return len(item.songs) if isinstance(item, SongGroup) else 0

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:
        return 1

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        item = self._item(index)
        if isinstance(item, SongGroup):
            return self._group_data(item, role)
        return self._song_data(item, role)

    def _group_data(self, group: SongGroup, role: int) -> Any:
        if role == Qt.ItemDataRole.DisplayRole:
            return group.name
        if role == IsGroupRole:
            return True
        if role == GroupSongCountRole:
            return len(group.songs)
        return None

    def _song_data(self, song: Song, role: int) -> Any:
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
        if role == IsGroupRole:
            return False
        return None

    # --- Helpers ------------------------------------------------------------------------------------

    def _item(self, index: ModelIndex) -> SortingItem:
        """Return the song or group shown at a valid ``index``."""
        if index.internalId() == TOP_LEVEL_ID:
            return self._items[index.row()]
        group = self._items[self._group_rows[index.internalId()]]
        assert isinstance(group, SongGroup)
        return group.songs[index.row()]

    def _group_at(self, top_row: int) -> SongGroup:
        group = self._items[top_row]
        if not isinstance(group, SongGroup):
            raise ValueError(f"top-level row {top_row} is not a group")
        return group

    def _emit_song_count_changed(self, group: SongGroup) -> None:
        group_index = self.index(self._group_rows[id(group)], 0)
        self.dataChanged.emit(group_index, group_index, [GroupSongCountRole])

    def _update_group_rows(self) -> None:
        self._group_rows = {id(item): row for row, item in enumerate(self._items) if isinstance(item, SongGroup)}

    def _index_of_song(self, song_id: ItunesPersistentID | None) -> QModelIndex:
        """Return the index of the song with ``song_id`` wherever it is, or an invalid index."""
        if song_id is None:
            return QModelIndex()
        for row, item in enumerate(self._items):
            if isinstance(item, SongGroup):
                for child_row, song in enumerate(item.songs):
                    if song.id == song_id:
                        return self.index(child_row, 0, self.index(row, 0))
            elif item.id == song_id:
                return self.index(row, 0)
        return QModelIndex()

    def _artwork_pixmap(self, song: Song) -> QPixmap:
        """Return the song's artwork scaled for a row, or an empty placeholder when there is none."""
        pixmap = self._artwork_pixmaps.get(song.id)
        if pixmap is None:
            pixmap = load_artwork_pixmap(self._artwork_cache, song, ARTWORK_SIZE)
            self._artwork_pixmaps[song.id] = pixmap
        return pixmap


def _copy_item(item: SortingItem) -> SortingItem:
    """Return a group as a new ``SongGroup`` with its own song list; songs are returned as they are."""
    if isinstance(item, SongGroup):
        return SongGroup(name=item.name, songs=list(item.songs))
    return item
