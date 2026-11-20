from itunes_tools.common.models import ItunesPersistentID, Playlist
from itunes_tools.sorter.sorter_file import GroupRange, SorterFile
from itunes_tools.sorter.sorting_items import (
    SongGroup,
    flatten,
    items_from_sorter_file,
    season_group_names,
    sorter_file_from_items,
)

PLAYLIST_ID = ItunesPersistentID(high=1, low=1)


def test_flatten_reads_group_songs_in_place(make_song):
    songs = [make_song(low) for low in range(5)]
    items = [songs[0], SongGroup(name="G", songs=songs[1:3]), SongGroup(name="Empty"), songs[3], songs[4]]

    assert flatten(items) == songs


def test_season_names_of_one_year_start_with_winter_and_end_with_fall():
    assert season_group_names(2017, 2017) == ["Winter 2017", "Spring 2017", "Summer 2017", "Fall 2017"]


def test_season_names_of_a_range_are_oldest_first():
    names = season_group_names(2017, 2019)

    assert len(names) == 12
    assert names[3:5] == ["Fall 2017", "Winter 2018"]
    assert names[-1] == "Fall 2019"


def test_season_names_are_empty_for_a_reversed_range():
    assert season_group_names(2019, 2017) == []


def test_sorter_file_from_items_stores_flat_tracks_and_group_ranges(make_song):
    songs = [make_song(low) for low in range(4)]
    playlist = Playlist(id=PLAYLIST_ID, name="Mix", tracks=[])
    items = [SongGroup(name="Empty"), songs[0], SongGroup(name="Pair", songs=songs[1:3]), songs[3]]

    sorter_file = sorter_file_from_items(playlist, items)

    assert sorter_file.playlist.tracks == songs
    assert sorter_file.playlist.name == "Mix"
    assert sorter_file.groups == [
        GroupRange(name="Empty", first_track=0, track_count=0),
        GroupRange(name="Pair", first_track=1, track_count=2),
    ]


def test_items_round_trip_through_a_sorter_file(make_song):
    songs = [make_song(low) for low in range(4)]
    playlist = Playlist(id=PLAYLIST_ID, name="Mix", tracks=[])
    items = [songs[0], SongGroup(name="A", songs=songs[1:3]), SongGroup(name="B"), songs[3], SongGroup(name="C")]

    assert items_from_sorter_file(sorter_file_from_items(playlist, items)) == items


def test_file_without_groups_gives_top_level_songs(make_song):
    songs = [make_song(1), make_song(2)]

    items = items_from_sorter_file(SorterFile(playlist=Playlist(id=PLAYLIST_ID, name="Mix", tracks=songs)))

    assert items == songs
