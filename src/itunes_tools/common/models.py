from pydantic import BaseModel, Field

from itunes_tools.common.utils import to_persistent_id


class ItunesPersistentID(BaseModel):
    high: int = Field(description="The high 32 bits of the unique identifier of the iTunes persistent object.")
    low: int = Field(description="The low 32 bits of the unique identifier of the iTunes persistent object.")

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
