import pytest

from itunes_tools.common.exceptions import DuplicatePlaylistNameError, PlaylistNotFoundError
from itunes_tools.common.itunes_client import ItunesClient
from itunes_tools.common.models import ItunesPersistentID, Song


def test_constructor_does_not_dispatch_com(com_dispatch):
    ItunesClient()

    com_dispatch.assert_not_called()


def test_com_app_is_dispatched_once_on_first_use_and_reused(com_dispatch):
    client = ItunesClient()

    client.list_playlists()
    client.list_playlists()

    com_dispatch.assert_called_once_with("iTunes.Application")


def test_custom_prog_id_is_passed_to_dispatch(com_dispatch):
    ItunesClient("Custom.Application").list_playlists()

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


def test_get_playlist_by_id_maps_tracks_to_songs(fake_itunes, make_com_playlist, make_com_track):
    track = make_com_track(10, -20, name="Song", artist="Artist", album="Album", duration=215)
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
            duration=215,
        )
    ]


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
