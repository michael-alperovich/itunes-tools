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
    id: ItunesPersistentID = Field(description="The unique identifier of the song.")
    name: str = Field(description="The name of the song.")
    artist: str = Field(description="The artist of the song.")
    album: str = Field(description="The album of the song.")
    duration: int = Field(description="The duration of the song in seconds.")


class Playlist(BaseModel):
    id: ItunesPersistentID = Field(description="The unique identifier of the playlist.")
    name: str = Field(description="The name of the playlist.")
    tracks: list[Song] = Field(description="The tracks in the playlist.")
