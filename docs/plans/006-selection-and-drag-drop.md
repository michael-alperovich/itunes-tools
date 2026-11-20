# 006 – Selection, drag and drop, cut and paste (UC-8)

**Mode:** Default (agent implements, developer reviews `git diff`; nothing committed).

**Status:** Complete (tracked in [README.md](README.md)).

**Issue:** UC-8 (#8, song selection and drag-and-drop).

## Context

The sorter list (`QTreeView` over the two-level `SongListModel`) has single selection only, and songs
can change place only through the *Move to group* row button (plan 005). Sorting a playlist needs
moving songs freely: selecting several songs, dragging them to any position, into and out of groups,
and reordering groups. Plan 005 left "moving groups and moving songs out of a group" to UC-8.

Note: plan 005's changes are still uncommitted and this plan edits the same files (`song_list.py`,
`main_window.py`, their tests). Committing 005 first keeps the UC-8 `git diff` readable.

## Scope

**In** (issue #8 + answers in chat)
1. **Selection**: click selects one row (song or group); Shift+click selects the visible songs from the
   anchor to the clicked song; Ctrl+click toggles a song. **Multi-select is for songs only**: group rows
   are never part of a multi-selection (a range skips group headers; Ctrl/Shift+click on a group does
   nothing; Ctrl/Shift+click on a song while a group is selected replaces the group). Ctrl+A selects all
   visible songs. So a selection is either one group or one or more songs.
2. **Drag and drop**: dragging the selection moves it, in true playlist order, to the drop point:
   - between any two rows, at the top level or inside a group (into / out of / between groups);
   - onto a group row (collapsed or expanded) → appended to the end of that group;
   - just below an expanded group's header → first songs of that group;
   - below the last row → end of the list.
   - A **group** drags as a whole (its songs with it) and drops only at the top level; positions inside
     a group are refused (forbidden cursor), except "below a group's last song", which means "after
     that group". Hovering a collapsed group while dragging expands it after a short delay.
3. **Cut / paste**: Ctrl+X remembers the selection (message: "Cut N songs…"); Ctrl+V moves it above the
   current row (inside the current song's group when the current song is in one; above the group at the
   top level when the current row is a group header). A group is pasted at the top level above the
   current row's top-level item. Esc or a new cut forgets the cut; paste forgets it after moving.
4. **Move to group** row button: when the clicked song is in the selection, all selected songs move
   (in order, appended to the group); otherwise only the clicked song.
5. Selection, the current row and the playing mark follow moved rows; group song counts update.

**Out**: copy (duplicating songs), dimming cut rows, undo, keyboard moves (Alt+Up/Down), multi-group
selection, unsaved-changes tracking.

## Approach

### Model — `sorter/song_list.py`
- One general move: `move_items(indexes, target_parent, target_row) -> int` (moved count).
  - Sorts `indexes` into true playlist order (key: top-level row, then child row).
  - Validates: songs only, or exactly one group; a group only to the top level (no nesting) →
    `ValueError` otherwise. A no-op move returns 0.
  - Moves one row at a time with `beginMoveRows`/`endMoveRows` (persistent indexes — selection,
    current index — follow; simple and explicit, fast enough for thousands of songs), keeping an
    insert-before position that is adjusted when a source sits above it in the same parent; Qt's
    rejected no-op moves (`dest == row` or `row + 1`) are skipped. The target group is tracked by its
    `SongGroup` object, since its row can change while top-level songs above it move.
  - Emits `GroupSongCountRole` changes for every touched group (reuses `_emit_song_count_changed`).
- `move_song_to_group` is replaced by `move_items([...], group_index, group_song_count)`; tests move over.
- Drag support: `flags()` adds `ItemIsDragEnabled` everywhere and `ItemIsDropEnabled` on groups and the
  root (songs accept only Above/Below, so Qt offers "onto" only for groups); `supportedDropActions()` =
  `MoveAction`; `mimeTypes()` / `mimeData()` with one private format (`application/x-itunes-tools-rows`,
  no payload — drags never leave the view, which moves its own selection). No `removeRows`/`dropMimeData`.

### View — `sorter/song_tree_view.py` (new; keeps `main_window.py`, ~550 lines, from growing)
- `SongTreeView(QTreeView)`: takes over the view setup now in `MainWindow._create_central_widget`
  (hidden header, no indentation, delegate, mouse tracking) plus `ExtendedSelection`, `InternalMove`,
  `setDragEnabled`, drop indicator, `setAutoExpandDelay`.
- `SongSelectionModel(QItemSelectionModel)`: overrides `select` to enforce the selection rule of scope
  item 1 (drop group indexes from multi-row selections; allow a lone group on a clearing select; clear a
  selected group when songs are added). Installed with `setSelectionModel` after `setModel`.
- `drop_target(index, indicator) -> tuple[QModelIndex, int] | None`: maps `dropIndicatorPosition()` and
  the hovered index to (parent, row) per scope item 2, using `isExpanded` and whether a group is dragged.
- `dragMoveEvent`: `super()` (Qt computes the indicator), then `ignore()` when `drop_target` is `None`.
- `dropEvent`: computes the target, calls `model.move_items(selected rows, …)`, then
  `setDropAction(IgnoreAction)` + `accept()` — the move is done, so Qt's drag code must not remove rows.
- Cut / paste / Esc as `QAction`s with standard shortcuts on the view (`WidgetWithChildrenShortcut`);
  cut stored as `QPersistentModelIndex`es. `messageRequested = Signal(str)` reports cuts and moves.
- `selected_songs_for(index)` helper for scope item 4 (selection if `index` is in it, else `[index]`).

### `sorter/main_window.py`
- Create `SongTreeView`; connect `messageRequested` to `_show_message`.
- `_move_song_to_group` → `_move_songs_to_group(index)`: uses `selected_songs_for`, then `move_items`;
  message "Moved N songs to the group X".

### Docs
README *Playlist sorter* (selection, drag and drop, cut/paste), CLAUDE.md *Current state* (new
`song_tree_view.py`, `move_items`), module docstrings (`song_list.py`, `main_window.py`), plan index.

## Steps
1. Save plan 006 + index entry.
2. `move_items` + drag flags/mime in `song_list.py`; replace `move_song_to_group`; tests.
3. `song_tree_view.py`: setup, selection model, drop target, drag/drop events, cut/paste; tests.
4. Main window wiring and multi-song *Move to group*.
5. Docs; plan → Ready for review; spike (`spikes/groups_demo.py` or a copy) for a quick offline look.

## Acceptance criteria
- Click / Shift+click / Ctrl+click select as in scope item 1; a group is never in a multi-selection.
- Dragging songs moves them, in order, between rows, into, out of and between groups, and onto a group
  row; a group drags as a whole and only to the top level.
- Ctrl+X then Ctrl+V moves the cut songs (or group) above the current row.
- *Move to group* moves all selected songs when clicked on a selected song.
- Selection and playing mark follow; playback, Save and Commit use the new order; group counts update.
- Unit tests, `ruff format --check`, `ruff check` pass.

## Validation
- `tests/sorter/test_song_list.py` (under `QAbstractItemModelTester`): `move_items` up/down at top
  level, non-contiguous songs to a point between them, into/out of/between groups, onto an empty group,
  group reorder, no-op, invalid (group into group, mixed group+songs) raises, persistent indexes follow,
  song-count `dataChanged`; `songs()` order after each.
- `tests/sorter/test_song_tree_view.py` (new, `qt_application`): selection rules via the selection
  model (range across a header skips it, Ctrl on group ignored, song after group replaces it);
  `drop_target` for each indicator case incl. expanded/collapsed group and group drags; cut/paste via
  the actions; `selected_songs_for`.
- `uv run pytest`, `uv run ruff format --check --diff .`, `uv run ruff check .`
  (with `UV_PROJECT_ENVIRONMENT=D:\venv\itunes-tools`).
- Manual (developer; real mouse drags cannot be unit-tested well): select with click/Shift/Ctrl, drag
  songs into/out of/between groups and onto collapsed groups, drag a group, cut/paste, Move to group
  with a multi-selection, playback continues in the new order, Save → Open, Commit order in iTunes.

## Open questions
None.

## Amendments

### 2026-11-19 – Implementation details

- **What changed:**
  - `move_items` first pulls the insertion point up past moved rows that already stand right above it,
    so moving rows to where they are is a true no-op (no `rowsMoved`) instead of a reshuffle.
  - The view creates the row delegate and exposes it as `SongTreeView.row_delegate`; the main window
    connects to it there. Drops report no message (the move is visible); cut and paste do.
  - Collapsing a group deselects its songs, so hidden songs are never dragged or cut along unseen.
  - Shift+click that ends on a group header selects the songs of the range (the header is skipped),
    rather than doing nothing.
  - A refused drop place shows the forbidden cursor, but Qt still draws its indicator line there (Qt
    keeps the indicator private).
  - Spike `spikes/drag_drop_demo.py` drives selection, multi-song *Move to group*, a drop target and
    cut/paste offline; real mouse drags are left to the manual check.
- **Why:** correctness of no-op moves; consistent selection with collapsed groups.
- **Effect on acceptance criteria / validation:** none.

