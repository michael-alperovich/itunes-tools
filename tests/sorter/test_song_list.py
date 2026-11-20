from collections.abc import Callable, Iterator

import pytest
from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QAbstractItemModelTester

from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.common.models import Song
from itunes_tools.sorter.song_list import (
    ARTWORK_SIZE,
    AlbumRole,
    ArtistRole,
    GroupSongCountRole,
    IsGroupRole,
    IsPlayingRole,
    SongListModel,
    SongRole,
)
from itunes_tools.sorter.sorting_items import SongGroup

pytestmark = pytest.mark.usefixtures("qt_application")


@pytest.fixture
def make_model(tmp_path) -> Iterator[Callable[[], SongListModel]]:
    """Return a factory for empty models that are checked by ``QAbstractItemModelTester``.

    The tester checks the model's tree structure and its change signals after every change, and reports
    problems as Qt warnings; the test fails if any were reported.
    """
    warnings: list[str] = []

    def collect_warning(message_type: QtMsgType, context, message: str) -> None:
        if message_type != QtMsgType.QtDebugMsg:
            warnings.append(message)

    testers = []

    def factory() -> SongListModel:
        model = SongListModel(ArtworkCache(tmp_path))
        testers.append(QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Warning))
        return model

    previous_handler = qInstallMessageHandler(collect_warning)
    yield factory
    qInstallMessageHandler(previous_handler)
    assert warnings == []


def names(model: SongListModel) -> list[str]:
    return [song.name for song in model.songs()]


def tree(model: SongListModel) -> list[str | tuple[str, list[str]]]:
    """Return the model as top-level song names and ``(group name, song names)`` tuples, read through Qt's API."""
    result: list[str | tuple[str, list[str]]] = []
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        if index.data(IsGroupRole):
            children = [model.index(child, 0, index).data() for child in range(model.rowCount(index))]
            result.append((index.data(), children))
        else:
            result.append(index.data())
    return result


@pytest.fixture
def songs(make_song) -> list[Song]:
    return [make_song(low, name) for low, name in enumerate("ABCDE", start=1)]


def test_model_has_one_row_per_song_in_order(make_model, songs):
    model = make_model()

    model.set_items(songs[:2])

    assert model.rowCount() == 2
    assert tree(model) == ["A", "B"]
    assert model.songs() == songs[:2]


def test_groups_hold_their_songs_as_children(make_model, songs):
    model = make_model()

    model.set_items([songs[0], SongGroup(name="G", songs=songs[1:3]), SongGroup(name="Empty"), songs[3]])

    assert tree(model) == ["A", ("G", ["B", "C"]), ("Empty", []), "D"]
    assert names(model) == ["A", "B", "C", "D"]
    group = model.index(1, 0)
    assert model.parent(model.index(1, 0, group)) == group
    assert not model.parent(group).isValid()
    assert model.data(group, GroupSongCountRole) == 2
    assert model.data(group, SongRole) is None
    assert model.group_names() == ["G", "Empty"]
    assert model.group_row("Empty") == 2
    assert model.group_row("Missing") is None


def test_items_are_copies(make_model, songs):
    model = make_model()
    group = SongGroup(name="G", songs=[songs[0]])
    model.set_items([group])

    group.songs.append(songs[1])
    model.items()[0].songs.clear()

    assert tree(model) == [("G", ["A"])]


def test_model_exposes_artist_album_and_song_roles(make_model, make_song):
    model = make_model()
    song = make_song(1, artist="Queen", album="Jazz")
    model.set_items([song])
    index = model.index(0, 0)

    assert model.data(index, ArtistRole) == "Queen"
    assert model.data(index, AlbumRole) == "Jazz"
    assert model.data(index, SongRole) == song
    assert model.data(index, IsGroupRole) is False
    assert model.data(index, Qt.ItemDataRole.ToolTipRole) is None


def test_model_returns_a_placeholder_pixmap_when_artwork_is_not_cached(make_model, make_song):
    model = make_model()
    model.set_items([make_song(1)])

    pixmap = model.data(model.index(0, 0), Qt.ItemDataRole.DecorationRole)

    assert not pixmap.isNull()
    assert (pixmap.width(), pixmap.height()) == (ARTWORK_SIZE, ARTWORK_SIZE)


def test_model_scales_cached_artwork_to_the_row_size(tmp_path, make_song):
    image = QImage(200, 100, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    assert image.save(str(tmp_path / "0000000000000001.png"))
    model = SongListModel(ArtworkCache(tmp_path))
    model.set_items([make_song(1)])

    pixmap = model.data(model.index(0, 0), Qt.ItemDataRole.DecorationRole)

    assert (pixmap.width(), pixmap.height()) == (ARTWORK_SIZE, ARTWORK_SIZE // 2)


def test_insert_groups_adds_empty_groups_in_order(make_model, songs):
    model = make_model()
    model.set_items([songs[0], SongGroup(name="G", songs=[songs[1]])])
    child = QPersistentModelIndex(model.index(0, 0, model.index(1, 0)))

    model.insert_groups(1, ["X", "Y"])

    assert tree(model) == ["A", ("X", []), ("Y", []), ("G", ["B"])]
    # A song inside a group that moved down is still found through an index taken before.
    assert child.data() == "B"
    assert model.top_level_row(QModelIndex(child)) == 3


def test_rename_group(make_model, songs):
    model = make_model()
    model.set_items([SongGroup(name="Old", songs=[songs[0]])])

    model.rename_group(0, "New")

    assert tree(model) == [("New", ["A"])]


def test_delete_group_leaves_its_songs_in_place_and_in_order(make_model, songs):
    model = make_model()
    model.set_items([songs[0], SongGroup(name="G", songs=songs[1:4]), songs[4]])
    selected = QPersistentModelIndex(model.index(1, 0, model.index(1, 0)))

    model.delete_group(1)

    assert tree(model) == ["A", "B", "C", "D", "E"]
    assert selected.data() == "C"


def test_delete_empty_group(make_model, songs):
    model = make_model()
    model.set_items([SongGroup(name="Empty"), songs[0]])

    model.delete_group(0)

    assert tree(model) == ["A"]


def test_rows_that_are_not_groups_cannot_be_changed_as_groups(make_model, songs):
    model = make_model()
    model.set_items([songs[0]])

    with pytest.raises(ValueError):
        model.delete_group(0)


def top(model: SongListModel, row: int) -> QModelIndex:
    return model.index(row, 0)


def child(model: SongListModel, group_row: int, row: int) -> QModelIndex:
    return model.index(row, 0, model.index(group_row, 0))


@pytest.mark.parametrize(
    ("rows", "target_row", "expected"),
    [
        ([0, 1], 3, ["C", "A", "B", "D", "E"]),  # down
        ([3, 4], 0, ["D", "E", "A", "B", "C"]),  # up
        ([0, 2, 4], 2, ["B", "A", "C", "E", "D"]),  # non-contiguous, around the insertion point
        ([1, 3], 2, ["A", "B", "D", "C", "E"]),  # the first one already stands there
        ([0], 5, ["B", "C", "D", "E", "A"]),  # to the end
    ],
)
def test_move_top_level_songs(make_model, songs, rows, target_row, expected):
    model = make_model()
    model.set_items(songs)

    model.move_items([top(model, row) for row in rows], QModelIndex(), target_row)

    assert tree(model) == expected


def test_move_keeps_playlist_order_whatever_the_order_of_the_indexes(make_model, songs):
    model = make_model()
    model.set_items(songs)

    model.move_items([top(model, 4), top(model, 0), top(model, 4)], QModelIndex(), 2)

    assert tree(model) == ["B", "A", "E", "C", "D"]


def test_move_that_changes_nothing_moves_no_row(make_model, songs):
    model = make_model()
    model.set_items(songs)
    moves = []
    model.rowsMoved.connect(lambda *args: moves.append(args))

    assert model.move_items([top(model, 1), top(model, 2)], QModelIndex(), 1) == 0
    assert model.move_items([top(model, 1), top(model, 2)], QModelIndex(), 3) == 0
    assert model.move_items([], QModelIndex(), 0) == 0

    assert tree(model) == ["A", "B", "C", "D", "E"]
    assert moves == []


def test_move_songs_into_a_group_from_above_and_below(make_model, songs):
    model = make_model()
    model.set_items([songs[0], SongGroup(name="G", songs=songs[1:3]), songs[3]])

    moved = model.move_items([top(model, 0), top(model, 2)], model.index(1, 0), 1)

    assert moved == 2
    assert tree(model) == [("G", ["B", "A", "D", "C"])]
    assert model.data(model.index(0, 0), GroupSongCountRole) == 4


def test_move_songs_out_of_a_group(make_model, songs):
    model = make_model()
    model.set_items([songs[0], SongGroup(name="G", songs=songs[1:4]), songs[4]])

    model.move_items([child(model, 1, 0), child(model, 1, 2)], QModelIndex(), 0)

    assert tree(model) == ["B", "D", "A", ("G", ["C"]), "E"]


def test_move_songs_between_groups_and_the_top_level(make_model, songs):
    model = make_model()
    model.set_items([SongGroup(name="X", songs=songs[0:2]), songs[2], SongGroup(name="Y", songs=songs[3:5])])
    counts = []
    model.dataChanged.connect(
        lambda top_left, bottom_right, roles: counts.append((top_left.data(), top_left.data(GroupSongCountRole)))
    )

    model.move_items([child(model, 0, 1), top(model, 1), child(model, 2, 0)], model.index(0, 0), 0)

    assert tree(model) == [("X", ["B", "C", "D", "A"]), ("Y", ["E"])]
    assert sorted(counts) == [("X", 4), ("Y", 1)]


def test_move_song_to_the_end_of_an_empty_group(make_model, songs):
    model = make_model()
    model.set_items([songs[0], SongGroup(name="Empty")])

    model.move_items([top(model, 0)], model.index(1, 0), 0)

    assert tree(model) == [("Empty", ["A"])]


def test_move_group_with_its_songs(make_model, songs):
    model = make_model()
    model.set_items([songs[0], SongGroup(name="G", songs=songs[1:3]), songs[3]])
    inside = QPersistentModelIndex(child(model, 1, 1))

    model.move_items([top(model, 1)], QModelIndex(), 3)

    assert tree(model) == ["A", "D", ("G", ["B", "C"])]
    assert inside.data() == "C"
    assert inside.parent() == model.index(2, 0)


def test_moved_rows_keep_their_persistent_indexes(make_model, songs):
    model = make_model()
    model.set_items([songs[0], songs[1], SongGroup(name="G", songs=[songs[2]]), songs[3]])
    selected = [QPersistentModelIndex(top(model, 0)), QPersistentModelIndex(top(model, 3))]

    model.move_items([QModelIndex(index) for index in selected], model.index(2, 0), 1)

    assert [index.data() for index in selected] == ["A", "D"]
    assert all(index.parent() == model.index(1, 0) for index in selected)


def test_playing_song_keeps_its_mark_when_moved(make_model, songs):
    model = make_model()
    model.set_items([songs[0], songs[1], SongGroup(name="G")])
    model.set_playing_song(songs[0].id)

    model.move_items([top(model, 0)], model.index(2, 0), 0)

    assert model.playing_position() == 1
    assert child(model, 1, 0).data(IsPlayingRole)


@pytest.mark.parametrize("target", ["group", "song in group", "song"])
def test_invalid_moves_raise(make_model, songs, target):
    model = make_model()
    model.set_items([songs[0], SongGroup(name="X", songs=[songs[1]]), SongGroup(name="Y")])
    target_parent = {"group": model.index(2, 0), "song in group": child(model, 1, 0), "song": top(model, 0)}[target]

    with pytest.raises(ValueError):
        model.move_items([model.index(1, 0)], target_parent, 0)
    with pytest.raises(ValueError):
        model.move_items([top(model, 0), model.index(1, 0)], QModelIndex(), 0)
    assert tree(model) == ["A", ("X", ["B"]), ("Y", [])]


def test_drag_and_drop_flags(make_model, songs):
    model = make_model()
    model.set_items([songs[0], SongGroup(name="G", songs=[songs[1]])])

    song_flags = model.flags(top(model, 0))
    group_flags = model.flags(model.index(1, 0))

    assert song_flags & Qt.ItemFlag.ItemIsDragEnabled
    assert not song_flags & Qt.ItemFlag.ItemIsDropEnabled
    assert group_flags & Qt.ItemFlag.ItemIsDragEnabled
    assert group_flags & Qt.ItemFlag.ItemIsDropEnabled
    assert model.flags(QModelIndex()) & Qt.ItemFlag.ItemIsDropEnabled
    assert model.mimeData([top(model, 0)]).hasFormat(model.mimeTypes()[0])
    assert model.supportedDropActions() == Qt.DropAction.MoveAction


def test_top_level_row_of_songs_groups_and_nothing(make_model, songs):
    model = make_model()
    model.set_items([songs[0], SongGroup(name="G", songs=[songs[1]])])

    assert model.top_level_row(model.index(0, 0)) == 0
    assert model.top_level_row(model.index(0, 0, model.index(1, 0))) == 1
    assert model.top_level_row(QModelIndex()) == 2


def test_index_at_position_walks_into_groups(make_model, songs):
    model = make_model()
    model.set_items([songs[0], SongGroup(name="Empty"), SongGroup(name="G", songs=songs[1:3]), songs[3]])

    assert [model.index_at_position(position).data() for position in range(4)] == ["A", "B", "C", "D"]
    assert not model.index_at_position(4).isValid()


def test_set_playing_song_marks_only_that_song_and_repaints_old_and_new_rows(make_model, songs):
    model = make_model()
    model.set_items([songs[0], SongGroup(name="G", songs=[songs[1]]), songs[2]])
    model.set_playing_song(songs[0].id)
    changed = []
    model.dataChanged.connect(lambda top_left, bottom_right, roles: changed.append(top_left.data()))

    model.set_playing_song(songs[1].id)

    assert model.playing_position() == 1
    assert model.index(0, 0, model.index(1, 0)).data(IsPlayingRole)
    assert not model.index(0, 0).data(IsPlayingRole)
    assert sorted(changed) == ["A", "B"]


def test_playing_position_is_none_without_a_playing_song_in_the_list(make_model, songs, make_song):
    model = make_model()
    model.set_items([songs[0]])

    assert model.playing_position() is None
    model.set_playing_song(make_song(99).id)
    assert model.playing_position() is None
