"""Exceptions raised by ``ItunesClient``.

Every exception derives from ``ItunesClientError``, so callers such as a UI can handle all
client failures, including COM failures, with a single ``except ItunesClientError``.
"""

from itunes_tools.common.models import ItunesPersistentID


class ItunesClientError(Exception):
    """Base class for all errors raised by ``ItunesClient``."""


class ItunesComError(ItunesClientError):
    """Raised when a COM call to iTunes fails.

    Common causes: iTunes is not installed, it is showing a modal dialog, or it was closed while
    in use. The original ``pywintypes.com_error`` is available as ``__cause__``.
    """

    def __init__(self, action: str):
        self.action = action
        super().__init__(
            f"iTunes did not respond while trying to {action}. "
            "Make sure iTunes is installed, running, and not showing a dialog."
        )


class ItunesClientThreadError(ItunesClientError):
    """Raised when an ``ItunesClient`` is used from a thread other than the one it is bound to."""

    def __init__(self):
        super().__init__(
            "An ItunesClient can only be used on the thread that first used it. "
            "Create a separate ItunesClient in each worker thread."
        )


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
