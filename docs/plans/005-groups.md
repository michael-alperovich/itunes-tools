# 005 – Groups (UC-7)

**Mode:** Default (agent implements, developer reviews `git diff`; nothing committed).

**Status:** Ready for review (tracked in [README.md](README.md)).

**Issue:** UC-7 (#7, groups).

## Context

The sorter shows a flat song list; *Add group* (toolbar) and *Send to a group* (row button) are
disabled placeholders. Groups are temporary containers that help sorting: a group holds songs, is never
nested, and is not sent to iTunes. The true playlist order is always the songs read top to bottom
(group contents in place), so the player, *Save* and *Commit* keep working unchanged in spirit.

## Scope

**In** (developer's list + rename, agreed in chat)
1. Groups as top-level song containers (no nesting), saved in the sorter file and restored on *Open*.
2. Group row buttons: **Delete** (its songs stay at the group's position, in order) and **Rename**.
3. Toolbar **Add group**: asks a name; inserted above the current row's top-level item (above the
   song's group when the current song is inside one), at the end when nothing is current.
4. Toolbar **Add season groups**: years *From*–*To*, creates empty groups oldest first —
   `Winter 2017, Spring 2017, Summer 2017, Fall 2017, Winter 2018 …` (Winter Y = Dec Y-1 – Feb Y; names
   only, no song assignment), inserted as one block at the same place as *Add group*.
5. Row button **Move to group** enabled: a small dialog with a search box filters group names; the song
   is appended at the end of the chosen group (from the top level or from another group).
6. Playlist order = depth-first flattening; player next/previous, the speaker icon, *Save* and *Commit*
   follow it, including songs in collapsed groups.
- Group names are unique and non-empty (the search dialog shows names); a taken name is rejected with
  a message; season groups whose name exists are skipped with a message.

**Out**
- Moving groups and moving songs out of a group (UC-8 drag and drop; the tree model is ready for it),
  saving expanded/collapsed state (groups open expanded), unsaved-changes tracking.

## Approach

### Data and file format — `sorter/sorting_items.py` (new, pure Python, no Qt)
- `SongGroup(BaseModel)`: `name: str`, `songs: list[Song]`. `SortingItem = Song | SongGroup`.
- `flatten(items) -> list[Song]` — the true playlist order.
- `season_group_names(first_year, last_year) -> list[str]`.
- `items_from_sorter_file(SorterFile) -> list[SortingItem]` and
  `sorter_file_from_items(playlist, items) -> SorterFile`.

### `sorter/sorter_file.py`
- `format_version` default → 2. New field `groups: list[GroupRange] = []`, where
  `GroupRange(name, first_track: int, track_count: int)` points into `playlist.tracks`.
  `playlist.tracks` stays the full playlist in true order (the file's existing contract), so v1 files
  load unchanged (no groups) and Commit still reads one flat list.
- A model validator rejects ranges that overlap, go out of bounds, are out of order, or repeat a name
  (surfaces as the existing "not a sorter file" `ValidationError` message on *Open*).

### Qt model — `sorter/song_list.py`
- `SongListModel` becomes a two-level `QAbstractItemModel` over `list[SortingItem]` (class name kept to
  limit churn). `internalId` encodes the parent: `0` for top-level rows, `group_row + 1` for a group's
  songs; `parent()` decodes it (no `internalPointer`, which is fragile with Python objects).
- New roles: `IsGroupRole`; group `DisplayRole` = name, plus song count for painting.
- API: `set_items`, `items`, `songs()` (flattened), `group_names()`, `insert_groups(top_row, names)`,
  `delete_group(top_row)` (`beginRemoveRows` of the group, then `beginInsertRows` of its songs),
  `rename_group(top_row, name)`, `move_song_to_group(song_index, group_row)` (`beginMoveRows`, so
  selection and the playing mark follow), `top_level_row(index)`.
- Playback helpers move from rows to flat positions: `playing_position()` and
  `index_at_position(position) -> QModelIndex`; `set_playing_song` finds the song wherever it is.

### Delegate — `sorter/song_row_delegate.py` (moved out of `song_list.py`, which would pass ~400 lines)
- Song rows paint as today; `MOVE_TO_GROUP` enabled. Group rows paint a bold header (name, song count)
  with `RENAME_GROUP` and `DELETE_GROUP` buttons. `button_rects(row_rect, count)` and `button_at` choose
  `SONG_ACTIONS` or `GROUP_ACTIONS` by `IsGroupRole`; `rowActionTriggered` unchanged.

### Dialogs — `sorter/group_dialogs.py` (new)
- `GroupPickerDialog`: `QLineEdit` filtering a `QListView` through `QSortFilterProxyModel` over a
  `QStringListModel` (case-insensitive); Enter takes the first match, double-click accepts.
  `ask_group(parent, names) -> str | None`.
- `SeasonGroupsDialog`: two `QSpinBox` years (default: current year), *To* minimum follows *From*.
  `ask_year_range(parent) -> tuple[int, int] | None`.

### `sorter/main_window.py`
- `QListView` → `QTreeView` (header hidden, children indented, expand arrows, non-uniform row heights,
  groups expanded on load).
- Real *Add group* / *Add season groups* actions (enabled with a playlist), row-action handlers for
  move, rename (`QInputDialog.getText`) and delete. Insert position from `view.currentIndex()` via
  `model.top_level_row`.
- `_current_sorter_file` / `_show_playlist` go through `sorter_file_from_items` / `items_from_sorter_file`.
- Playback uses `playing_position()`, `songs()` and `index_at_position()`; `scrollTo` on a tree index
  also expands a collapsed group, so the playing song is always shown. `playback.py` is unchanged.

### Docs
README *Playlist sorter* (groups, season groups, file format note), CLAUDE.md *Current state*,
module docstrings, `docs/plans/README.md`.

## Steps
1. Save plan 005 + index entry.
2. `sorting_items.py` + `sorter_file.py` format v2, with tests.
3. Tree model in `song_list.py`; split delegate into `song_row_delegate.py`; group rows and buttons; tests.
4. `group_dialogs.py` + tests.
5. Main window: tree view, actions, row handlers, playback by flat position, save/open with groups.
6. Docs, plan → Ready for review; spike + manual run.

## Acceptance criteria
- Add group / Add season groups create groups at the agreed position; seasons `Winter Y … Fall Y`,
  oldest first; duplicates rejected or skipped with a message.
- Move to group (with search) moves a song into a group from anywhere; delete leaves the songs in order
  at the group's place; rename works; no way to nest a group.
- Player next/previous, the speaker icon and Commit follow the flattened order, including collapsed
  groups; the list expands to show the playing song.
- Save then Open restores groups and order; v1 files still open.
- Unit tests, `ruff format --check`, `ruff check` pass.

## Validation
- `tests/sorter/test_sorting_items.py`: flatten, season names (single year, range, Fall, Winter naming),
  file conversion round trip.
- `tests/sorter/test_sorter_file.py`: v2 round trip with groups (incl. empty ones), v1 file loads,
  invalid ranges / duplicate names raise `ValidationError`.
- `tests/sorter/test_song_list.py`: run every scenario under `QtTest.QAbstractItemModelTester` (checks
  the tree model's consistency); insert/delete/rename/move keep `songs()` order; playing position and
  `index_at_position` across groups; move signals keep the playing mark.
- `tests/sorter/test_song_row_delegate.py` (moved tests + group actions), `tests/sorter/test_group_dialogs.py`
  (filtering, first match on Enter, year bounds).
- `uv run pytest`, `uv run ruff format --check --diff .`, `uv run ruff check .`
  (with `UV_PROJECT_ENVIRONMENT=D:\venv\itunes-tools`).
- Spike `spikes/groups_demo.py` opens the window on a saved sorter file offline for a quick look.
- Manual (developer): open a sorter file, add groups and season groups, move songs, collapse a group and
  let playback run into it, delete/rename, Save → Open, Commit and check the order in iTunes.

## Open questions
None.

## Amendments

### 2026-11-19 – Implementation details

- **What changed:**
  - Group keys in `internalId` are the identity of the model's own `SongGroup` objects instead of
    `group_row + 1`: Qt does not update the indexes of songs inside a group when rows above the group
    are inserted or removed, so a row-based key would leave the view's selection pointing at the wrong
    group. `delete_group` moves the songs out (`beginMoveRows`) before removing the group row.
  - The style has no one-colour pencil or trash icon (the tinted ones become solid squares), so
    *Rename* is drawn as a text glyph (✎) and *Delete* uses the title-bar close icon (✕); `RowAction.icon`
    accepts either. The `enabled` flag of `RowAction` is gone, since every button now works.
  - Skipped season groups are reported in one message. Opening a file reports its group count.
  - `main_window.py` grew to about 540 lines; splitting its group handling out is left as a suggestion.
  - Throwaway spike `spikes/groups_demo.py` drives the window offline (dialogs and player replaced).
- **Why:** correctness of persistent indexes; readable buttons in the dark theme; less message noise.
- **Effect on acceptance criteria / validation:** none.
