"""The sorter's save file: a YAML document holding a full dump of the playlist being sorted.

The file carries every song's metadata, so a saved session can be reopened without iTunes. The order of
``playlist.tracks`` is the sorting order. Album artwork is not included; see ``ArtworkCache``.
"""

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from itunes_tools.common.config import SORTER_FOLDER
from itunes_tools.common.models import Playlist

SORTER_FILE_SUFFIX = ".yaml"

# Characters Windows does not allow in file names.
_FORBIDDEN_FILE_NAME_CHARACTERS = re.compile(r'[<>:"/\\|?*]')


class SorterFile(BaseModel):
    """The content of a sorter file."""

    format_version: int = Field(default=1, description="Version of the file layout, raised on incompatible changes.")
    playlist: Playlist = Field(description="The playlist being sorted; its tracks are in sorting order.")


def save_sorter_file(sorter_file: SorterFile, path: Path) -> None:
    """Write a sorter file as YAML, replacing any existing file at ``path``.

    Fields keep their model order (no key sorting) so the file reads top to bottom like the model.
    """
    content = yaml.safe_dump(sorter_file.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
    path.write_text(content, encoding="utf-8")


def load_sorter_file(path: Path) -> SorterFile:
    """Read a sorter file written by ``save_sorter_file``.

    :raises pydantic.ValidationError: if the content does not match ``SorterFile``.
    :raises yaml.YAMLError: if the file is not valid YAML.
    """
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SorterFile.model_validate(content)


def suggested_sorter_file_path(playlist_name: str, folder: Path = SORTER_FOLDER) -> Path:
    """Return ``<folder>/<playlist name>.yaml``, the path the save dialog proposes first.

    Characters Windows forbids in file names are replaced with ``_``.
    """
    file_stem = _FORBIDDEN_FILE_NAME_CHARACTERS.sub("_", playlist_name)
    return folder / (file_stem + SORTER_FILE_SUFFIX)
