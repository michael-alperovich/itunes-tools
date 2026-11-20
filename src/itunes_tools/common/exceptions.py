"""Exceptions raised by ``ItunesClient``.

Every exception derives from ``ItunesClientError``, so callers such as a UI can handle all
client failures with a single ``except ItunesClientError``.
"""

from itunes_tools.common.models import ItunesPersistentID


class ItunesClientError(Exception):
    """Base class for all errors raised by ``ItunesClient``."""


class PlaylistNotFoundError(ItunesClientError):
    """Raised when no playlist has the requested persistent ID."""

    def __init__(self, persistent_id: ItunesPersistentID):
        self.persistent_id = persistent_id
        super().__init__(f"Playlist with ID {persistent_id.to_hex()} not found")


class DuplicatePlaylistNameError(ItunesClientError):
    """Raised when several playlists share a name, which the iTunes library contract forbids.

    See the *iTunes library contract* section in ``README.md``.
    """

    def __init__(self, duplicate_names: list[str]):
        self.duplicate_names = duplicate_names
        names = ", ".join(repr(name) for name in duplicate_names)
        super().__init__(f"Playlist names must be unique. Rename these playlists in iTunes: {names}")
