"""The sorter's main window: toolbar, player, song list and messages, top to bottom.

*Import from iTunes* (UC-1, UC-4), the player (UC-5) and the per-song play buttons (UC-6) work. The other
toolbar actions and *Send to a group* are placeholders for later use cases.

Playback follows the sorting order: when a song ends, the next song in the list plays and the list scrolls
to it. The shared ``PlayerWidget`` only plays songs; this window decides which one comes next.
"""

from datetime import datetime
from pathlib import Path

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
from itunes_tools.sorter.sorter_file import SorterFile, save_sorter_file, suggested_sorter_file_path

logger = get_logger(__name__)

MESSAGES_HEIGHT = 90
SORTER_FILE_FILTER = "Sorter files (*.yaml);;All files (*)"


class MainWindow(QMainWindow):
    # Requests for the worker thread. Emitting a signal queues the call in the worker's event loop;
    # calling the worker's slots directly would run them here, in the UI thread.
    _listPlaylistsRequested = Signal()
    _importPlaylistRequested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Playlist Sorter")
        self.resize(900, 600)

        artwork_cache = ArtworkCache()
        self._song_model = SongListModel(artwork_cache, self)
        self._player = PlayerWidget(artwork_cache)

        self._create_toolbar()
        self.setCentralWidget(self._create_central_widget())
        self._connect_player()
        self._start_worker(artwork_cache)
        self._show_message("Ready. Use 'Import from iTunes' to load a playlist.")

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

        # Placeholders for later use cases; disabled until implemented.
        placeholders = [
            ("Open", "Open a saved sorter file (coming soon)", QStyle.StandardPixmap.SP_DialogOpenButton),
            ("Save", "Save the sorting progress (coming soon)", QStyle.StandardPixmap.SP_DialogSaveButton),
            ("Add group", "Add a group of songs (coming soon)", QStyle.StandardPixmap.SP_FileDialogNewFolder),
            (
                "Commit to iTunes",
                "Create the sorted playlist in iTunes (coming soon)",
                QStyle.StandardPixmap.SP_ArrowUp,
            ),
        ]
        for text, tooltip, icon in placeholders:
            self._add_action(toolbar, text, tooltip, icon).setEnabled(False)

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
        self._worker.playlistsListed.connect(self._on_playlists_listed)
        self._worker.playlistImported.connect(self._on_playlist_imported)
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

    # --- Import from iTunes -------------------------------------------------------------------------

    @Slot()
    def _on_import_triggered(self) -> None:
        self._import_action.setEnabled(False)  # one job at a time; re-enabled when the import ends
        self._listPlaylistsRequested.emit()

    @Slot(list)
    def _on_playlists_listed(self, playlist_names: list[str]) -> None:
        playlist_name, accepted = QInputDialog.getItem(
            self, "Import from iTunes", "Playlist:", playlist_names, 0, False
        )
        if not accepted:
            self._show_message("Import cancelled.")
            self._import_action.setEnabled(True)
            return
        self._importPlaylistRequested.emit(playlist_name)

    @Slot(object)
    def _on_playlist_imported(self, playlist: Playlist) -> None:
        self._player.stop()  # the playing song may not be in the new playlist
        self._song_model.set_songs(playlist.tracks)
        self.setWindowTitle(f"Playlist Sorter – {playlist.name}")
        self._show_message(f"Imported {playlist.name!r} with {len(playlist.tracks)} songs.")
        self._import_action.setEnabled(True)
        self._save_imported_playlist(playlist)

    def _save_imported_playlist(self, playlist: Playlist) -> None:
        """Ask where to save the playlist's sorter file, starting in the sorter folder, and save it."""
        suggested_path = suggested_sorter_file_path(playlist.name)
        # The dialog can only open in a folder that exists.
        suggested_path.parent.mkdir(parents=True, exist_ok=True)
        # The dialog asks before overwriting an existing file.
        path_text, _selected_filter = QFileDialog.getSaveFileName(
            self, "Save sorter file", str(suggested_path), SORTER_FILE_FILTER
        )
        if not path_text:
            self._show_message("Sorter file not saved.")
            return

        try:
            save_sorter_file(SorterFile(playlist=playlist), Path(path_text))
        except OSError as error:
            self._show_message(f"Error: could not save {path_text}: {error}")
            return
        self._show_message(f"Saved {path_text}")

    @Slot(str)
    def _on_worker_failed(self, message: str) -> None:
        self._show_message(f"Error: {message}")
        self._import_action.setEnabled(True)

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
