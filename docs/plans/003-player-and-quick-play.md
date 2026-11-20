# 003 – Shared player widget, UC-5 (player) and UC-6 (quick play actions)

**Mode:** Default (agent implements, developer reviews `git diff`; nothing committed).

**Status:** Ready for review (tracked in [README.md](README.md)).

**Issues:** UC-5 (#5, player widget), UC-6 (#6, quick play actions per song).

## Context

Plan 002 left a "Player (coming soon)" placeholder and three inert buttons on every song row. To sort a
playlist the user needs to hear the songs: a player showing the current song (artwork, title,
artist – album), a seek bar, and iTunes-style controls, which plays the next song in *sorting order* when
one ends. Two row buttons start playback quickly: from the beginning, or the last 10 seconds. Other apps
(verifier, importer) will want the same player, so it is a shared component.

## Scope

**In**

- `PlayerWidget`, a reusable Qt widget in `itunes_tools/common/widgets/player.py`:
  - artwork, title, artist – album; elapsed and remaining time; a seek slider;
  - controls: previous, play/pause, next, volume slider;
  - plays local files (`Song.location`) with Qt Multimedia, without iTunes (the sorter works offline).
- Sorter wiring:
  1. The playing song's row shows a speaker icon in a new narrow column left of the artwork; the column
     is empty for every other row. No coloured highlight.
  2. When a song ends, the next song in the current sorting order plays and the list scrolls to it.
     *Next* / *Previous* buttons do the same.
  3. Row buttons *Play from the beginning* and *Play the last 10 seconds* work (enabled icons, clickable).
     After the last 10 seconds, playback continues with the next song like any song end.
- Messages pane reports songs that cannot play (no file, unreadable file); auto-advance skips them.

**Out**

- *Send to a group* (UC-7) stays inert. Double-click to play, shuffle/repeat, keyboard shortcuts, a play
  queue separate from the sorting order, remembering the playing song in the sorter file.

## Approach

### 1. Shared Qt code — `itunes_tools/common/widgets/` (new package)

`common` stays the home of shared code; the `widgets` subpackage holds the parts that need Qt, so the
non-Qt modules keep importing without a `QApplication`.

- `widgets/artwork.py`: `load_artwork_pixmap(cache: ArtworkCache, song: Song, size: int) -> QPixmap`,
  moved out of `SongListModel._artwork_pixmap` (scaled artwork, light-grey square when missing). The song
  list keeps its per-song memo and calls this; the player calls it with a larger size.
- `widgets/player.py`:
  - `PlayerWidget(QWidget)` owns a `QMediaPlayer` + `QAudioOutput`.
    - Public: `play(song, start_ms=0)`, `play_last_seconds(song, seconds=10)`, `toggle_play_pause()`,
      `stop()`, `current_song() -> Song | None`.
    - Signals: `currentSongChanged(object)` (Song or None), `songFinished(object)`,
      `nextRequested()`, `previousRequested(object)`, `playbackFailed(str)`.
    - It does **not** know the play order: on end of media it emits `songFinished(song)` and the app
      decides what plays next. Next/Previous buttons only emit requests. This keeps it reusable by apps
      with different sequences.
    - Previous follows iTunes: more than 3 s into the song restarts it; otherwise emits
      `previousRequested`.
    - Start positions are applied once the media has loaded (`mediaStatusChanged` → `LoadedMedia`),
      because `setPosition` right after `setSource` is ignored. "Last 10 seconds" uses the real duration
      from `QMediaPlayer.duration()` (more precise than `Song.duration`, which is whole seconds).
    - Seek slider: dragging pauses position updates and seeks on release (`sliderReleased`), so the
      slider does not fight the playback position.
    - A song with `location is None` or a media error emits `playbackFailed` with the song name.
  - Pure helpers, unit-testable without audio: `format_time(ms) -> str` (`m:ss`),
    `last_seconds_start(duration_ms, seconds) -> int` (clamped at 0).
- Layout (fixed height ~80 px, replacing `PLAYER_HEIGHT = 64`):
  ```
  | ⏮ ⏯ ⏭  🔈──── | [art] Title                          |
  |               |       Artist – Album                 |
  |               |  0:42 ━━━━━━━━●──────────── -2:13    |
  ```
  Icons from `QStyle.StandardPixmap.SP_Media*`, like the toolbar.

### 2. Song list — `sorter/song_list.py`

- `SongListModel`: `set_playing_song(song_id | None)`, `playing_row() -> int | None`, and a new
  `IsPlayingRole`; emits `dataChanged` for the old and new rows only.
- `SongRowDelegate`:
  - Paints a speaker column (`SP_MediaVolume`, ~16 px) left of the artwork, only when `IsPlayingRole`
    is true. Text and artwork shift right accordingly.
  - Buttons *Play from the beginning* and *Play the last 10 seconds* painted enabled; *Send to a group*
    stays disabled with "(coming soon)" in its tooltip.
  - `button_at(row_rect, pos) -> RowAction | None` hit-test, and `editorEvent` on mouse release over an
    enabled button emits `rowActionTriggered(str, QModelIndex)` (action name, row). A `RowAction` gets
    an `enabled: bool` field.

### 3. Sorter wiring — `sorter/main_window.py` and a small `sorter/playback.py`

- `playback.py` holds the order logic as plain functions, testable without Qt multimedia:
  `next_playable_index(songs, after_index) -> int | None` and
  `previous_playable_index(songs, before_index) -> int | None`, skipping songs with `location is None`.
- `MainWindow` replaces the placeholder frame with `PlayerWidget` and connects:
  - `rowActionTriggered` → `play(song)` or `play_last_seconds(song)`;
  - `currentSongChanged` → `model.set_playing_song(...)`;
  - `songFinished` / `nextRequested` → next playable song after the current one in the model's *current*
    order (so later reordering in UC-8 is respected), then `view.scrollTo(index, PositionAtCenter)`;
    at the end of the list playback stops;
  - `previousRequested` → previous playable song, scrolled to likewise;
  - `playbackFailed` → messages pane, then advance as on song end;
  - importing a new playlist stops playback; `closeEvent` stops the player.
- README *Playlist sorter*: describe the player and row buttons. CLAUDE.md *Current state*: the
  `common/widgets` package and player exist.

## Steps

1. `common/widgets/artwork.py`; switch `SongListModel` to it (no behaviour change; existing tests pass).
2. `PlayerWidget` with helpers; manual check in a spike script (`spikes/player_demo.py`) playing a file.
3. Model playing state + speaker column + clickable row buttons in the delegate.
4. `playback.py` order functions; wire everything in `MainWindow`.
5. Tests, README, CLAUDE.md, plan index; manual run.

## Acceptance criteria

- The player shows the playing song's artwork, title, artist – album, elapsed/remaining time; play/pause,
  previous, next and volume work; dragging the seek bar seeks.
- Clicking *Play from the beginning* on a row plays that song from 0; *Play the last 10 seconds* starts
  10 s before its end (from 0 if shorter).
- Only the playing song's row shows the speaker icon; it moves when the song changes.
- When a song ends (including after "last 10 seconds"), the next song in sorting order plays and the list
  scrolls to it; songs without a file are skipped with a message; after the last song playback stops.
- *Send to a group* still does nothing; no iTunes calls during playback.
- Unit tests pass; formatting and import checks pass.

## Validation

- Unit tests (with `UV_PROJECT_ENVIRONMENT=D:\venv\itunes-tools`):
  - `tests/common/widgets/test_artwork.py`: scaled pixmap; placeholder when no artwork.
  - `tests/common/widgets/test_player.py`: `format_time`, `last_seconds_start`; `PlayerWidget` shows a
    song's info on `play` and emits `playbackFailed` for `location=None` (no audio needed).
  - `tests/sorter/test_playback.py`: next/previous skipping unplayable songs, ends of list.
  - `tests/sorter/test_song_list.py`: `set_playing_song` role and `dataChanged` rows; `button_at`
    hit-testing; disabled button not triggered.
  - `uv run pytest`, `uv run ruff format --check --diff .`, `uv run ruff check .`.
- Manual (no iTunes needed after import, or open a saved sorter file once UC-2 exists): import a playlist;
  play from beginning; last 10 s on a long and a very short song; let a song end and watch the list
  scroll; next/previous, including previous after 3 s; seek by dragging; volume; a song with a missing
  file; import another playlist while playing; close while playing.

## Open questions

- Qt Multimedia's FFmpeg backend ships with PySide6 (verified: `QtMultimedia.pyd`, `avcodec-*.dll` are
  installed). Format support for every file in the library (AAC/ALAC `.m4a`, MP3) is assumed and checked
  in the manual run; protected old iTunes Store `.m4p` files will not play and are reported as failures.

## Amendments

### 2026-11-19 – Implementation details

- **What changed:** the `qt_application` fixture moved from `tests/sorter/test_song_list.py` to
  `tests/conftest.py`, next to a new `make_song` factory fixture; both are shared by the song list,
  player, artwork and playback tests. The spike `spikes/player_demo.py` drives the sorter window's
  playback offline (muted) with two real files and a song without one.
- **Why:** the new widget tests need a `QApplication` and songs too, and conftest cannot be imported.
- **Effect on acceptance criteria / validation:** none.

### 2026-11-19 – Seek bar length lost when replaying the current song

- **What changed:** `PlayerWidget._start` sets the seek bar's range from `QMediaPlayer.duration()`
  right after `setSource`. A regression test plays a generated silent WAV twice (muted).
- **Why:** setting the same file again (e.g. *Play the last 10 seconds* on the playing song) does not
  reload it, so `durationChanged` never came after `_show_song` had reset the range to 0, leaving the
  seek bar at 0:00. Reproduced with `spikes/seek_bar_bug.py`.
- **Effect on acceptance criteria / validation:** none; the regression test needs Qt Multimedia to load
  a real file.

### 2026-11-19 – Player layout and icon colours

- **What changed:** the player's controls (previous / play-pause / next, volume) moved to the right of
  the song info; the layout is now artwork, title, artist – album and seek bar, then the controls.
  Media icons in the player and on the song rows are recoloured to the palette's button text colour
  (white in a dark theme) with the disabled text colour for disabled icons, through a new shared helper
  `text_colored_icon` in `common/widgets/icons.py`, with a unit test.
- **Why:** requested by the developer; the style's black media icons were hard to tell from disabled
  ones on a dark background.
- **Effect on acceptance criteria / validation:** the layout sketch under *Approach* is superseded by
  this order; acceptance criteria unchanged.
