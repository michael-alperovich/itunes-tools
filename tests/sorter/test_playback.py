from pathlib import Path

import pytest

from itunes_tools.sorter.playback import is_playable, next_playable_index, previous_playable_index


@pytest.fixture
def songs(make_song):
    """Five songs; the ones at indexes 1 and 3 have no file."""
    return [make_song(low, location=None if low in (1, 3) else Path(f"D:/Music/{low}.m4a")) for low in range(5)]


def test_is_playable_needs_a_file(make_song):
    assert is_playable(make_song(1, location=Path("D:/Music/a.m4a")))
    assert not is_playable(make_song(1, location=None))


def test_next_playable_index_skips_songs_without_a_file(songs):
    assert next_playable_index(songs, -1) == 0
    assert next_playable_index(songs, 0) == 2
    assert next_playable_index(songs, 2) == 4


def test_next_playable_index_is_none_after_the_last_song(songs):
    assert next_playable_index(songs, 4) is None
    assert next_playable_index([], -1) is None


def test_previous_playable_index_skips_songs_without_a_file(songs):
    assert previous_playable_index(songs, 4) == 2
    assert previous_playable_index(songs, 2) == 0


def test_previous_playable_index_is_none_before_the_first_song(songs):
    assert previous_playable_index(songs, 0) is None
    assert previous_playable_index(songs, 1) == 0
