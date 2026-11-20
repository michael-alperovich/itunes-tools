"""Which song the sorter plays next: the following or preceding playable song in sorting order.

A song is playable when iTunes knows its file (``Song.location`` is set). Songs without one are skipped.
Plain functions over the song list, so they are tested without Qt Multimedia.
"""

from collections.abc import Sequence

from itunes_tools.common.models import Song


def is_playable(song: Song) -> bool:
    """Return whether the song has a local file to play."""
    return song.location is not None


def next_playable_index(songs: Sequence[Song], after_index: int) -> int | None:
    """Return the index of the first playable song after ``after_index``, or ``None`` at the end.

    Pass ``-1`` to search from the first song.
    """
    for index in range(after_index + 1, len(songs)):
        if is_playable(songs[index]):
            return index
    return None


def previous_playable_index(songs: Sequence[Song], before_index: int) -> int | None:
    """Return the index of the last playable song before ``before_index``, or ``None`` at the start."""
    for index in range(min(before_index, len(songs)) - 1, -1, -1):
        if is_playable(songs[index]):
            return index
    return None
