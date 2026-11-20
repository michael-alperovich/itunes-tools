"""Icons recoloured to the palette's text colour, so they stay visible in dark and light themes.

The style's standard media icons (``QStyle.StandardPixmap.SP_Media*``) are drawn in black, which is hard
to tell from a greyed-out (disabled) icon on a dark background. ``text_colored_icon`` repaints them in
the palette's button text colour (white in a dark theme, black in a light one), with a separate disabled
colour.
"""

from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import QStyle

# Large enough to stay sharp when scaled down to toolbar and row button sizes.
TINT_PIXMAP_SIZE = 64


def text_colored_icon(style: QStyle, palette: QPalette, standard_pixmap: QStyle.StandardPixmap) -> QIcon:
    """Return the style's standard icon painted in the palette's button text colour.

    The icon's *Disabled* mode uses the palette's disabled button text colour, so enabled and disabled
    buttons are easy to tell apart.
    """
    shape = style.standardIcon(standard_pixmap)
    enabled_color = palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText)
    disabled_color = palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText)

    icon = QIcon()
    icon.addPixmap(_tinted_pixmap(shape, enabled_color), QIcon.Mode.Normal)
    icon.addPixmap(_tinted_pixmap(shape, enabled_color), QIcon.Mode.Active)  # hovered tool buttons
    icon.addPixmap(_tinted_pixmap(shape, disabled_color), QIcon.Mode.Disabled)
    return icon


def _tinted_pixmap(shape: QIcon, color: QColor) -> QPixmap:
    """Fill the opaque pixels of ``shape`` with ``color``, keeping its transparency (the outline)."""
    pixmap = shape.pixmap(TINT_PIXMAP_SIZE, TINT_PIXMAP_SIZE)
    painter = QPainter(pixmap)
    # SourceIn: paint the colour only where the icon already has pixels.
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()
    return pixmap
