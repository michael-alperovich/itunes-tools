from datetime import UTC, datetime
from pathlib import Path

from itunes_tools.common.models import ItunesPersistentID, Playlist, Song
from itunes_tools.sorter.sorter_file import (
    SorterFile,
    load_sorter_file,
    save_sorter_file,
    suggested_sorter_file_path,
)

MODIFIED = datetime(2023, 7, 8, 20, 33, 28, tzinfo=UTC)


def make_song(low: int, name: str = "Song", location: Path | None = None) -> Song:
    return Song(
        id=ItunesPersistentID(high=-5, low=low),
        name=name,
        artist="Artist",
        album="Album",
        album_artist="",
        genre="",
        year=2020,
        track_number=1,
        disc_number=1,
        duration=180,
        date_added=MODIFIED,
        modification_date=MODIFIED,
        location=location,
        artwork_count=1,
    )


def make_sorter_file() -> SorterFile:
    tracks = [
        make_song(3, name="Third", location=Path(r"D:\Music\Third.mp3")),
        make_song(1, name="Ünïcödé"),
        make_song(2, name="Second"),
    ]
    return SorterFile(playlist=Playlist(id=ItunesPersistentID(high=1, low=-1), name="Mix", tracks=tracks))


def test_save_then_load_returns_an_equal_sorter_file(tmp_path):
    sorter_file = make_sorter_file()
    path = tmp_path / "Mix.yaml"

    save_sorter_file(sorter_file, path)

    assert load_sorter_file(path) == sorter_file


def test_saved_file_keeps_track_order_and_model_field_order(tmp_path):
    path = tmp_path / "Mix.yaml"

    save_sorter_file(make_sorter_file(), path)

    text = path.read_text(encoding="utf-8")
    assert text.startswith("format_version: 1\nplaylist:\n")
    assert text.index("Third") < text.index("Ünïcödé") < text.index("Second")


def test_save_replaces_an_existing_file(tmp_path):
    path = tmp_path / "Mix.yaml"
    path.write_text("old content", encoding="utf-8")

    save_sorter_file(make_sorter_file(), path)

    assert load_sorter_file(path) == make_sorter_file()


def test_suggested_path_uses_the_playlist_name_in_the_given_folder(tmp_path):
    assert suggested_sorter_file_path("Summer Mix", tmp_path) == tmp_path / "Summer Mix.yaml"


def test_suggested_path_replaces_characters_windows_forbids(tmp_path):
    path = suggested_sorter_file_path('a<b>c:d"e/f\\g|h?i*j', tmp_path)

    assert path == tmp_path / "a_b_c_d_e_f_g_h_i_j.yaml"
