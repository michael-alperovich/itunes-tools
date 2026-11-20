# 004 – Open/Save sorter files (UC-2) and Commit to iTunes (UC-3)

**Mode:** Default (agent implements, developer reviews `git diff`; nothing committed).

**Status:** Complete (tracked in [README.md](README.md)).

**Issues:** UC-2 (#2, save and restore a sorter file), UC-3 (#3, commit the sorted playlist to iTunes).

One plan for both, as agreed with the developer.

## Context

The toolbar's *Open*, *Save* and *Commit to iTunes* are disabled placeholders. The sorter file format,
`load_sorter_file` / `save_sorter_file` (`sorter/sorter_file.py`) and `ItunesClient.create_playlist`
(name check, `PlaylistNameTakenError`, `TrackNotFoundError`) already exist and are tested; only the UI
and worker wiring is missing. Outcome: a user can reopen a saved session without iTunes, save progress,
and commit the current order as a new iTunes playlist (which also saves the sorter file).

## Scope

**In**
- *Open*: file dialog in `SORTER_FOLDER` → load → show songs, title, remember the file path.
- *Save*: write the current state (model order) to the remembered file; if none, ask with a save
  dialog (same as after import). Import also remembers the path it saved to.
- *Commit to iTunes*: ask for a new playlist name, save the sorter file, then create the playlist in
  iTunes in the current order on the worker thread; taken name → error in the messages pane, nothing
  created (the user tries again with another name).
- *Save* and *Commit* enabled only while a playlist is loaded; iTunes actions (Import, Commit)
  disabled while a worker job runs.

**Out**
- Groups (UC-7; the issue's "groups saved" criterion waits for it — nothing to save yet), reordering
  (UC-8), unsaved-changes tracking / prompt on close (nothing can change yet), *Save As*, refresh.

## Approach

### `sorter/main_window.py`
- New state: `_playlist: Playlist | None` (id + name of the loaded playlist) and
  `_sorter_file_path: Path | None`.
- Replace the placeholder loop: real `_open_action`, `_save_action`, `_commit_action`; *Add group*
  stays a disabled placeholder. Tooltips drop "(coming soon)".
- `_show_playlist(playlist, path)` – shared by import and open: stop player, `set_songs`, window title,
  enable Save/Commit, remember state.
- `_current_sorter_file() -> SorterFile` – `SorterFile(playlist=playlist.model_copy(update={"tracks":
  self._song_model.songs()}))`, so saving follows the model's current order (UC-8 ready).
- `_save(ask_path: bool) -> bool` – reuses the existing dialog code from `_save_imported_playlist`
  (renamed/generalized to `_ask_sorter_file_path`), writes, reports; returns whether it saved.
- Open: catch `OSError`, `yaml.YAMLError`, `pydantic.ValidationError` → "Error: could not open …".
- Commit: `QInputDialog.getText` suggesting `"<playlist name> (sorted)"`; blank/cancel → message;
  `_save(...)` first (cancelled save → commit cancelled, since the issue requires the file be saved);
  then `_commitPlaylistRequested.emit(name, [song.id for song in songs])`.
- `_set_itunes_busy(busy: bool)` toggles Import and Commit (Commit only when a playlist is loaded);
  used by import, commit and `_on_worker_failed`.

### `sorter/itunes_worker.py`
- Signal `playlistCommitted = Signal(object)  # Playlist`, slot `commitPlaylist(str, list)` calling
  `self._get_client().create_playlist(name, track_ids)`, with the same `ItunesClientError` /
  unexpected-exception handling as the other slots. Update the class docstring's result-signal list.
- Window: `playlistCommitted` → "Created iTunes playlist 'X' with N songs." and un-busy.
- To avoid a third copy of the try/except block, extract a small private helper in the worker only if
  it stays obvious; otherwise keep the explicit pattern (Zen: explicit over compact).

### Docs
- README *Playlist sorter*: Open, Save, Commit; *iTunes library contract*: commit requires a new,
  unused playlist name. CLAUDE.md *Current state*: sorter opens/saves files and commits.
- Module docstring of `main_window.py` updated.

## Steps
1. Save plan 004 + index entry.
2. Worker `commitPlaylist` + tests.
3. Window state, `_show_playlist`, Open and Save actions.
4. Commit flow and busy-state handling.
5. README, CLAUDE.md, plan status → Ready for review; manual run.

## Acceptance criteria
- *Open* loads a sorter file saved by import and shows its songs and title without iTunes; a broken
  or foreign file gives an error message, the current list stays.
- *Save* writes the current order to the opened/imported file without asking; asks when none is known.
- *Commit* creates a new iTunes playlist with the songs in the shown order and saves the sorter file
  first; a taken name is rejected with a message and nothing is created; cancel at any prompt does
  nothing to iTunes.
- Save/Commit disabled with no playlist; the UI stays responsive during commit.
- Unit tests, `ruff format --check`, `ruff check` pass.

## Validation
- `tests/sorter/test_itunes_worker.py`: `commitPlaylist` emits `playlistCommitted` with the new
  playlist (COM fakes), emits `failed` for a taken name (`PlaylistNameTakenError` message) and for an
  unexpected exception. Existing `tests/sorter/test_sorter_file.py` covers the round trip.
- `uv run pytest`, `uv run ruff format --check --diff .`, `uv run ruff check .`
  (with `UV_PROJECT_ENVIRONMENT=D:\venv\itunes-tools`).
- Manual, with iTunes (developer, since it writes to the library): import → Save → close → Open
  (iTunes closed) → play a song; open a non-YAML file; commit with a taken name, then a new name, and
  check order in iTunes; cancel the name dialog and the save dialog.

## Open questions
None.

## Amendments

### 2026-11-19 – Implementation details

- **What changed:** *Open* reports the three failure kinds separately (unreadable file, invalid YAML,
  not a sorter file) and logs the full error, since a Pydantic validation error is too long for the
  messages pane. A throwaway spike, `spikes/open_save_commit_demo.py`, drives Open, Save and Commit
  offline (dialogs patched, worker request captured instead of sent to iTunes). The worker's three
  try/except blocks stay explicit; no helper was extracted.
- **Why:** clearer messages; the window has no unit tests, so the spike stands in for a first check.
- **Effect on acceptance criteria / validation:** none.
