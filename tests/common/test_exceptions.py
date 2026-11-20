import pytest

from itunes_tools.common.exceptions import DuplicatePlaylistNameError, ItunesClientError, PlaylistNotFoundError
from itunes_tools.common.models import ItunesPersistentID


@pytest.mark.parametrize(
    "error",
    [
        PlaylistNotFoundError(ItunesPersistentID(high=1, low=2)),
        DuplicatePlaylistNameError(["Rock"]),
    ],
    ids=lambda error: type(error).__name__,
)
def test_client_errors_can_be_caught_by_base_class(error):
    with pytest.raises(ItunesClientError):
        raise error


def test_duplicate_playlist_name_error_lists_names_in_message():
    error = DuplicatePlaylistNameError(["Blues", "Rock"])

    assert str(error) == "Playlist names must be unique. Rename these playlists in iTunes: 'Blues', 'Rock'"
