import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QStyle

from itunes_tools.common.widgets.icons import text_colored_icon

pytestmark = pytest.mark.usefixtures("qt_application")


def opaque_colors(icon: QIcon, mode: QIcon.Mode) -> set[str]:
    """Return the colours of the icon's visible pixels."""
    image = icon.pixmap(32, 32, mode).toImage()
    return {
        image.pixelColor(x, y).name()
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() == 255
    }


def test_icon_is_painted_in_the_text_colour_and_the_disabled_text_colour():
    palette = QPalette()
    palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, QColor(Qt.GlobalColor.white))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#808080"))

    icon = text_colored_icon(QApplication.style(), palette, QStyle.StandardPixmap.SP_MediaPlay)

    assert opaque_colors(icon, QIcon.Mode.Normal) == {"#ffffff"}
    assert opaque_colors(icon, QIcon.Mode.Disabled) == {"#808080"}
