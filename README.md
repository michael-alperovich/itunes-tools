## itunes-tools 

This is a project that provides several applications for managing iTunes library.
Applications will be implemented using Python and PySide6 (Qt for Python). WinCom API will be used for communication with iTunes.
Pydantic will b

Applications will include:
- iTunes playlist manual sorter
- iTunes metadata verifier
- iTunes new song importer
- iTunes to Spotify sync (bidirectional)

### iTunes library contract

The applications rely on the iTunes library following the rules below. When a rule is broken, the
applications stop with an error that explains what to fix in iTunes, rather than guessing.
Custom metadata conventions will be documented here as they are introduced.

**Constraints**

- **Unique playlist names.** No two playlists, including folders and smart playlists, may share a
  name. Names are compared exactly, so `Rock` and `rock` are different names.
  Violations raise `DuplicatePlaylistNameError`, which lists the names to rename.
- **Don't edit a playlist while sorting it.** The sorter reads a playlist's songs and their metadata
  from iTunes once, when the playlist is opened, and works from that copy (saved in its YAML file)
  without iTunes. Changes made in iTunes meanwhile are not seen until the playlist is refreshed in
  the sorter. This rule is not checked; committing a sorted playlist that contains a song since
  deleted from iTunes fails with `TrackNotFoundError`, listing the songs to drop by refreshing.

**Custom metadata**

None yet.

### Configuration

| Environment variable     | Default | Purpose                                                   |
|--------------------------|---------|-----------------------------------------------------------|
| `ITUNES_TOOLS_LOG_LEVEL` | `DEBUG` | Log level for the applications (`INFO`, `WARNING`, ...). |

The log level is case-insensitive. An unknown value falls back to `DEBUG` and logs a warning.

File locations are constants in `src/itunes_tools/common/config.py`:

| Constant             | Value                                 | Purpose                                     |
|----------------------|---------------------------------------|---------------------------------------------|
| `ITUNES_FOLDER`      | `D:\OneDrive\Music\iTunes`            | The iTunes library folder                   |
| `ITUNES_LIBRARY_XML` | `ITUNES_FOLDER\iTunes Music Library.xml` | iTunes' XML export of the library           |
| `ITUNES_LIBRARY_ITL` | `ITUNES_FOLDER\iTunes Library.itl`    | The iTunes database (never written)         |
| `APP_FOLDER`         | `ITUNES_FOLDER\itunes-tools`          | Data written by these applications          |
| `IMAGE_CACHE_FOLDER` | `APP_FOLDER\image-cache`              | Album artwork exported from iTunes          |
| `SORTER_FOLDER`      | `APP_FOLDER\sorter`                   | Where the sorter's save dialog opens first  |

The image cache holds one file per song, named after its persistent ID (`<ID>.png`, `.jpg`, ...,
or `<ID>.none` for a song without artwork). It is filled when a playlist's metadata is read from
iTunes and refreshed when a song changes in iTunes. It can be deleted at any time; it is rebuilt
the next time a playlist is opened.

### Playlist sorter

Run it from the repository root (see *Setup* below):

```powershell
uv run --directory src python -m itunes_tools.sorter
```

**Import from iTunes** lists the iTunes playlists, reads the chosen one with all its song metadata and
artwork, and shows its songs. A save dialog then asks where to store the playlist's *sorter file*,
suggesting `SORTER_FOLDER\<playlist name>.yaml`. The sorter file is a YAML dump of the whole playlist
(every song's metadata, in sorting order), so a saved session needs no iTunes to reopen.

The **player** above the list plays the songs' audio files directly (Qt Multimedia), without iTunes. It
shows the song's artwork, title, artist and album, a seek bar with elapsed and remaining time, and
previous / play-pause / next buttons with a volume slider. A speaker icon marks the playing song's row.
When a song ends, the next song in the current sorting order plays and the list scrolls to it; songs
iTunes has no file for are skipped with a message. Each row has two quick play buttons: *Play from the
beginning* and *Play the last 10 seconds* (which then continues into the next song, to hear the
transition). The other toolbar buttons and *Send to a group* are placeholders for now.

### Development

Requires Windows, Python 3.14 and [uv](https://docs.astral.sh/uv/). Run the commands below from the
repository root in PowerShell.

**Setup**

The project's virtual environment lives outside the repository. Set its location once per shell
before running any `uv` command (skip this to use uv's default `.venv` instead):

```powershell
$env:UV_PROJECT_ENVIRONMENT = 'D:\venv\itunes-tools'
uv sync --locked
uv run pre-commit install
```

`pre-commit install` adds a git hook that checks formatting and imports on every commit. It reports
problems without changing files, so fix them with the commands below and commit again.

**Testing**

Tests use pytest and live under `tests/`, mirroring `src/`. Unit tests replace iTunes COM with
fakes from `tests/conftest.py`. Integration tests carry the `itunes` marker, need a real iTunes,
and are skipped by default. They are read-only, but they start iTunes if it is not running.

| Command                     | Runs                                |
|-----------------------------|-------------------------------------|
| `uv run pytest`             | Unit tests only (the default)       |
| `uv run pytest -m itunes`   | iTunes integration tests only       |
| `uv run pytest -m ""`       | All tests                           |

**Formatting and imports**

[Ruff](https://docs.astral.sh/ruff/) formats code and optimizes imports (sorts them and removes
unused ones), configured in `pyproject.toml` to follow PyCharm's defaults with 120-column lines.
To make PyCharm's own *Reformat Code* agree with Ruff, enable Ruff under
**Settings → Python → Tools → Ruff**.

| Command                                | Does                                          |
|----------------------------------------|-----------------------------------------------|
| `uv run ruff format .`                 | Format all files                              |
| `uv run ruff check --fix .`            | Sort imports and remove unused ones           |
| `uv run ruff format --check --diff .`  | Show formatting problems without fixing them  |
| `uv run ruff check .`                  | Show import problems without fixing them      |
| `uv run pre-commit run --all-files`    | Run the commit hooks on every tracked file    |
