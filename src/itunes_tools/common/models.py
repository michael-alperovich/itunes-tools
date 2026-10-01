from pydantic import BaseModel, Field


class ItunesPersistentID(BaseModel):
    high: int = Field(description="The high 32 bits of the unique identifier of the iTunes persistent object.")
    low: int = Field(description="The low 32 bits of the unique identifier of the iTunes persistent object.")

    def to_hex(self):
        combined = ((self.high & 0xFFFFFFFF) << 32) | (self.low & 0xFFFFFFFF)
        return f"{combined:016X}"


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
