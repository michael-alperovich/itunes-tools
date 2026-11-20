# 002 – Sorter MVP: main window, song list, import from iTunes

**Mode:** Default throughout (agent implements, developer reviews `git diff`; nothing committed).

**Status:** Ready for review (tracked in [README.md](README.md)).

**Issues:** UC-1 (#1, open a playlist from iTunes), UC-4 (#4, view songs as a list). Lays out space for
UC-5 (player), UC-6 (quick play actions) and UC-7 (groups) without implementing them.

## Purpose

Build the first runnable sorter: a main window with a toolbar, a player placeholder, a song list and a
messages pane. One action works end to end: **Import from iTunes** — pick a playlist, capture its songs
(metadata + artwork) from iTunes, show them as rows, and save a sorter file for the playlist to a
location the user picks.

## Scope

**In**

- Window layout (top to bottom):
  ```
  | Import from iTunes | Open | Save | Add group | Commit to iTunes |   toolbar: icons + tooltips
  |                         player (placeholder)                   |
  | artwork | name / artist – album              | ▶  ⏭10s  ➜group |   one row per song
  | messages                                                       |
  ```
- Toolbar actions with icons and tooltips. Only *Import from iTunes* is enabled; the others are present
  but disabled.
- Song rows: artwork, title, artist, album (UC-4), in playlist order, plus three per-row buttons that are
  drawn but do nothing yet: *Play from beginning*, *Play last 10 seconds* (UC-6), *Send to group* (UC-7).
- A sorter file per imported playlist, in YAML: the full `Playlist` model dump (as plan 001 designed),
  whose track order is the sorting order. Groups are left for UC-7. A file picker chooses where to save;
  it opens in the app's sorter folder with `<playlist name>.yaml` suggested.
- A messages pane showing progress and errors (iTunes not running, duplicate playlist names, …).

**Out**

- Opening/saving sorter files from the UI (*Open*, *Save* stay disabled; UC-2), commit (UC-3), playback
  (UC-5/6), groups (UC-7), drag and drop (UC-8), refresh/merge of an already imported playlist.
- Restoring a window from a sorter file (needs *Open*).

## Approach

### 1. Sorter file — `sorter/sorter_file.py` (new)

Follows plan 001's design: the file is the full model dump, readable without iTunes.

- New constant in `common/config.py`: `SORTER_FOLDER = APP_FOLDER / "sorter"`, the folder the save
  dialog opens in. The image cache stays where it is.

- `SorterFile` Pydantic model: `format_version: int = 1`, `playlist: Playlist`. The order of
  `playlist.tracks` is the sorting order. Groups get added in UC-7.
- `save_sorter_file(sorter_file, path) -> None` writes
  `yaml.safe_dump(sorter_file.model_dump(mode="json"), sort_keys=False, allow_unicode=True)`.
- `load_sorter_file(path) -> SorterFile` validates with `SorterFile.model_validate(yaml.safe_load(...))`.
  Not used by the UI yet (*Open* is UC-2), but it makes the round trip testable.
- `suggested_sorter_file_path(playlist_name, folder=SORTER_FOLDER) -> Path` builds
  `<folder>/<playlist name>.yaml`, replacing characters Windows forbids in file names (`<>:"/\|?*`)
  with `_`. Only a suggestion for the file picker.
- Adds `pyyaml` as a direct dependency (it is already in `uv.lock` through `pre-commit`, dev only).

### 2. iTunes worker — `sorter/itunes_worker.py` (new)

- Plain function `capture_playlist(client, playlist_id, artwork_cache) -> Playlist`:
  `get_playlist_by_id`, then `artwork_cache.fill`. Unit-testable with the existing COM fakes, no Qt.
- `ItunesWorker(QObject)` living in one dedicated `QThread` for the app's lifetime. It creates its
  `ItunesClient` lazily on first use *inside that thread*, which satisfies the client's thread binding.
  Slots `listPlaylists()` and `importPlaylist(playlist_id)`; signals `playlistsListed(list[str] / dict)`,
  `playlistImported(Playlist)`, `failed(str)`, `progress(str)`. Cross-thread signal/slot connections are
  queued by Qt, so the UI never blocks on COM.
- Shut the thread down cleanly on window close (`quit()` + `wait()`).

### 3. Main window — `sorter/main_window.py` (developer's existing file, extended)

- `QToolBar` with `QAction`s; icons from `self.style().standardIcon(QStyle.StandardPixmap.…)`
  (always available on Windows, unlike theme icons), `setToolTip`/`setStatusTip` for hover text.
- Central widget: `QVBoxLayout` of player placeholder (`QFrame`, fixed height, “Player — coming in
  UC-5” label), song list view (stretch), messages pane (read-only `QPlainTextEdit`, a few lines high).
- Import flow: action → worker lists playlists → `QInputDialog.getItem` with sorted names → worker
  imports → model shows the songs → `QFileDialog.getSaveFileName` opening at
  `suggested_sorter_file_path(...)` (creating `SORTER_FOLDER` first so the picker can open there), filter
  `*.yaml` → `save_sorter_file` → message with the file path. The file dialog asks before overwriting
  an existing file; cancelling leaves the songs shown and reports "not saved". The action is disabled
  while a job runs.

### 4. Song list — `sorter/song_list.py` (new)

Model/view rather than `QListWidget.setItemWidget`: per-row widgets are simpler today but scale poorly
and fight drag and drop (UC-8) and groups (UC-7), which a model/view design handles naturally.

- `SongListModel(QAbstractListModel)` holding `list[Song]`; `DisplayRole` → title,
  `DecorationRole` → artwork `QPixmap` from `ArtworkCache.get_path` (scaled, memoized per song ID;
  placeholder icon when `None`), custom roles for artist and album.
- `SongRowDelegate(QStyledItemDelegate)`: `paint` draws artwork, title on one line, artist – album
  below, and three button icons right-aligned; `sizeHint` gives a fixed row height. Button hit-testing
  (`editorEvent`) is deferred to UC-6/7; for now the buttons are drawn in a disabled state.

### 5. Tests and docs

- `tests/common/test_config.py`: `SORTER_FOLDER` derived from `APP_FOLDER`.
- `tests/sorter/test_sorter_file.py`: save/load round trip equals the original (incl. `location=None`
  and datetimes), track order preserved, suggested path replaces forbidden characters.
- `tests/sorter/test_itunes_worker.py`: `capture_playlist` with the COM fakes returns the playlist and fills the artwork cache.
- `tests/sorter/test_song_list.py`: `rowCount`, `data` for display/custom roles (needs a
  `QApplication` fixture; no new test dependency).
- README: *Configuration* gains `SORTER_FOLDER`; describe sorter files; how to run the sorter
  (`uv run python -m itunes_tools.sorter`). CLAUDE.md *Current state*: the sorter app exists.

## Steps

1. `SORTER_FOLDER`, `SorterFile` + YAML save/load + suggested path + `pyyaml` dependency + tests.
2. Window skeleton: toolbar (icons, tooltips, disabled actions), player placeholder, messages pane.
3. `SongListModel` + `SongRowDelegate`, shown with a few hard-coded songs.
4. `ItunesWorker` + `capture_playlist` + import flow wired to the window.
5. README, CLAUDE.md, plan index; manual run against iTunes.

## Acceptance criteria

- `uv run --directory src python -m itunes_tools.sorter` opens the window with the layout above; toolbar icons show
  tooltips on hover; only *Import from iTunes* is enabled.
- Import lists iTunes playlists, loads the chosen one in iTunes order, shows artwork, title, artist and
  album per row, with three inert action buttons per row.
- The UI stays responsive during the import; failures appear in the messages pane, not as a crash.
- After import, the image cache holds artwork for every song of the playlist.
- A file picker then opens in `SORTER_FOLDER` suggesting `<playlist>.yaml`; the saved YAML holds the
  full playlist dump (tracks in order) and loads back into an equal `SorterFile`. Cancelling saves nothing.
- Unit tests above pass; formatting and import checks pass.

## Validation

- `uv run pytest`, `uv run ruff format --check --diff .`, `uv run ruff check .`
  (with `UV_PROJECT_ENVIRONMENT=D:\venv\itunes-tools`).
- Manual, with iTunes: import a small and a large playlist, check rows and covers, check the YAML
  file, move the window during import (responsiveness), import with iTunes closed (it starts),
  save to another folder, cancel the picker, save over an existing file (overwrite prompt).
  Read-only towards iTunes.

## Open questions

None. (A song info cache was considered and dropped: sorter files carry the full metadata.)

## Amendments

### 2026-11-19 – Implementation details

- **What changed:** `ItunesWorker.importPlaylist` takes the playlist *name* chosen in the dialog and
  looks up its ID from the last `listPlaylists` result, instead of taking the ID. The toolbar also has
  a disabled *Commit to iTunes* action. Row button tooltips say "(coming soon)".
- **Why:** the dialog returns a name, and keeping the name→ID mapping in the worker avoids passing it
  back and forth between threads.
- **Effect on acceptance criteria / validation:** none. Unit tests cover the worker's list, import and
  failure paths with the COM fakes, without a running thread.
