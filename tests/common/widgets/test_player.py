import time
import wave
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.common.widgets.player import PlayerWidget, format_time, last_seconds_start

pytestmark = pytest.mark.usefixtures("qt_application")


@pytest.mark.parametrize(
    ("milliseconds", "expected"),
    [(0, "0:00"), (999, "0:00"), (61_000, "1:01"), (3_725_000, "62:05"), (-5, "0:00")],
)
def test_format_time(milliseconds, expected):
    assert format_time(milliseconds) == expected


def test_last_seconds_start_is_counted_from_the_end():
    assert last_seconds_start(180_000, 10) == 170_000


def test_last_seconds_start_is_zero_for_short_songs():
    assert last_seconds_start(4_000, 10) == 0


def test_a_new_player_shows_nothing_playing(tmp_path):
    player = PlayerWidget(ArtworkCache(tmp_path))

    assert player.current_song() is None
    assert player._title_label.text() == "Not playing"


def test_playing_a_song_without_a_file_shows_it_and_reports_the_failure(tmp_path, make_song):
    player = PlayerWidget(ArtworkCache(tmp_path))
    song = make_song(1, name="Bohemian Rhapsody", artist="Queen", album="A Night at the Opera")
    current_songs, failures = [], []
    player.currentSongChanged.connect(current_songs.append)
    player.playbackFailed.connect(failures.append)

    player.play(song)

    assert player.current_song() == song
    assert current_songs == [song]
    assert player._title_label.text() == "Bohemian Rhapsody"
    assert player._details_label.text() == "Queen – A Night at the Opera"
    assert failures == ["Cannot play 'Bohemian Rhapsody': iTunes has no file for it."]


def test_stop_unloads_the_song(tmp_path, make_song):
    player = PlayerWidget(ArtworkCache(tmp_path))
    player.play(make_song(1))
    current_songs = []
    player.currentSongChanged.connect(current_songs.append)

    player.stop()

    assert player.current_song() is None
    assert current_songs == [None]


def write_silent_wav(path: Path, seconds: int) -> Path:
    """Write a silent mono 8 kHz WAV file, small enough for Qt Multimedia to load quickly."""
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(bytes(2) * 8000 * seconds)
    return path


def wait_until(condition: Callable[[], bool], timeout_s: float = 5.0) -> bool:
    """Process Qt events until ``condition`` holds or the timeout passes; return whether it held."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return condition()


def test_replaying_the_same_song_keeps_the_seek_bar_length(tmp_path, make_song):
    # Regression: setting the same file again does not reload it, so durationChanged does not come
    # and the seek bar was left with a 0:00 length.
    song = make_song(1, location=write_silent_wav(tmp_path / "song.wav", seconds=3))
    player = PlayerWidget(ArtworkCache(tmp_path))
    player._volume_slider.setValue(0)
    player.play(song)
    assert wait_until(lambda: player._seek_slider.maximum() > 0)

    player.play_last_seconds(song, 1)

    assert player._seek_slider.maximum() > 0
    player.stop()
