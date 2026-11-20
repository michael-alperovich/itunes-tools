"""The items of the sorting list: songs and groups of songs (UC-7), without Qt.

The sorting list is a list of top-level items, each a song or a ``SongGroup``. Groups hold songs only;
they are never nested. Reading the list top to bottom, with each group's songs in place, gives the true
playlist order (``flatten``), which the player follows and *Commit to iTunes* sends.
"""

from pydantic import BaseModel, Field

from itunes_tools.common.models import Playlist, Song
from itunes_tools.sorter.sorter_file import GroupRange, SorterFile

# Seasons in calendar order. Winter is named after the year holding most of its months, so
# Winter 2017 is December 2016 – February 2017 and opens the year 2017.
SEASONS = ("Winter", "Spring", "Summer", "Fall")


class SongGroup(BaseModel):
    """A named container of songs in the sorting list. Groups exist only in the sorter, not in iTunes."""

    name: str = Field(min_length=1, description="The group's name, unique within the sorting list.")
    songs: list[Song] = Field(default=[], description="The group's songs, in sorting order.")


SortingItem = Song | SongGroup


def flatten(items: list[SortingItem]) -> list[Song]:
    """Return every song in sorting order: top-level songs and group contents, top to bottom."""
    songs: list[Song] = []
    for item in items:
        if isinstance(item, SongGroup):
            songs.extend(item.songs)
        else:
            songs.append(item)
    return songs


def season_group_names(first_year: int, last_year: int) -> list[str]:
    """Return the season names from Winter ``first_year`` to Fall ``last_year``, oldest first.

    For example ``2017, 2018`` gives ``Winter 2017, Spring 2017, Summer 2017, Fall 2017, Winter 2018, …``.
    An empty list when ``last_year`` is before ``first_year``.
    """
    return [f"{season} {year}" for year in range(first_year, last_year + 1) for season in SEASONS]


def items_from_sorter_file(sorter_file: SorterFile) -> list[SortingItem]:
    """Rebuild the sorting list from a sorter file: its tracks, with each group's range gathered into a group."""
    tracks = sorter_file.playlist.tracks
    items: list[SortingItem] = []
    next_track = 0
    for group in sorter_file.groups:
        # Songs between the previous group and this one are at the top level.
        items.extend(tracks[next_track : group.first_track])
        next_track = group.first_track + group.track_count
        items.append(SongGroup(name=group.name, songs=tracks[group.first_track : next_track]))
    items.extend(tracks[next_track:])
    return items


def sorter_file_from_items(playlist: Playlist, items: list[SortingItem]) -> SorterFile:
    """Return the sorter file for ``playlist`` with the songs and groups of ``items``.

    ``playlist`` provides the id and name; its tracks are replaced by the flattened ``items``.
    """
    groups: list[GroupRange] = []
    track_count = 0
    for item in items:
        if isinstance(item, SongGroup):
            groups.append(GroupRange(name=item.name, first_track=track_count, track_count=len(item.songs)))
            track_count += len(item.songs)
        else:
            track_count += 1
    return SorterFile(playlist=playlist.model_copy(update={"tracks": flatten(items)}), groups=groups)
