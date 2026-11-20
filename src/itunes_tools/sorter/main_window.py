"""The sorter's main window: toolbar, player, song list and messages, top to bottom.

*Import from iTunes* (UC-1, UC-4), *Open* and *Save* of sorter files (UC-2), *Commit to iTunes* (UC-3),
the player (UC-5) and the per-song play buttons (UC-6) work. *Add group* and *Send to a group* are
placeholders for UC-7.

iTunes work (listing, importing, committing) runs in ``ItunesWorker`` on its own thread, one job at a
time; opening and saving sorter files is local and needs no iTunes.

Playback follows the sorting order: when a song ends, the next song in the list plays and the list scrolls
to it. The shared ``PlayerWidget`` only plays songs; this window decides which one comes next.
"""

from datetime import datetime
from pathlib import Path

import yaml
from pydantic import ValidationError
from PySide6.QtCore import QModelIndex, Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QInputDialog,
    QListView,
    QMainWindow,
    QPlainTextEdit,
    QStyle,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.common.config import SORTER_FOLDER
from itunes_tools.common.logger import get_logger
from itunes_tools.common.models import Playlist, Song
from itunes_tools.common.widgets.player import PlayerWidget
from itunes_tools.sorter.itunes_worker import ItunesWorker
from itunes_tools.sorter.playback import next_playable_index, previous_playable_index
from itunes_tools.sorter.song_list import (
    PLAY_FROM_START,
    PLAY_LAST_SECONDS,
    SongListModel,
    SongRole,
    SongRowDelegate,
)
from itunes_tools.sorter.sorter_file import (
    SorterFile,
    load_sorter_file,
    save_sorter_file,
    suggested_sorter_file_path,
)

logger = get_logger(__name__)

MESSAGES_HEIGHT = 90
SORTER_FILE_FILTER = "Sorter files (*.yaml);;All files (*)"


class MainWindow(QMainWindow):
    # Requests for the worker thread. Emitting a signal queues the call in the worker's event loop;
    # calling the worker's slots directly would run them here, in the UI thread.
    _listPlaylistsRequested = Signal()
    _importPlaylistRequested = Signal(str)
    _commitPlaylistRequested = Signal(str, list)  # new playlist name, list[ItunesPersistentID] in order

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Playlist Sorter")
        self.resize(900, 600)

        # The playlist being sorted (its id and name; the song order lives in the model) and the sorter
        # file it was opened from or saved to. Both are None until a playlist is imported or opened.
        self._playlist: Playlist | None = None
        self._sorter_file_path: Path | None = None
        # True while the worker runs a job; the worker handles one job at a time.
        self._itunes_busy = False

        artwork_cache = ArtworkCache()
        self._song_model = SongListModel(artwork_cache, self)
        self._player = PlayerWidget(artwork_cache)

        self._create_toolbar()
        self.setCentralWidget(self._create_central_widget())
        self._connect_player()
        self._start_worker(artwork_cache)
        self._show_message("Ready. Use 'Import from iTunes' or 'Open' to load a playlist.")

    # --- Layout -------------------------------------------------------------------------------------

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Main toolbar", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(toolbar)

        self._import_action = self._add_action(
            toolbar,
            "Import from iTunes",
            "Load a playlist and its songs from iTunes, then save it as a sorter file",
            QStyle.StandardPixmap.SP_ArrowDown,
        )
        self._import_action.triggered.connect(self._on_import_triggered)

        self._open_action = self._add_action(
            toolbar, "Open", "Open a saved sorter file", QStyle.StandardPixmap.SP_DialogOpenButton
        )
        self._open_action.triggered.connect(self._on_open_triggered)

        self._save_action = self._add_action(
            toolbar, "Save", "Save the sorting progress to the sorter file", QStyle.StandardPixmap.SP_DialogSaveButton
        )
        self._save_action.triggered.connect(self._on_save_triggered)

        # Placeholder for UC-7 (groups); disabled until implemented.
        self._add_action(
            toolbar, "Add group", "Add a group of songs (coming soon)", QStyle.StandardPixmap.SP_FileDialogNewFolder
        ).setEnabled(False)

        self._commit_action = self._add_action(
            toolbar,
            "Commit to iTunes",
            "Save the sorter file and create the sorted playlist in iTunes under a new name",
            QStyle.StandardPixmap.SP_ArrowUp,
        )
        self._commit_action.triggered.connect(self._on_commit_triggered)

        # Save and Commit need a playlist; see _update_actions.
        self._update_actions()

    def _add_action(self, toolbar: QToolBar, text: str, tooltip: str, icon: QStyle.StandardPixmap) -> QAction:
        action = QAction(self.style().standardIcon(icon), text, self)
        action.setToolTip(tooltip)  # shown when hovering the toolbar button
        action.setStatusTip(tooltip)  # shown in the status bar meanwhile
        toolbar.addAction(action)
        return action

    def _create_central_widget(self) -> QWidget:
        self._song_view = QListView()
        self._song_view.setModel(self._song_model)
        self._song_delegate = SongRowDelegate(self._song_view)
        self._song_view.setItemDelegate(self._song_delegate)
        self._song_view.setUniformItemSizes(True)  # all rows share one height, which speeds up long lists
        self._song_view.setMouseTracking(True)  # hover highlight

        self._messages = QPlainTextEdit()
        self._messages.setReadOnly(True)
        self._messages.setFixedHeight(MESSAGES_HEIGHT)

        layout = QVBoxLayout()
        layout.addWidget(self._player)
        layout.addWidget(self._song_view, stretch=1)  # the list takes all remaining height
        layout.addWidget(self._messages)

        # QMainWindow owns its layout; the content goes into one "central widget".
        central = QWidget()
        central.setLayout(layout)
        return central

    # --- Worker thread ------------------------------------------------------------------------------

    def _start_worker(self, artwork_cache: ArtworkCache) -> None:
        """Create the iTunes worker in its own thread, running for the window's lifetime."""
        self._worker_thread = QThread(self)
        # No parent: an object with a parent cannot be moved to another thread.
        self._worker = ItunesWorker(artwork_cache)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.finished.connect(self._worker.deleteLater)

        self._listPlaylistsRequested.connect(self._worker.listPlaylists)
        self._importPlaylistRequested.connect(self._worker.importPlaylist)
        self._commitPlaylistRequested.connect(self._worker.commitPlaylist)
        self._worker.playlistsListed.connect(self._on_playlists_listed)
        self._worker.playlistImported.connect(self._on_playlist_imported)
        self._worker.playlistCommitted.connect(self._on_playlist_committed)
        self._worker.progress.connect(self._show_message)
        self._worker.failed.connect(self._on_worker_failed)

        self._worker_thread.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop the worker thread before the window goes away.

        ``quit`` ends the thread's event loop once the current job (if any) has finished, so closing
        during an import waits for it.
        """
        self._player.stop()
        self._worker_thread.quit()
        self._worker_thread.wait()
        super().closeEvent(event)

    def _set_itunes_busy(self, busy: bool) -> None:
        """Mark whether a worker job runs, disabling the iTunes actions meanwhile."""
        self._itunes_busy = busy
        self._update_actions()

    def _update_actions(self) -> None:
        """Enable each toolbar action that can run now: iTunes actions only when the worker is idle,
        Save and Commit only when a playlist is loaded."""
        has_playlist = self._playlist is not None
        self._import_action.setEnabled(not self._itunes_busy)
        self._save_action.setEnabled(has_playlist)
        self._commit_action.setEnabled(has_playlist and not self._itunes_busy)

    @Slot(str)
    def _on_worker_failed(self, message: str) -> None:
        self._show_message(f"Error: {message}")
        self._set_itunes_busy(False)

    # --- Showing a playlist -------------------------------------------------------------------------

    def _show_playlist(self, playlist: Playlist, sorter_file_path: Path | None) -> None:
        """Replace the songs in the list with ``playlist``'s, in its order, and remember its sorter file."""
        self._player.stop()  # the playing song may not be in the new playlist
        self._playlist = playlist
        self._sorter_file_path = sorter_file_path
        self._song_model.set_songs(playlist.tracks)
        self.setWindowTitle(f"Playlist Sorter – {playlist.name}")
        self._update_actions()

    def _current_sorter_file(self) -> SorterFile:
        """Return the sorting state to save: the loaded playlist with its songs in the list's current order."""
        assert self._playlist is not None, "Save and Commit are disabled until a playlist is loaded"
        return SorterFile(playlist=self._playlist.model_copy(update={"tracks": self._song_model.songs()}))

    # --- Import from iTunes -------------------------------------------------------------------------

    @Slot()
    def _on_import_triggered(self) -> None:
        self._set_itunes_busy(True)  # one job at a time; cleared when the import ends
        self._listPlaylistsRequested.emit()

    @Slot(list)
    def _on_playlists_listed(self, playlist_names: list[str]) -> None:
        playlist_name, accepted = QInputDialog.getItem(
            self, "Import from iTunes", "Playlist:", playlist_names, 0, False
        )
        if not accepted:
            self._show_message("Import cancelled.")
            self._set_itunes_busy(False)
            return
        self._importPlaylistRequested.emit(playlist_name)

    @Slot(object)
    def _on_playlist_imported(self, playlist: Playlist) -> None:
        self._show_playlist(playlist, sorter_file_path=None)
        self._show_message(f"Imported {playlist.name!r} with {len(playlist.tracks)} songs.")
        self._set_itunes_busy(False)
        self._save(ask_path=True)

    # --- Open and save sorter files -----------------------------------------------------------------

    @Slot()
    def _on_open_triggered(self) -> None:
        # The dialog can only open in a folder that exists.
        SORTER_FOLDER.mkdir(parents=True, exist_ok=True)
        path_text, _selected_filter = QFileDialog.getOpenFileName(
            self, "Open sorter file", str(SORTER_FOLDER), SORTER_FILE_FILTER
        )
        if not path_text:
            return

        path = Path(path_text)
        try:
            sorter_file = load_sorter_file(path)
        except OSError as error:
            self._show_message(f"Error: could not read {path}: {error}")
            return
        except yaml.YAMLError:
            logger.warning("Could not parse %s", path, exc_info=True)
            self._show_message(f"Error: {path} is not a valid YAML file; see the log for details.")
            return
        except ValidationError:
            # The error lists every mismatch, which is too long for the messages pane.
            logger.warning("%s does not match the sorter file layout", path, exc_info=True)
            self._show_message(f"Error: {path} is not a sorter file; see the log for details.")
            return

        playlist = sorter_file.playlist
        self._show_playlist(playlist, path)
        self._show_message(f"Opened {path} ({playlist.name!r}, {len(playlist.tracks)} songs).")

    @Slot()
    def _on_save_triggered(self) -> None:
        self._save(ask_path=self._sorter_file_path is None)

    def _save(self, ask_path: bool) -> bool:
        """Save the sorting state to the remembered sorter file, or to a file the user picks.

        :param ask_path: Show a save dialog, starting in the sorter folder, even if a file is remembered.
        :return: Whether the file was saved; the user may cancel the dialog, or writing may fail.
        """
        assert self._playlist is not None, "Save and Commit are disabled until a playlist is loaded"
        path = self._sorter_file_path
        if ask_path or path is None:
            path = self._ask_sorter_file_path(self._playlist.name)
            if path is None:
                self._show_message("Sorter file not saved.")
                return False

        try:
            save_sorter_file(self._current_sorter_file(), path)
        except OSError as error:
            self._show_message(f"Error: could not save {path}: {error}")
            return False
        self._sorter_file_path = path
        self._show_message(f"Saved {path}")
        return True

    def _ask_sorter_file_path(self, playlist_name: str) -> Path | None:
        """Ask where to save a playlist's sorter file, suggesting one in the sorter folder.

        :return: The chosen path, or ``None`` if the user cancelled.
        """
        suggested_path = suggested_sorter_file_path(playlist_name)
        # The dialog can only open in a folder that exists.
        suggested_path.parent.mkdir(parents=True, exist_ok=True)
        # The dialog asks before overwriting an existing file.
        path_text, _selected_filter = QFileDialog.getSaveFileName(
            self, "Save sorter file", str(suggested_path), SORTER_FILE_FILTER
        )
        return Path(path_text) if path_text else None

    # --- Commit to iTunes ---------------------------------------------------------------------------

    @Slot()
    def _on_commit_triggered(self) -> None:
        """Ask for a new playlist name, save the sorter file, then have the worker create the playlist.

        The sorter file is saved first (UC-3 requires it), so a cancelled or failed save commits nothing.
        Whether the name is taken is checked by the worker, against iTunes.
        """
        assert self._playlist is not None, "Commit is disabled until a playlist is loaded"
        name, accepted = QInputDialog.getText(
            self, "Commit to iTunes", "Name of the new iTunes playlist:", text=f"{self._playlist.name} (sorted)"
        )
        name = name.strip()
        if not accepted or not name:
            self._show_message("Commit cancelled.")
            return
        if not self._save(ask_path=False):
            self._show_message("Commit cancelled: the sorter file was not saved.")
            return

        self._set_itunes_busy(True)
        self._commitPlaylistRequested.emit(name, [song.id for song in self._song_model.songs()])

    @Slot(object)
    def _on_playlist_committed(self, playlist: Playlist) -> None:
        self._show_message(f"Created the iTunes playlist {playlist.name!r} with {len(playlist.tracks)} songs.")
        self._set_itunes_busy(False)

    # --- Playback -----------------------------------------------------------------------------------

    def _connect_player(self) -> None:
        self._song_delegate.rowActionTriggered.connect(self._on_row_action_triggered)
        self._player.currentSongChanged.connect(self._on_current_song_changed)
        self._player.songFinished.connect(self._play_next_song)
        self._player.nextRequested.connect(self._play_next_song)
        self._player.previousRequested.connect(self._on_previous_requested)
        self._player.playbackFailed.connect(self._on_playback_failed)

    @Slot(str, QModelIndex)
    def _on_row_action_triggered(self, action_name: str, index: QModelIndex) -> None:
        song: Song = index.data(SongRole)
        if action_name == PLAY_FROM_START:
            self._player.play(song)
        elif action_name == PLAY_LAST_SECONDS:
            self._player.play_last_seconds(song)

    @Slot(object)
    def _on_current_song_changed(self, song: Song | None) -> None:
        self._song_model.set_playing_song(song.id if song is not None else None)

    @Slot()
    def _play_next_song(self) -> None:
        """Play the next playable song after the playing one in sorting order; stop after the last."""
        playing_row = self._song_model.playing_row()
        after_row = playing_row if playing_row is not None else -1
        songs = self._song_model.songs()
        next_row = next_playable_index(songs, after_row)
        # Songs between the playing one and the next playable one have no file; say why they are skipped.
        for skipped_song in songs[after_row + 1 : next_row if next_row is not None else len(songs)]:
            self._show_message(f"Skipped {skipped_song.name!r}: iTunes has no file for it.")
        if next_row is None:
            self._player.stop()
            self._show_message("Reached the end of the playlist.")
            return
        self._play_row(next_row)

    @Slot(object)
    def _on_previous_requested(self, song: Song) -> None:
        """Play the previous playable song; at the top of the list, restart the current one."""
        playing_row = self._song_model.playing_row()
        previous_row = (
            previous_playable_index(self._song_model.songs(), playing_row) if playing_row is not None else None
        )
        if previous_row is None:
            self._player.play(song)
            return
        self._play_row(previous_row)

    @Slot(str)
    def _on_playback_failed(self, message: str) -> None:
        self._show_message(f"Error: {message}")
        self._play_next_song()

    def _play_row(self, row: int) -> None:
        """Play the song at ``row`` and scroll the list so that it is visible in the middle."""
        index = self._song_model.index(row)
        self._player.play(index.data(SongRole))
        self._song_view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)

    # --- Messages -----------------------------------------------------------------------------------

    @Slot(str)
    def _show_message(self, message: str) -> None:
        """Append a timestamped line to the messages pane and the log."""
        logger.info(message)
        self._messages.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")
