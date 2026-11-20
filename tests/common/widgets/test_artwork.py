import pytest
from PySide6.QtGui import QColor, QImage

from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.common.widgets.artwork import PLACEHOLDER_COLOR, load_artwork_pixmap

pytestmark = pytest.mark.usefixtures("qt_application")


def test_returns_a_placeholder_square_when_artwork_is_not_cached(tmp_path, make_song):
    pixmap = load_artwork_pixmap(ArtworkCache(tmp_path), make_song(1), 32)

    assert (pixmap.width(), pixmap.height()) == (32, 32)
    assert pixmap.toImage().pixelColor(0, 0) == PLACEHOLDER_COLOR


def test_scales_cached_artwork_keeping_its_aspect_ratio(tmp_path, make_song):
    image = QImage(200, 100, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    assert image.save(str(tmp_path / "0000000000000001.png"))

    pixmap = load_artwork_pixmap(ArtworkCache(tmp_path), make_song(1), 64)

    assert (pixmap.width(), pixmap.height()) == (64, 32)
