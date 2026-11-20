"""A folder of album artwork exported from iTunes, so covers can be shown without iTunes running.

The cache has two sides:

* ``get_path`` reads the folder only and never touches iTunes. The sorter uses it while sorting and
  after restoring a saved session.
* ``fill`` exports missing or outdated images through an ``ItunesClient``. The sorter calls it when it
  captures metadata from iTunes (opening or refreshing a playlist), in the worker thread that owns
  the client.

Each song has at most one entry, named after its persistent ID: ``<ID>.jpg``/``.png``/``.bmp``/``.img``
for an image, or ``<ID>.none`` to remember that the song has no artwork.
"""

from collections.abc import Iterable
from pathlib import Path

from itunes_tools.common.config import IMAGE_CACHE_FOLDER
from itunes_tools.common.itunes_client import ItunesClient
from itunes_tools.common.logger import get_logger
from itunes_tools.common.models import Song

logger = get_logger(__name__)

NO_ARTWORK_SUFFIX = ".none"


class ArtworkCache:
    """Album artwork for songs, stored as image files in ``folder``."""

    def __init__(self, folder: Path = IMAGE_CACHE_FOLDER):
        self.folder = folder

    def get_path(self, song: Song) -> Path | None:
        """Return the cached artwork image of a song, without contacting iTunes.

        An outdated image is still returned: an old cover is more useful than none until the next ``fill``.

        :return: The image file, or ``None`` if the song has no artwork or it has not been cached yet.
        """
        entry = self._find_entry(song)
        if entry is None or entry.suffix == NO_ARTWORK_SUFFIX:
            return None
        return entry

    def fill(self, songs: Iterable[Song], client: ItunesClient) -> None:
        """Export artwork for songs whose cache entry is missing or outdated.

        An entry is outdated when the song was modified in iTunes after the entry was written.
        Creates the cache folder if needed.

        :raises ItunesClientError: if exporting fails, for example because a song left the library.
        """
        self.folder.mkdir(parents=True, exist_ok=True)
        exported_count = 0
        for song in songs:
            entry = self._find_entry(song)
            if entry is not None:
                if not self._is_outdated(entry, song):
                    continue
                entry.unlink()

            stem = self.folder / song.id.to_hex()
            # Songs known to have no artwork are recorded without asking iTunes.
            exported = client.export_artwork(song.id, stem) if song.artwork_count > 0 else None
            if exported is None:
                stem.with_name(stem.name + NO_ARTWORK_SUFFIX).touch()
            exported_count += 1
        logger.debug("Updated %d artwork cache entries in %s", exported_count, self.folder)

    def _find_entry(self, song: Song) -> Path | None:
        """Return the song's cache file (image or no-artwork marker), or ``None`` if it has none."""
        # Hex IDs contain no glob special characters. A missing folder simply matches nothing.
        matches = sorted(self.folder.glob(f"{song.id.to_hex()}.*"))
        return matches[0] if matches else None

    @staticmethod
    def _is_outdated(entry: Path, song: Song) -> bool:
        return entry.stat().st_mtime < song.modification_date.timestamp()
