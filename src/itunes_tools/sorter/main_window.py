"""The sorter's main window: toolbar, player, song list and messages, top to bottom.

*Import from iTunes* (UC-1, UC-4), *Open* and *Save* of sorter files (UC-2), *Commit to iTunes* (UC-3),
the player (UC-5), the per-song play buttons (UC-6), groups (UC-7) and moving songs and groups by
selection, drag and drop, and cut and paste (UC-8, in ``SongTreeView``) work.

iTunes work (listing, importing, committing) runs in ``ItunesWorker`` on its own thread, one job at a
time; opening and saving sorter files is local and needs no iTunes.

The song list is a tree: top-level songs and groups of songs. Playback follows the sorting order, read
top to bottom with group contents in place: when a song ends, the next song plays and the list scrolls
to it, expanding its group if collapsed. The shared ``PlayerWidget`` only plays songs; this window
decides which one comes next.
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
from itunes_tools.sorter.group_dialogs import ask_group, ask_year_range
from itunes_tools.sorter.itunes_worker import ItunesWorker
from itunes_tools.sorter.playback import next_playable_index, previous_playable_index
from itunes_tools.sorter.song_list import SongListModel, SongRole
from itunes_tools.sorter.song_row_delegate import (
    DELETE_GROUP,
    MOVE_TO_GROUP,
    PLAY_FROM_START,
    PLAY_LAST_SECONDS,
    RENAME_GROUP,
    TOGGLE_GROUP,
)
from itunes_tools.sorter.song_tree_view import SongTreeView
from itunes_tools.sorter.sorter_file import (
    SorterFile,
    load_sorter_file,
    save_sorter_file,
    suggested_sorter_file_path,
)
from itunes_tools.sorter.sorting_items import (
    SortingItem,
    items_from_sorter_file,
    season_group_names,
    sorter_file_from_items,
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

        # The playlist being sorted (its id and name; songs and groups live in the model) and the sorter
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

        self._add_group_action = self._add_action(
            toolbar,
            "Add group",
            "Add an empty group above the current row",
            QStyle.StandardPixmap.SP_FileDialogNewFolder,
        )
        self._add_group_action.triggered.connect(self._on_add_group_triggered)

        self._add_season_groups_action = self._add_action(
            toolbar,
            "Add season groups",
            "Add empty groups Winter, Spring, Summer and Fall for a range of years above the current row",
            QStyle.StandardPixmap.SP_FileDialogListView,
        )
        self._add_season_groups_action.triggered.connect(self._on_add_season_groups_triggered)

        self._commit_action = self._add_action(
            toolbar,
            "Commit to iTunes",
            "Save the sorter file and create the sorted playlist in iTunes under a new name",
            QStyle.StandardPixmap.SP_ArrowUp,
        )
        self._commit_action.triggered.connect(self._on_commit_triggered)

        # Save, Commit and the group actions need a playlist; see _update_actions.
        self._update_actions()

    def _add_action(self, toolbar: QToolBar, text: str, tooltip: str, icon: QStyle.StandardPixmap) -> QAction:
        action = QAction(self.style().standardIcon(icon), text, self)
        action.setToolTip(tooltip)  # shown when hovering the toolbar button
        action.setStatusTip(tooltip)  # shown in the status bar meanwhile
        toolbar.addAction(action)
        return action

    def _create_central_widget(self) -> QWidget:
        # A tree view: groups are top-level rows that expand to show their songs.
        self._song_view = SongTreeView(self._song_model)
        self._song_view.messageRequested.connect(self._show_message)

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
        Save, Commit and the group actions only when a playlist is loaded."""
        has_playlist = self._playlist is not None
        self._import_action.setEnabled(not self._itunes_busy)
        self._save_action.setEnabled(has_playlist)
        self._add_group_action.setEnabled(has_playlist)
        self._add_season_groups_action.setEnabled(has_playlist)
        self._commit_action.setEnabled(has_playlist and not self._itunes_busy)

    @Slot(str)
    def _on_worker_failed(self, message: str) -> None:
        self._show_message(f"Error: {message}")
        self._set_itunes_busy(False)

    # --- Showing a playlist -------------------------------------------------------------------------

    def _show_playlist(self, playlist: Playlist, items: list[SortingItem], sorter_file_path: Path | None) -> None:
        """Show ``items`` (``playlist``'s songs and groups) in the list and remember the playlist and its file.

        Groups start expanded, empty ones too, so songs moved into them later are visible.
        """
        self._player.stop()  # the playing song may not be in the new playlist
        self._playlist = playlist
        self._sorter_file_path = sorter_file_path
        self._song_model.set_items(items)
        # Groups open by default. expandAll skips empty groups, so expand every top-level row instead.
        for row in range(self._song_model.rowCount()):
            self._song_view.expand(self._song_model.index(row, 0))
        self.setWindowTitle(f"Playlist Sorter – {playlist.name}")
        self._update_actions()

    def _current_sorter_file(self) -> SorterFile:
        """Return the sorting state to save: the loaded playlist with the list's current songs and groups."""
        assert self._playlist is not None, "Save and Commit are disabled until a playlist is loaded"
        return sorter_file_from_items(self._playlist, self._song_model.items())

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
        self._show_playlist(playlist, list(playlist.tracks), sorter_file_path=None)
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
        self._show_playlist(playlist, items_from_sorter_file(sorter_file), path)
        self._show_message(
            f"Opened {path} ({playlist.name!r}, {len(playlist.tracks)} songs, {len(sorter_file.groups)} groups)."
        )

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
        self._song_view.row_delegate.rowActionTriggered.connect(self._on_row_action_triggered)
        self._player.currentSongChanged.connect(self._on_current_song_changed)
        self._player.songFinished.connect(self._play_next_song)
        self._player.nextRequested.connect(self._play_next_song)
        self._player.previousRequested.connect(self._on_previous_requested)
        self._player.playbackFailed.connect(self._on_playback_failed)

    @Slot(str, QModelIndex)
    def _on_row_action_triggered(self, action_name: str, index: QModelIndex) -> None:
        if action_name == PLAY_FROM_START:
            self._player.play(index.data(SongRole))
        elif action_name == PLAY_LAST_SECONDS:
            self._player.play_last_seconds(index.data(SongRole))
        elif action_name == MOVE_TO_GROUP:
            self._move_songs_to_group(index)
        elif action_name == RENAME_GROUP:
            self._rename_group(index.row())
        elif action_name == DELETE_GROUP:
            self._delete_group(index.row())
        elif action_name == TOGGLE_GROUP:
            self._song_view.setExpanded(index, not self._song_view.isExpanded(index))

    @Slot(object)
    def _on_current_song_changed(self, song: Song | None) -> None:
        self._song_model.set_playing_song(song.id if song is not None else None)

    @Slot()
    def _play_next_song(self) -> None:
        """Play the next playable song after the playing one in sorting order; stop after the last."""
        playing_position = self._song_model.playing_position()
        after_position = playing_position if playing_position is not None else -1
        songs = self._song_model.songs()
        next_position = next_playable_index(songs, after_position)
        # Songs between the playing one and the next playable one have no file; say why they are skipped.
        for skipped_song in songs[after_position + 1 : next_position if next_position is not None else len(songs)]:
            self._show_message(f"Skipped {skipped_song.name!r}: iTunes has no file for it.")
        if next_position is None:
            self._player.stop()
            self._show_message("Reached the end of the playlist.")
            return
        self._play_position(next_position)

    @Slot(object)
    def _on_previous_requested(self, song: Song) -> None:
        """Play the previous playable song; at the top of the list, restart the current one."""
        playing_position = self._song_model.playing_position()
        previous_position = (
            previous_playable_index(self._song_model.songs(), playing_position)
            if playing_position is not None
            else None
        )
        if previous_position is None:
            self._player.play(song)
            return
        self._play_position(previous_position)

    @Slot(str)
    def _on_playback_failed(self, message: str) -> None:
        self._show_message(f"Error: {message}")
        self._play_next_song()

    def _play_position(self, position: int) -> None:
        """Play the song at flat ``position`` in sorting order and scroll the list to show it in the middle.

        ``QTreeView.scrollTo`` also expands the song's group when it is collapsed.
        """
        index = self._song_model.index_at_position(position)
        self._player.play(index.data(SongRole))
        self._song_view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)

    # --- Groups -------------------------------------------------------------------------------------

    @Slot()
    def _on_add_group_triggered(self) -> None:
        name = self._ask_group_name("Add group", "Name of the new group:", "")
        if name is not None:
            self._insert_groups([name])

    @Slot()
    def _on_add_season_groups_triggered(self) -> None:
        """Add empty groups for every season of a range of years, oldest first, skipping names already used."""
        years = ask_year_range(self)
        if years is None:
            return
        taken_names = set(self._song_model.group_names())
        all_names = season_group_names(*years)
        names = [name for name in all_names if name not in taken_names]
        skipped_names = [name for name in all_names if name in taken_names]
        if skipped_names:
            self._show_message(f"Skipped groups that exist already: {', '.join(skipped_names)}.")
        self._insert_groups(names)

    def _insert_groups(self, names: list[str]) -> None:
        """Insert empty groups above the current row's top-level item (at the end when nothing is current).

        A song inside a group has its group as top-level item, so groups are never nested.
        """
        if not names:
            return
        top_row = self._song_model.top_level_row(self._song_view.currentIndex())
        self._song_model.insert_groups(top_row, names)
        # Groups open by default, so songs moved into them stay visible.
        for row in range(top_row, top_row + len(names)):
            self._song_view.expand(self._song_model.index(row, 0))
        self._song_view.scrollTo(self._song_model.index(top_row, 0))
        self._show_message(f"Added {len(names)} {'group' if len(names) == 1 else 'groups'}: {', '.join(names)}.")

    def _rename_group(self, top_row: int) -> None:
        old_name = self._song_model.index(top_row, 0).data()
        name = self._ask_group_name("Rename group", f"New name of the group {old_name!r}:", old_name)
        if name is not None and name != old_name:
            self._song_model.rename_group(top_row, name)
            self._show_message(f"Renamed the group {old_name!r} to {name!r}.")

    def _delete_group(self, top_row: int) -> None:
        name = self._song_model.index(top_row, 0).data()
        self._song_model.delete_group(top_row)
        self._show_message(f"Deleted the group {name!r}; its songs stay in place.")

    def _move_songs_to_group(self, song_index: QModelIndex) -> None:
        """Ask for a group (with a search box) and move songs to the end of it, in playlist order.

        The selected songs move when the clicked song is one of them; otherwise only the clicked song.
        """
        group_names = self._song_model.group_names()
        if not group_names:
            self._show_message("There are no groups yet; add one with 'Add group'.")
            return
        group_name = ask_group(self, group_names)
        if group_name is None:
            return
        song_indexes = self._song_view.selected_songs_for(song_index)
        group_row = self._song_model.group_row(group_name)
        assert group_row is not None, "the dialog offers existing group names only"
        # Described before the move, which makes the indexes stale.
        if len(song_indexes) == 1:
            song: Song = song_indexes[0].data(SongRole)
            message = f"Moved {song.name!r} to the group {group_name!r}."
        else:
            message = f"Moved {len(song_indexes)} songs to the group {group_name!r}."
        group_index = self._song_model.index(group_row, 0)
        self._song_model.move_items(song_indexes, group_index, self._song_model.rowCount(group_index))
        self._show_message(message)

    def _ask_group_name(self, title: str, label: str, text: str) -> str | None:
        """Ask for a group name; return it stripped, or ``None`` if cancelled, blank or already used.

        Group names must be unique, since groups are picked by name. Keeping the current name of a
        group being renamed (``text``) is allowed.
        """
        name, accepted = QInputDialog.getText(self, title, label, text=text)
        name = name.strip()
        if not accepted or not name:
            return None
        if name != text and name in self._song_model.group_names():
            self._show_message(f"Error: a group named {name!r} exists; choose another name.")
            return None
        return name

    # --- Messages -----------------------------------------------------------------------------------

    @Slot(str)
    def _show_message(self, message: str) -> None:
        """Append a timestamped line to the messages pane and the log."""
        logger.info(message)
        self._messages.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")
