"""Album artwork as Qt pixmaps, read from the ``ArtworkCache`` (never from iTunes)."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap

from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.common.models import Song

PLACEHOLDER_COLOR = QColor("lightgray")


def load_artwork_pixmap(artwork_cache: ArtworkCache, song: Song, size: int) -> QPixmap:
    """Return the song's artwork scaled to fit a ``size`` × ``size`` square, keeping its aspect ratio.

    Needs a ``QApplication``. Loading reads the image file each time; callers showing many songs should
    keep the result.

    :return: The scaled artwork, or a light grey ``size`` × ``size`` square when the song has no
        artwork, it is not cached yet, or the file cannot be read.
    """
    path = artwork_cache.get_path(song)
    pixmap = QPixmap(str(path)) if path is not None else QPixmap()
    if pixmap.isNull():
        placeholder = QPixmap(size, size)
        placeholder.fill(PLACEHOLDER_COLOR)
        return placeholder
    return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
