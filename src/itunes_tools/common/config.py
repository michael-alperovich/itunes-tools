"""File system locations shared by the applications.

Folders listed here are not created on import; the code that writes to a folder creates it when needed.
"""

from pathlib import Path

ITUNES_FOLDER = Path(r"D:\OneDrive\Music\iTunes")
"""The iTunes library folder, the one holding ``iTunes Library.itl``."""

ITUNES_LIBRARY_XML = ITUNES_FOLDER / "iTunes Music Library.xml"
"""The XML export iTunes keeps next to its database; readable without COM."""

ITUNES_LIBRARY_ITL = ITUNES_FOLDER / "iTunes Library.itl"
"""The binary iTunes database. Never written by these applications."""

APP_FOLDER = ITUNES_FOLDER / "itunes-tools"
"""Data written by the itunes-tools applications."""

IMAGE_CACHE_FOLDER = APP_FOLDER / "image-cache"
"""Album artwork exported from iTunes, so the sorter can show covers without iTunes running."""
