from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from itunes_tools.common.utils import INT32_MAX, INT32_MIN, to_persistent_id


class ItunesPersistentID(BaseModel):
    """Persistent ID of an iTunes object, as the signed 32-bit halves COM uses.

    Immutable and hashable, so it can be used as a dict key or in a set.
    """

    model_config = ConfigDict(frozen=True)

    high: int = Field(
        ge=INT32_MIN,
        le=INT32_MAX,
        description="The high 32 bits of the unique identifier of the iTunes persistent object.",
    )
    low: int = Field(
        ge=INT32_MIN,
        le=INT32_MAX,
        description="The low 32 bits of the unique identifier of the iTunes persistent object.",
    )

    def to_hex(self) -> str:
        """Return the 16-digit uppercase hex form, as used in ``iTunes Library.xml``."""
        return to_persistent_id(self.high, self.low)


class Song(BaseModel):
    """Metadata of one iTunes track, captured once so the sorter can work without iTunes.

    Survives ``model_dump(mode="json")`` followed by ``model_validate`` unchanged, which is how the
    sorter saves songs to its YAML files. Album artwork is not included; see ``ArtworkCache``.
    """

    id: ItunesPersistentID = Field(description="The unique identifier of the song.")
    name: str = Field(description="The name of the song.")
    artist: str = Field(description="The artist of the song.")
    album: str = Field(description="The album of the song.")
    album_artist: str = Field(description="The album artist; empty when not set or the track has no file.")
    genre: str = Field(description="The genre of the song; empty when not set.")
    year: int = Field(ge=0, description="The release year; 0 when not set.")
    track_number: int = Field(ge=0, description="The track number on its disc; 0 when not set.")
    disc_number: int = Field(ge=0, description="The disc number; 0 when not set.")
    duration: int = Field(description="The duration of the song in seconds.")
    date_added: datetime = Field(description="When the song was added to the library, in UTC.")
    modification_date: datetime = Field(
        description="When the song's file or metadata last changed, in UTC. Used to refresh cached artwork."
    )
    location: Path | None = Field(
        description="The audio file, or None when iTunes cannot find it or the track has no local file."
    )
    artwork_count: int = Field(ge=0, description="The number of artwork images attached to the song.")


class Playlist(BaseModel):
    id: ItunesPersistentID = Field(description="The unique identifier of the playlist.")
    name: str = Field(description="The name of the playlist.")
    tracks: list[Song] = Field(description="The tracks in the playlist.")
