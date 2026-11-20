# 001 – Finish ItunesClient for the sorter

**Mode:** Default (agent implements, developer reviews `git diff`; nothing committed).

**Status:** Ready for review (tracked in [README.md](README.md)).

## Context

The sorter (issues UC-1 … UC-8, label `sorter`) needs more from `ItunesClient` than it offers today
(`list_playlists`, `get_playlist_by_id`, a `Song` with name/artist/album/duration):

| Use case | Needs from the common module |
|---|---|
| UC-1 open playlist | already covered; this is the *metadata capture* step |
| UC-2 save/restore YAML | `Song`/`Playlist` must round-trip through a JSON-mode model dump; refresh = re-read the playlist |
| UC-3 commit to iTunes | create a new playlist with ordered tracks, reject a taken name |
| UC-4 list rows | album cover served from a local cache with no iTunes call; title, artist, album |
| UC-5/6 player | file path of each song — playback is done by Qt's `QMediaPlayer`, not iTunes |
| UC-7/8 groups, drag-drop | nothing (app-side state) |

**Offline-sorting design (developer decision).** iTunes is opened only to capture metadata: loading a
playlist (UC-1), an explicit *refresh*, and committing (UC-3). The sorting session YAML (UC-2) holds the
full song metadata — essentially `Song.model_dump(mode="json")` — minus images, which live in the
artwork cache, filled at capture time. Sorting, restoring a YAML and showing covers need no iTunes.
Because of this, the library contract gains a rule: **don't edit a playlist in iTunes while it is being
sorted**; if it changed anyway, use refresh.

Other decisions: Qt plays audio (so no iTunes playback API); artwork is exported through COM into our
own cache folder (iTunes' `Album Artwork/Cache/*.itc2` is proprietary and only covers ~1000 tracks).

## Scope

In: `config.py`, richer serializable `Song`, artwork export + offline cache, `create_playlist`, new
exceptions, unit tests, read-only integration tests, README updates (config + contract rule).
Out: the sorter app, Qt UI, the YAML file itself and refresh merge logic (UC-2 belongs to the app —
the client only supplies `get_playlist_by_id`), playlist folders/smart-playlist filtering, renaming
files (never).

## Approach

### 1. `common/config.py` (new)
Plain `pathlib.Path` constants, documented in README *Configuration*:
```python
ITUNES_FOLDER = Path(r"D:\OneDrive\Music\iTunes")
ITUNES_LIBRARY_XML = ITUNES_FOLDER / "iTunes Music Library.xml"
ITUNES_LIBRARY_ITL = ITUNES_FOLDER / "iTunes Library.itl"
APP_FOLDER = ITUNES_FOLDER / "itunes-tools"
IMAGE_CACHE_FOLDER = APP_FOLDER / "image-cache"
```
Folders are created on demand by the code that writes to them (the cache), not at import.

### 2. `Song` model (`models.py`)
Add, read from `IITTrack` / `IITFileOrCDTrack`:
- `album_artist`, `genre`, `year`, `track_number`, `disc_number`
- `date_added`, `modification_date` (`datetime`; `modification_date` drives cache invalidation)
- `location: Path | None` — `None` when the file is missing or the track has no file (URL/cloud tracks
  lack the `Location` property; read it defensively)
- `artwork_count: int` — lets the UI skip the cache lookup for tracks without art

Shared builder `ItunesClient._song_from_com(track_com)` replaces the inline `Song(...)` in
`get_playlist_by_id`.

Serialization contract (for the app's YAML): `Playlist.model_validate(playlist.model_dump(mode="json"))`
equals the original — datetimes as ISO strings, `location` as a string, IDs as `{high, low}`. COM
datetimes (`pywintypes.datetime`) are converted to plain `datetime` in `_song_from_com` so dumps are
clean. Covered by a round-trip unit test.

### 3. Artwork
- `ItunesClient.export_artwork(track_id, destination_stem: Path) -> Path | None` — looks up the track,
  takes `Artwork.Item(1)`, picks the extension from `Artwork.Format` (1 jpg, 2 png, 3 bmp, else `.img`;
  Qt detects format by content anyway), calls `SaveArtworkToFile(str(absolute path))`, returns the path,
  or `None` if the track has no artwork. Only COM-touching part.
- `common/artwork_cache.py` (new) — `ArtworkCache(folder=IMAGE_CACHE_FOLDER)`, split into an offline
  read side and a capture-time fill side:
  - `get_path(song) -> Path | None` — **never touches iTunes**; returns the cached file or `None`
    (no art, or not cached yet). Used while sorting and after restoring a YAML.
  - `fill(songs, client) -> None` — called at capture/refresh time (in the worker thread that owns the
    `ItunesClient`); exports art for songs whose entry is missing or stale.
  - cache file name `<song.id.to_hex()>.<ext>`; a `<hex>.none` marker records "no artwork" so
    `fill` doesn't ask iTunes again;
  - an entry is stale when its mtime < `song.modification_date` (the date in the YAML, updated by
    refresh);
  - per-track keying (simple, correct when one album has mixed art; disk cost is acceptable).

### 4. Client operations (`itunes_client.py`)
- Refresh needs nothing new: the app calls `get_playlist_by_id` again and merges (app-side).
- `create_playlist(name: str, track_ids: list[ItunesPersistentID]) -> Playlist` — (UC-3)
  1. reject blank name (`ValueError`) and a name already in `list_playlists()` → `PlaylistNameTakenError(name)`;
  2. resolve every track first via `LibraryPlaylist.Tracks.ItemByPersistentID`, raising
     `TrackNotFoundError` listing all missing IDs *before* anything is created (a song deleted from
     iTunes since capture);
  3. `CreatePlaylist(name)`, then `AddTrack` in order; return `get_playlist_by_id(new_id)`.
  If adding fails midway, log the partially created playlist's name in the error (no automatic delete).

### 5. Exceptions (`exceptions.py`)
`PlaylistNameTakenError(name)` and `TrackNotFoundError(ids)`, both `ItunesClientError` subclasses with
messages telling the user what to do.

### 6. Tests and docs
- `tests/conftest.py`: extend `make_com_track` (new fields, optional `Location`, fake `Artwork`
  collection whose `SaveArtworkToFile` writes bytes), add `LibraryPlaylist`, `CreatePlaylist`, and
  `AddTrack` to the fakes.
- `tests/common/test_models.py`: `Playlist` JSON-mode dump/validate round trip, incl. `location=None`.
- `tests/common/test_itunes_client.py`: new fields, missing location, datetime conversion,
  `create_playlist` happy path / taken name / blank name / missing track creates nothing,
  `export_artwork` formats and no-art case.
- `tests/common/test_artwork_cache.py` (new, `tmp_path`): `get_path` hit / miss / `.none` → `None`
  without a client; `fill` exports missing, re-exports stale, skips fresh, writes `.none`, creates folder.
- `tests/common/test_config.py`: derived paths.
- Integration (`-m itunes`, still read-only): new `Song` fields parse from real COM and round-trip;
  `export_artwork` into `tmp_path` produces a readable image.
- README: *Configuration* table gains the paths and the image cache; *iTunes library contract* gains
  "Don't edit a playlist while sorting it" (the sorter works from captured metadata; use refresh if
  it changed). Unlike the other rules this one isn't enforced by an error — the commit step reports
  missing tracks via `TrackNotFoundError`.
- CLAUDE.md *Current state*: list `config.py` and `artwork_cache.py`.

## Steps
1. Spike `spikes/sorter_com_probe.py` (read-only + one throwaway playlist that the script deletes):
   confirm COM types of `DateAdded`/`ModificationDate`, `Location` on non-file tracks, `Artwork.Format`
   values, `SaveArtworkToFile` path rules, and that `AddTrack` works on `CreatePlaylist`'s result
   under dynamic dispatch. Adjust the design if anything differs (and report it).
2. `config.py` + test.
3. `Song` fields + `_song_from_com` + fakes + round-trip test.
4. Exceptions, `create_playlist` + tests.
5. `export_artwork` + `ArtworkCache` + tests.
6. Integration tests, README (config + contract rule), CLAUDE.md, plan index.

## Acceptance criteria
- `Song` exposes the fields above; `get_playlist_by_id` fills them from COM.
- A `Playlist` survives `model_dump(mode="json")` → `model_validate` unchanged.
- `ArtworkCache.get_path` works with no `ItunesClient` at all; `fill` exports only missing or stale
  entries (stale = track modified after caching).
- `create_playlist` creates a playlist with tracks in the given order, and rejects a taken or blank
  name or unknown track without creating anything.
- README documents the config paths, the image cache, and the "don't edit while sorting" rule.
- All paths come from `common/config.py`.

## Validation
- `uv run pytest`, `uv run ruff format --check --diff .`, `uv run ruff check .` (with
  `UV_PROJECT_ENVIRONMENT=D:\venv\itunes-tools`).
- `uv run pytest -m itunes` against real iTunes (read-only).
- Manual (writes to the library): run the spike's create-playlist check, confirm the playlist and order
  in iTunes, then let the script delete it. Not automated because integration tests must stay read-only.

## Open questions
- None blocking. Possible later additions (not in scope): filtering folders/smart playlists out of the
  UC-1 list; album-level artwork sharing if per-track cache size becomes a problem.

## Amendments

### 2026-11-19 – Findings from the COM spike (step 1)

- **What changed:** `ItunesClient` calls `win32com.client.CastTo(..., "IITFileOrCDTrack")` before
  reading `AlbumArtist`/`Location` (only for file and CD tracks, `Kind` 1 and 2), and
  `CastTo(..., "IITUserPlaylist")` on the result of `CreatePlaylist` before `AddTrack`. Tests replace
  `CastTo` with a new `com_cast_to` fixture.
- **Why:** pywin32's generated type library cache (in `%TEMP%\gen_py`) makes COM objects arrive as
  wrappers of their declared interface, which hide members of derived interfaces. `dynamic.Dispatch`
  does not help: child objects still come back early-bound. Without the cache, `CastTo` generates it.
- **Other confirmed details:** COM dates are local-time `pywintypes.datetime`, stored as plain UTC
  `datetime`; `SaveArtworkToFile` rejects forward slashes, so an absolute Windows path is passed; the
  library holds only file tracks today (825), 101 without artwork, formats PNG and JPEG.
- **Test doubles:** `conftest.py` cannot be imported under `--import-mode=importlib`, so `FakeArtwork`
  is exposed through a `make_artwork` fixture.
- **Effect on acceptance criteria / validation:** none.

### 2026-11-19 – Small additions within scope

- `ArtworkCache.fill` writes the `.none` marker without calling iTunes when `song.artwork_count == 0`,
  and treats an outdated `.none` marker like an outdated image (re-checks it).
- `get_path` still returns an outdated image (an old cover beats none until the next `fill`).
