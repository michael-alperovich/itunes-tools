import threading
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
import pywintypes

from itunes_tools.common.exceptions import (
    DuplicatePlaylistNameError,
    ItunesClientThreadError,
    ItunesComError,
    PlaylistNameTakenError,
    PlaylistNotFoundError,
    TrackNotFoundError,
)
from itunes_tools.common.itunes_client import ItunesClient
from itunes_tools.common.models import ItunesPersistentID, Song

TRACK_KIND_URL = 3  # ITTrackKindURL: a track without a local file

OPERATION_UNAVAILABLE = pywintypes.com_error(-2147221021, "Operation unavailable", None, None)


def test_constructor_does_not_dispatch_com(com_dispatch):
    ItunesClient()

    com_dispatch.assert_not_called()


def test_com_app_is_dispatched_once_on_first_use_and_reused(com_dispatch):
    client = ItunesClient()

    client.list_playlists()
    client.list_playlists()

    com_dispatch.assert_called_once_with("iTunes.Application")


def test_custom_prog_id_is_passed_to_dispatch(com_dispatch):
    ItunesClient(prog_id="Custom.Application").list_playlists()

    com_dispatch.assert_called_once_with("Custom.Application")


def test_list_playlists_maps_names_to_persistent_ids(fake_itunes, make_com_playlist):
    fake_itunes.set_playlists(
        make_com_playlist(1, 2, name="Library"),
        make_com_playlist(3, -4, name="Favourites"),
    )

    playlists = ItunesClient().list_playlists()

    assert playlists == {
        "Library": ItunesPersistentID(high=1, low=2),
        "Favourites": ItunesPersistentID(high=3, low=-4),
    }


def test_list_playlists_returns_empty_dict_for_empty_library(fake_itunes):
    assert ItunesClient().list_playlists() == {}


def test_list_playlists_raises_for_duplicate_names(fake_itunes, make_com_playlist):
    fake_itunes.set_playlists(
        make_com_playlist(1, 1, name="Rock"),
        make_com_playlist(2, 2, name="Jazz"),
        make_com_playlist(3, 3, name="Rock"),
        make_com_playlist(4, 4, name="Blues"),
        make_com_playlist(5, 5, name="Blues"),
        make_com_playlist(6, 6, name="Rock"),
    )

    with pytest.raises(DuplicatePlaylistNameError, match="Rename these playlists") as error_info:
        ItunesClient().list_playlists()

    assert error_info.value.duplicate_names == ["Blues", "Rock"]


def test_list_playlists_treats_names_differing_in_case_as_distinct(fake_itunes, make_com_playlist):
    fake_itunes.set_playlists(
        make_com_playlist(1, 1, name="Rock"),
        make_com_playlist(2, 2, name="rock"),
    )

    assert set(ItunesClient().list_playlists()) == {"Rock", "rock"}


def test_get_playlist_by_id_maps_tracks_to_songs(fake_itunes, make_com_playlist, make_com_track, make_artwork):
    track = make_com_track(
        10,
        -20,
        name="Song",
        artist="Artist",
        album="Album",
        album_artist="Album Artist",
        genre="Rock",
        year=1999,
        track_number=4,
        disc_number=2,
        duration=215,
        date_added=datetime(2022, 3, 7, 12, 39, 30, tzinfo=UTC),
        modification_date=datetime(2023, 7, 8, 20, 33, 28, tzinfo=UTC),
        location=r"D:\Music\Song.mp3",
        artworks=[make_artwork()],
    )
    fake_itunes.set_playlists(
        make_com_playlist(1, 2, name="Library"),
        make_com_playlist(3, 4, name="Favourites", tracks=[track]),
    )

    playlist = ItunesClient().get_playlist_by_id(ItunesPersistentID(high=3, low=4))

    assert playlist.id == ItunesPersistentID(high=3, low=4)
    assert playlist.name == "Favourites"
    assert playlist.tracks == [
        Song(
            id=ItunesPersistentID(high=10, low=-20),
            name="Song",
            artist="Artist",
            album="Album",
            album_artist="Album Artist",
            genre="Rock",
            year=1999,
            track_number=4,
            disc_number=2,
            duration=215,
            date_added=datetime(2022, 3, 7, 12, 39, 30, tzinfo=UTC),
            modification_date=datetime(2023, 7, 8, 20, 33, 28, tzinfo=UTC),
            location=Path(r"D:\Music\Song.mp3"),
            artwork_count=1,
        )
    ]


def test_get_playlist_by_id_casts_file_tracks_to_read_file_members(
    fake_itunes, com_cast_to, make_com_playlist, make_com_track
):
    track = make_com_track(1, 1)
    fake_itunes.set_playlists(make_com_playlist(5, 5, tracks=[track]))

    ItunesClient().get_playlist_by_id(ItunesPersistentID(high=5, low=5))

    com_cast_to.assert_called_once_with(track, "IITFileOrCDTrack")


def test_song_from_track_without_file_has_no_location_or_album_artist(
    fake_itunes, com_cast_to, make_com_playlist, make_com_track
):
    fake_itunes.set_playlists(make_com_playlist(5, 5, tracks=[make_com_track(1, 1, kind=TRACK_KIND_URL)]))

    [song] = ItunesClient().get_playlist_by_id(ItunesPersistentID(high=5, low=5)).tracks

    assert song.location is None
    assert song.album_artist == ""
    com_cast_to.assert_not_called()


def test_song_location_is_none_when_itunes_cannot_find_the_file(fake_itunes, make_com_playlist, make_com_track):
    fake_itunes.set_playlists(make_com_playlist(5, 5, tracks=[make_com_track(1, 1, location="")]))

    [song] = ItunesClient().get_playlist_by_id(ItunesPersistentID(high=5, low=5)).tracks

    assert song.location is None


def test_song_dates_are_converted_to_plain_utc_datetimes(fake_itunes, make_com_playlist, make_com_track):
    # COM returns local-time pywintypes.datetime values; songs store plain UTC datetimes.
    local_time = datetime(2022, 3, 7, 14, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    fake_itunes.set_playlists(make_com_playlist(5, 5, tracks=[make_com_track(1, 1, date_added=local_time)]))

    [song] = ItunesClient().get_playlist_by_id(ItunesPersistentID(high=5, low=5)).tracks

    assert song.date_added == datetime(2022, 3, 7, 12, 0, 0, tzinfo=UTC)
    assert song.date_added.tzinfo is UTC
    assert type(song.date_added) is datetime


def test_get_playlist_by_id_preserves_track_order(fake_itunes, make_com_playlist, make_com_track):
    tracks = [make_com_track(1, index, name=f"Track {index}") for index in (3, 1, 2)]
    fake_itunes.set_playlists(make_com_playlist(5, 5, tracks=tracks))

    playlist = ItunesClient().get_playlist_by_id(ItunesPersistentID(high=5, low=5))

    assert [song.name for song in playlist.tracks] == ["Track 3", "Track 1", "Track 2"]


def test_get_playlist_by_id_returns_empty_playlist(fake_itunes, make_com_playlist):
    fake_itunes.set_playlists(make_com_playlist(1, 2, name="Empty"))

    playlist = ItunesClient().get_playlist_by_id(ItunesPersistentID(high=1, low=2))

    assert playlist.tracks == []


def test_get_playlist_by_id_raises_for_unknown_id(fake_itunes, make_com_playlist):
    fake_itunes.set_playlists(make_com_playlist(1, 2, name="Library"))

    with pytest.raises(PlaylistNotFoundError, match="0000000900000009 not found") as error_info:
        ItunesClient().get_playlist_by_id(ItunesPersistentID(high=9, low=9))

    assert error_info.value.persistent_id == ItunesPersistentID(high=9, low=9)


def test_create_playlist_adds_tracks_in_the_given_order(fake_itunes, com_cast_to, make_com_track):
    tracks = [make_com_track(1, index, name=f"Track {index}") for index in (1, 2, 3)]
    fake_itunes.set_library_tracks(*tracks)
    track_ids = [ItunesPersistentID(high=1, low=index) for index in (3, 1, 2)]

    playlist = ItunesClient().create_playlist("Sorted", track_ids)

    assert playlist.name == "Sorted"
    assert [song.name for song in playlist.tracks] == ["Track 3", "Track 1", "Track 2"]
    assert ItunesClient().list_playlists()["Sorted"] == playlist.id
    com_cast_to.assert_any_call(fake_itunes.LibrarySource.Playlists.Item(1), "IITUserPlaylist")


def test_create_playlist_accepts_an_empty_track_list(fake_itunes):
    assert ItunesClient().create_playlist("Empty", []).tracks == []


def test_create_playlist_rejects_a_taken_name(fake_itunes, make_com_playlist, make_com_track):
    fake_itunes.set_playlists(make_com_playlist(1, 1, name="Rock"))
    fake_itunes.set_library_tracks(make_com_track(1, 2))

    with pytest.raises(PlaylistNameTakenError, match="'Rock' already exists") as error_info:
        ItunesClient().create_playlist("Rock", [ItunesPersistentID(high=1, low=2)])

    assert error_info.value.name == "Rock"
    assert fake_itunes.LibrarySource.Playlists.Count == 1


@pytest.mark.parametrize("name", ["", "   "])
def test_create_playlist_rejects_a_blank_name(fake_itunes, name):
    with pytest.raises(ValueError, match="blank"):
        ItunesClient().create_playlist(name, [])

    assert fake_itunes.LibrarySource.Playlists.Count == 0


def test_create_playlist_with_unknown_tracks_creates_nothing(fake_itunes, make_com_track):
    fake_itunes.set_library_tracks(make_com_track(1, 1))
    unknown_ids = [ItunesPersistentID(high=9, low=1), ItunesPersistentID(high=9, low=2)]

    with pytest.raises(TrackNotFoundError) as error_info:
        ItunesClient().create_playlist("Sorted", [ItunesPersistentID(high=1, low=1), *unknown_ids])

    assert error_info.value.persistent_ids == unknown_ids
    assert fake_itunes.LibrarySource.Playlists.Count == 0


def test_create_playlist_com_error_while_adding_warns_about_incomplete_playlist(fake_itunes, make_com_track):
    fake_itunes.set_library_tracks(make_com_track(1, 1))
    create_playlist = fake_itunes.CreatePlaylist

    def create_playlist_that_fails_to_add(name):
        playlist = create_playlist(name)

        def raise_com_error(track):
            raise OPERATION_UNAVAILABLE

        playlist.AddTrack = raise_com_error
        return playlist

    fake_itunes.CreatePlaylist = create_playlist_that_fails_to_add

    with pytest.raises(ItunesComError, match="'Sorted', which may now be incomplete"):
        ItunesClient().create_playlist("Sorted", [ItunesPersistentID(high=1, low=1)])


@pytest.mark.parametrize(("artwork_format", "extension"), [(1, ".jpg"), (2, ".png"), (3, ".bmp"), (0, ".img")])
def test_export_artwork_saves_first_image_with_extension_for_its_format(
    fake_itunes, make_com_track, make_artwork, tmp_path, artwork_format, extension
):
    first = make_artwork(format=artwork_format, content=b"first")
    fake_itunes.set_library_tracks(make_com_track(1, 1, artworks=[first, make_artwork(content=b"second")]))

    exported = ItunesClient().export_artwork(ItunesPersistentID(high=1, low=1), tmp_path / "cover")

    assert exported == tmp_path / f"cover{extension}"
    assert exported.read_bytes() == b"first"
    assert first.saved_paths == [str(exported)]


def test_export_artwork_passes_an_absolute_path(fake_itunes, make_com_track, make_artwork, tmp_path, monkeypatch):
    artwork = make_artwork()
    fake_itunes.set_library_tracks(make_com_track(1, 1, artworks=[artwork]))
    monkeypatch.chdir(tmp_path)

    ItunesClient().export_artwork(ItunesPersistentID(high=1, low=1), Path("cover"))

    assert artwork.saved_paths == [str(tmp_path / "cover.png")]


def test_export_artwork_returns_none_without_artwork(fake_itunes, make_com_track, tmp_path):
    fake_itunes.set_library_tracks(make_com_track(1, 1))

    assert ItunesClient().export_artwork(ItunesPersistentID(high=1, low=1), tmp_path / "cover") is None
    assert list(tmp_path.iterdir()) == []


def test_export_artwork_raises_for_unknown_track(fake_itunes, tmp_path):
    with pytest.raises(TrackNotFoundError):
        ItunesClient().export_artwork(ItunesPersistentID(high=9, low=9), tmp_path / "cover")


def test_dispatch_com_error_is_raised_as_client_error(com_dispatch):
    com_dispatch.side_effect = OPERATION_UNAVAILABLE

    with pytest.raises(ItunesComError, match="list playlists") as error_info:
        ItunesClient().list_playlists()

    assert error_info.value.__cause__ is OPERATION_UNAVAILABLE


def test_com_error_during_call_is_raised_as_client_error(fake_itunes, make_com_playlist, make_com_track):
    fake_itunes.set_playlists(make_com_playlist(1, 2, name="Library", tracks=[make_com_track(3, 4)]))

    def raise_com_error(com_object):
        raise OPERATION_UNAVAILABLE

    fake_itunes.GetITObjectPersistentIDs = raise_com_error

    with pytest.raises(ItunesComError, match="read a playlist"):
        ItunesClient().get_playlist_by_id(ItunesPersistentID(high=1, low=2))


def list_playlists_in_worker_thread(client: ItunesClient) -> Exception | None:
    """Call ``client.list_playlists()`` in a new thread and return the exception it raised, if any."""
    errors: list[Exception] = []

    def worker():
        try:
            client.list_playlists()
        except Exception as error:
            errors.append(error)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    return errors[0] if errors else None


def test_client_used_from_another_thread_raises(fake_itunes):
    client = ItunesClient()
    client.list_playlists()  # binds the client to this thread

    assert isinstance(list_playlists_in_worker_thread(client), ItunesClientThreadError)


def test_client_is_bound_to_the_thread_that_first_uses_it(fake_itunes):
    client = ItunesClient()  # created here, but first used in the worker

    assert list_playlists_in_worker_thread(client) is None
    with pytest.raises(ItunesClientThreadError):
        client.list_playlists()
