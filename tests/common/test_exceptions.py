import pytest

from itunes_tools.common.exceptions import (
    DuplicatePlaylistNameError,
    ItunesClientError,
    ItunesClientThreadError,
    ItunesComError,
    PlaylistNameTakenError,
    PlaylistNotFoundError,
    TrackNotFoundError,
)
from itunes_tools.common.models import ItunesPersistentID


@pytest.mark.parametrize(
    "error",
    [
        ItunesComError("list playlists"),
        ItunesClientThreadError(),
        PlaylistNotFoundError(ItunesPersistentID(high=1, low=2)),
        DuplicatePlaylistNameError(["Rock"]),
        PlaylistNameTakenError("Rock"),
        TrackNotFoundError([ItunesPersistentID(high=1, low=2)]),
    ],
    ids=lambda error: type(error).__name__,
)
def test_client_errors_can_be_caught_by_base_class(error):
    with pytest.raises(ItunesClientError):
        raise error


def test_com_error_message_names_the_action():
    assert "while trying to list playlists" in str(ItunesComError("list playlists"))


def test_duplicate_playlist_name_error_lists_names_in_message():
    error = DuplicatePlaylistNameError(["Blues", "Rock"])

    assert str(error) == "Playlist names must be unique. Rename these playlists in iTunes: 'Blues', 'Rock'"


def test_track_not_found_error_lists_hex_ids_in_message():
    error = TrackNotFoundError([ItunesPersistentID(high=1, low=2), ItunesPersistentID(high=0, low=-1)])

    assert "0000000100000002, 00000000FFFFFFFF" in str(error)
