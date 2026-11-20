import pytest
from pydantic import ValidationError

from itunes_tools.common.models import ItunesPersistentID, Playlist, Song


def make_song(**overrides) -> Song:
    fields = {
        "id": ItunesPersistentID(high=1, low=2),
        "name": "Song",
        "artist": "Artist",
        "album": "Album",
        "duration": 180,
    }
    fields.update(overrides)
    return Song(**fields)


def test_persistent_id_to_hex_masks_negative_halves():
    # Conversion edge cases are covered in test_utils.py; this checks the model delegates correctly.
    assert ItunesPersistentID(high=0x1A2B3C4D, low=-1).to_hex() == "1A2B3C4DFFFFFFFF"


def test_persistent_ids_compare_by_value():
    assert ItunesPersistentID(high=1, low=2) == ItunesPersistentID(high=1, low=2)
    assert ItunesPersistentID(high=1, low=2) != ItunesPersistentID(high=2, low=1)


def test_persistent_ids_work_as_dict_keys_and_set_members():
    songs_by_id = {ItunesPersistentID(high=1, low=2): "Song"}

    assert songs_by_id[ItunesPersistentID(high=1, low=2)] == "Song"
    assert len({ItunesPersistentID(high=1, low=2), ItunesPersistentID(high=1, low=2)}) == 1


def test_persistent_id_is_immutable():
    persistent_id = ItunesPersistentID(high=1, low=2)

    with pytest.raises(ValidationError):
        persistent_id.high = 3


@pytest.mark.parametrize("value", [-2147483648, 2147483647])
def test_persistent_id_accepts_int32_limits(value):
    assert ItunesPersistentID(high=value, low=value).high == value


@pytest.mark.parametrize("field", ["high", "low"])
@pytest.mark.parametrize("value", [-2147483649, 2147483648])
def test_persistent_id_rejects_values_outside_int32(field, value):
    fields = {"high": 0, "low": 0, field: value}

    with pytest.raises(ValidationError):
        ItunesPersistentID(**fields)


def test_song_accepts_valid_fields():
    song = make_song(name="Æon — Ünïcode", duration=215)

    assert song.name == "Æon — Ünïcode"
    assert song.duration == 215


def test_song_requires_all_fields():
    with pytest.raises(ValidationError):
        Song(id=ItunesPersistentID(high=1, low=2), name="Song")


def test_song_rejects_time_string_as_duration():
    # COM's ``Time`` property is a "m:ss" string; ``duration`` must come from ``Duration`` (seconds).
    with pytest.raises(ValidationError):
        make_song(duration="3:35")


def test_playlist_holds_songs_in_order():
    songs = [make_song(name="First"), make_song(name="Second")]

    playlist = Playlist(id=ItunesPersistentID(high=3, low=4), name="Mix", tracks=songs)

    assert [song.name for song in playlist.tracks] == ["First", "Second"]
