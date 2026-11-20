"""The sorter's save file: a YAML document holding a full dump of the playlist being sorted.

The file carries every song's metadata, so a saved session can be reopened without iTunes. The order of
``playlist.tracks`` is the sorting order, which is also the order committed to iTunes. Groups (UC-7) are
stored separately as ranges of consecutive tracks, so ``playlist.tracks`` stays one flat list and files
written before groups existed (format version 1) still load. Album artwork is not included; see
``ArtworkCache``.
"""

import re
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field, model_validator

from itunes_tools.common.config import SORTER_FOLDER
from itunes_tools.common.models import Playlist

SORTER_FILE_SUFFIX = ".yaml"

# Characters Windows does not allow in file names.
_FORBIDDEN_FILE_NAME_CHARACTERS = re.compile(r'[<>:"/\\|?*]')


class GroupRange(BaseModel):
    """A group of the sorting list, as the consecutive tracks of ``playlist.tracks`` it holds.

    An empty group has ``track_count`` 0 and sits just before the track at ``first_track``
    (or at the end of the list when ``first_track`` equals the number of tracks).
    """

    name: str = Field(min_length=1, description="The group's name, unique within the file.")
    first_track: int = Field(ge=0, description="Index in playlist.tracks of the group's first song.")
    track_count: int = Field(ge=0, description="The number of songs in the group.")


class SorterFile(BaseModel):
    """The content of a sorter file."""

    format_version: int = Field(default=2, description="Version of the file layout, raised on incompatible changes.")
    playlist: Playlist = Field(description="The playlist being sorted; its tracks are in sorting order.")
    groups: list[GroupRange] = Field(
        default=[], description="The groups, top to bottom; their tracks are ranges of playlist.tracks."
    )

    @model_validator(mode="after")
    def _check_groups(self) -> Self:
        """Reject groups that repeat a name, overlap, are out of order, or reach past the last track."""
        names = [group.name for group in self.groups]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"group names must be unique; repeated: {duplicates}")

        previous_end = 0
        for group in self.groups:
            if group.first_track < previous_end:
                raise ValueError(f"group {group.name!r} overlaps or precedes the previous group")
            previous_end = group.first_track + group.track_count
            if previous_end > len(self.playlist.tracks):
                raise ValueError(f"group {group.name!r} reaches past the last track")
        return self


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
