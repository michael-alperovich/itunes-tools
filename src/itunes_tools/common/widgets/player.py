"""An iTunes-style player for songs' local audio files, shared between the applications.

The player plays one song at a time with Qt Multimedia, straight from ``Song.location``; iTunes is not
involved. It does not know any play order: when a song ends it emits ``songFinished``, and its *Next* and
*Previous* buttons emit ``nextRequested`` and ``previousRequested``. The application decides which song
plays next and calls ``play`` again.

Layout, left to right: artwork; the title, ``artist – album`` and a seek bar with elapsed and remaining
time; then the previous / play-pause / next buttons and the volume.
"""

from PySide6.QtCore import QSize, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QFont, QIcon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QAbstractSlider,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from itunes_tools.common.artwork_cache import ArtworkCache
from itunes_tools.common.models import Song
from itunes_tools.common.widgets.artwork import load_artwork_pixmap
from itunes_tools.common.widgets.icons import text_colored_icon

ARTWORK_SIZE = 64
BUTTON_ICON_SIZE = 24
VOLUME_SLIDER_WIDTH = 90
DEFAULT_VOLUME_PERCENT = 80
SEEK_PAGE_STEP_MS = 10_000  # clicking the seek bar beside its handle jumps this far
# Like iTunes, *Previous* restarts the current song once it has played this long.
RESTART_INSTEAD_OF_PREVIOUS_AFTER_MS = 3_000


def format_time(milliseconds: int) -> str:
    """Format a position or duration as ``m:ss`` (minutes are not wrapped into hours)."""
    seconds = max(0, milliseconds) // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


def last_seconds_start(duration_ms: int, seconds: int) -> int:
    """Return the position, in milliseconds, ``seconds`` before the end; 0 for shorter songs."""
    return max(0, duration_ms - seconds * 1000)


class PlayerWidget(QWidget):
    """Plays songs from their local files and shows the current song, its progress and the controls."""

    currentSongChanged = Signal(object)
    """The song now loaded in the player (``Song``), or ``None`` after ``stop``."""
    songFinished = Signal(object)
    """The ``Song`` that just played to its end."""
    nextRequested = Signal()
    """The *Next* button was clicked."""
    previousRequested = Signal(object)
    """The *Previous* button was clicked at the start of the current ``Song`` (otherwise it restarts)."""
    playbackFailed = Signal(str)
    """A song cannot be played (no file, unreadable file); the message names the song."""

    def __init__(self, artwork_cache: ArtworkCache, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._artwork_cache = artwork_cache
        self._song: Song | None = None
        # Where to start the song once its file has loaded (seeking before that is ignored by Qt).
        # Exactly one of the two is set while a song loads, and both are None after the start.
        self._pending_start_ms: int | None = None
        self._pending_seconds_from_end: int | None = None

        self._audio_output = QAudioOutput(self)
        self._audio_output.setVolume(DEFAULT_VOLUME_PERCENT / 100)
        self._media_player = QMediaPlayer(self)
        self._media_player.setAudioOutput(self._audio_output)

        self._create_layout()
        self._connect_media_player()
        self._show_song(None)

    # --- Public interface ---------------------------------------------------------------------------

    def current_song(self) -> Song | None:
        """Return the song loaded in the player, playing or paused, or ``None``."""
        return self._song

    def play(self, song: Song, start_ms: int = 0) -> None:
        """Play ``song`` from ``start_ms`` milliseconds, replacing the current song."""
        self._start(song, start_ms=start_ms, seconds_from_end=None)

    def play_last_seconds(self, song: Song, seconds: int = 10) -> None:
        """Play the last ``seconds`` of ``song`` (all of it if it is shorter)."""
        self._start(song, start_ms=None, seconds_from_end=seconds)

    @Slot()
    def toggle_play_pause(self) -> None:
        """Pause a playing song, or resume a paused one. Does nothing without a song."""
        if self._song is None:
            return
        if self._media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._media_player.pause()
        else:
            self._media_player.play()

    def stop(self) -> None:
        """Stop playback and unload the current song."""
        self._media_player.stop()
        self._media_player.setSource(QUrl())
        self._pending_start_ms = None
        self._pending_seconds_from_end = None
        self._song = None
        self._show_song(None)
        self.currentSongChanged.emit(None)

    # --- Layout -------------------------------------------------------------------------------------

    def _create_layout(self) -> None:
        self._previous_button = self._create_button("Previous song", QStyle.StandardPixmap.SP_MediaSkipBackward)
        self._previous_button.clicked.connect(self._on_previous_clicked)
        self._play_pause_button = self._create_button("Play / Pause", QStyle.StandardPixmap.SP_MediaPlay)
        self._play_pause_button.clicked.connect(self.toggle_play_pause)
        self._next_button = self._create_button("Next song", QStyle.StandardPixmap.SP_MediaSkipForward)
        self._next_button.clicked.connect(self.nextRequested)

        volume_icon = QLabel()
        volume_icon.setPixmap(self._icon(QStyle.StandardPixmap.SP_MediaVolume).pixmap(16, 16))
        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(DEFAULT_VOLUME_PERCENT)
        self._volume_slider.setFixedWidth(VOLUME_SLIDER_WIDTH)
        self._volume_slider.setToolTip("Volume")
        self._volume_slider.valueChanged.connect(self._on_volume_changed)

        self._artwork_label = QLabel()
        self._artwork_label.setFixedSize(ARTWORK_SIZE, ARTWORK_SIZE)
        self._artwork_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._title_label = self._create_text_label()
        title_font = QFont(self._title_label.font())
        title_font.setBold(True)
        self._title_label.setFont(title_font)
        self._details_label = self._create_text_label()

        self._elapsed_label = QLabel()
        self._remaining_label = QLabel()
        self._seek_slider = QSlider(Qt.Orientation.Horizontal)
        self._seek_slider.setPageStep(SEEK_PAGE_STEP_MS)
        self._seek_slider.setToolTip("Drag to move within the song")
        # Seek when the handle is released, not on every move, so the playback position does not fight
        # the drag. Clicks beside the handle (page steps) seek at once.
        self._seek_slider.sliderMoved.connect(self._show_position)
        self._seek_slider.sliderReleased.connect(self._on_seek_released)
        self._seek_slider.actionTriggered.connect(self._on_seek_action)

        controls = QHBoxLayout()
        for widget in (self._previous_button, self._play_pause_button, self._next_button, volume_icon):
            controls.addWidget(widget)
        controls.addWidget(self._volume_slider)

        progress = QHBoxLayout()
        progress.addWidget(self._elapsed_label)
        progress.addWidget(self._seek_slider, stretch=1)
        progress.addWidget(self._remaining_label)

        song_info = QVBoxLayout()
        song_info.setSpacing(0)
        song_info.addWidget(self._title_label)
        song_info.addWidget(self._details_label)
        song_info.addLayout(progress)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self._artwork_label)
        layout.addLayout(song_info, stretch=1)
        layout.addSpacing(12)
        layout.addLayout(controls)

    def _create_button(self, tooltip: str, icon: QStyle.StandardPixmap) -> QToolButton:
        button = QToolButton()
        button.setIcon(self._icon(icon))
        button.setIconSize(QSize(BUTTON_ICON_SIZE, BUTTON_ICON_SIZE))
        button.setToolTip(tooltip)
        button.setAutoRaise(True)  # flat until hovered, like media player buttons
        return button

    def _icon(self, standard_pixmap: QStyle.StandardPixmap) -> QIcon:
        """Return a standard icon in the text colour, visible on dark backgrounds too."""
        return text_colored_icon(self.style(), self.palette(), standard_pixmap)

    @staticmethod
    def _create_text_label() -> QLabel:
        label = QLabel()
        # Ignored width: a long title is cut off instead of widening the window.
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        return label

    def _show_song(self, song: Song | None) -> None:
        """Show the song's artwork and text, or an empty player, and reset the progress."""
        if song is None:
            self._artwork_label.clear()
            self._title_label.setText("Not playing")
            self._details_label.setText("")
        else:
            self._artwork_label.setPixmap(load_artwork_pixmap(self._artwork_cache, song, ARTWORK_SIZE))
            self._title_label.setText(song.name)
            self._details_label.setText(f"{song.artist} – {song.album}")
        has_song = song is not None
        for widget in (self._previous_button, self._play_pause_button, self._next_button, self._seek_slider):
            widget.setEnabled(has_song)
        self._seek_slider.setRange(0, 0)
        self._show_position(0)

    @Slot(int)
    def _show_position(self, position_ms: int) -> None:
        self._elapsed_label.setText(format_time(position_ms))
        remaining_ms = max(0, self._seek_slider.maximum() - position_ms)
        self._remaining_label.setText(f"-{format_time(remaining_ms)}")

    # --- Playback -----------------------------------------------------------------------------------

    def _connect_media_player(self) -> None:
        self._media_player.positionChanged.connect(self._on_position_changed)
        self._media_player.durationChanged.connect(self._on_duration_changed)
        self._media_player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._media_player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._media_player.errorOccurred.connect(self._on_error)

    def _start(self, song: Song, start_ms: int | None, seconds_from_end: int | None) -> None:
        self._media_player.stop()
        self._song = song
        self._pending_start_ms = start_ms
        self._pending_seconds_from_end = seconds_from_end
        self._show_song(song)
        self.currentSongChanged.emit(song)

        if song.location is None:
            self._media_player.setSource(QUrl())
            self.playbackFailed.emit(f"Cannot play {song.name!r}: iTunes has no file for it.")
            return
        self._media_player.setSource(QUrl.fromLocalFile(str(song.location)))
        # Setting the same file again (replaying the current song) does not reload it, so durationChanged
        # does not come; take the known duration now. For a new file it is 0 until durationChanged.
        self._on_duration_changed(self._media_player.duration())
        self._media_player.play()

    @Slot(QMediaPlayer.MediaStatus)
    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self._apply_pending_start()
        elif status == QMediaPlayer.MediaStatus.EndOfMedia and self._song is not None:
            self.songFinished.emit(self._song)

    def _apply_pending_start(self) -> None:
        """Seek to the requested start position, once the file has loaded and its duration is known."""
        if self._pending_seconds_from_end is not None:
            duration_ms = self._media_player.duration()
            if duration_ms <= 0 and self._song is not None:  # unknown yet; fall back to iTunes' duration
                duration_ms = self._song.duration * 1000
            start_ms = last_seconds_start(duration_ms, self._pending_seconds_from_end)
        elif self._pending_start_ms is not None:
            start_ms = self._pending_start_ms
        else:
            return  # already started
        self._pending_start_ms = None
        self._pending_seconds_from_end = None
        if start_ms > 0:
            self._media_player.setPosition(start_ms)

    @Slot(int)
    def _on_position_changed(self, position_ms: int) -> None:
        if not self._seek_slider.isSliderDown():  # the user is dragging; keep their handle position
            self._seek_slider.setValue(position_ms)
            self._show_position(position_ms)

    @Slot(int)
    def _on_duration_changed(self, duration_ms: int) -> None:
        self._seek_slider.setRange(0, max(0, duration_ms))
        self._show_position(self._seek_slider.value())

    @Slot(QMediaPlayer.PlaybackState)
    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        icon = QStyle.StandardPixmap.SP_MediaPause if is_playing else QStyle.StandardPixmap.SP_MediaPlay
        self._play_pause_button.setIcon(self._icon(icon))

    @Slot(QMediaPlayer.Error, str)
    def _on_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        song_name = self._song.name if self._song is not None else "the song"
        self.playbackFailed.emit(f"Cannot play {song_name!r}: {error_string}")

    # --- Controls -----------------------------------------------------------------------------------

    @Slot()
    def _on_previous_clicked(self) -> None:
        if self._song is None:
            return
        if self._media_player.position() > RESTART_INSTEAD_OF_PREVIOUS_AFTER_MS:
            self._media_player.setPosition(0)
        else:
            self.previousRequested.emit(self._song)

    @Slot()
    def _on_seek_released(self) -> None:
        self._media_player.setPosition(self._seek_slider.value())

    @Slot(int)
    def _on_seek_action(self, action: int) -> None:
        # Dragging is handled on release. For page steps and arrow keys, the slider position already
        # holds the new value when this signal arrives.
        if action != QAbstractSlider.SliderAction.SliderMove.value:
            self._media_player.setPosition(self._seek_slider.sliderPosition())

    @Slot(int)
    def _on_volume_changed(self, percent: int) -> None:
        self._audio_output.setVolume(percent / 100)
