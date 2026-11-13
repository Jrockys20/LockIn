"""Video local manual o automático; una sola ventana y audio configurable."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)


from lockin.widgets import ResponsiveColumns, ScrollSafeSlider


VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mkv", ".mov", ".avi", ".webm", ".wmv"}
VIDEO_FILTER = "Videos (*.mp4 *.m4v *.mkv *.mov *.avi *.webm *.wmv);;Todos los archivos (*)"


def validate_video_path(value: str | Path) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError("Selecciona un archivo de video, no una carpeta.")
        if path.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError("Elige un video MP4, M4V, MKV, MOV, AVI, WebM o WMV.")
        # Solo verifica acceso y contenido; Qt comprueba el formato al reproducir.
        with path.open("rb") as source:
            if not source.read(1):
                raise ValueError("El archivo está vacío. Elige otro video.")
        return path
    except (OSError, RuntimeError) as exc:
        raise ValueError(
            "No se puede acceder al video. Comprueba que exista, "
            "que tengas permiso de lectura y vuelve a seleccionarlo."
        ) from exc


class PlaybackWindow(QWidget):
    finished = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("LockIn — Video")
        self.resize(960, 600)
        self.setMinimumSize(480, 320)
        self._closing = False
        self._started = False
        self._repeat = False
        self._result = "Reproducción detenida."
        self.video_widget = QVideoWidget(self)
        self.video_widget.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.info = QLabel("Cargando video… · Esc para cerrar")
        self.info.setTextFormat(Qt.TextFormat.PlainText)
        self.info.setWordWrap(True)
        close_button = QPushButton("Cerrar (Esc)")
        close_button.clicked.connect(self.close)
        controls = QHBoxLayout()
        controls.addWidget(self.info, 1)
        controls.addWidget(close_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.video_widget, 1)
        layout.addLayout(controls)

        self.audio_output = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.player.setLoops(1)
        self.player.mediaStatusChanged.connect(self._media_status_changed)
        self.player.errorOccurred.connect(self._error_occurred)
        self.escape_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.escape_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self.escape_shortcut.activated.connect(self.close)

    def set_audio(self, volume: int, muted: bool) -> None:
        self.audio_output.setVolume(max(0, min(volume, 100)) / 100.0)
        self.audio_output.setMuted(muted)

    def start_video(
        self, path: Path, *, volume: int = 50,
        muted: bool = False, fullscreen: bool = False, repeat: bool = False,
    ) -> None:
        if self._started or self._closing:
            return
        path = validate_video_path(path)
        self._started = True
        self._repeat = repeat
        self.player.setLoops(QMediaPlayer.Loops.Infinite if repeat else QMediaPlayer.Loops.Once)
        self.set_audio(volume, muted)
        if self.parentWidget() is not None:
            self.setScreen(self.parentWidget().screen())
        # Solo URLs de archivo local; no se recibe una URL de red desde la interfaz.
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        if self._closing:
            return
        if fullscreen:
            self.showFullScreen()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        self.player.play()

    @Slot(QMediaPlayer.MediaStatus)
    def _media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if self._closing:
            return
        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.fail(self.player.errorString() or "El formato no se puede reproducir.")
        elif status == QMediaPlayer.MediaStatus.EndOfMedia and not self._repeat:
            self._result = "El video terminó."
            self.close()
        elif status == QMediaPlayer.MediaStatus.LoadedMedia:
            if not self.player.hasVideo():
                self.fail("El archivo no contiene una pista de video reproducible.")
            elif not self.player.hasAudio():
                self.info.setText("Video sin pista de audio · Esc para cerrar")
            else:
                self.info.setText("Reproduciendo video con audio · Esc para cerrar")

    @Slot(QMediaPlayer.Error, str)
    def _error_occurred(self, error: QMediaPlayer.Error, message: str) -> None:
        if error != QMediaPlayer.Error.NoError and not self._closing:
            self.fail(message or "El formato o el códec no es compatible.")

    def fail(self, message: str) -> None:
        if self._closing:
            return
        self._result = (
            f"No se pudo reproducir el video: {message} "
            "Prueba otro archivo o formato."
        )
        self.close()

    def finish(self, message: str) -> None:
        if not self._closing:
            self._result = message
            self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._closing:
            self._closing = True
            # stop y la fuente vacía detienen el sonido y sueltan el archivo.
            self.player.stop()
            self.player.setSource(QUrl())
            self.finished.emit(self._result)
        event.accept()


class VideoPanel(QGroupBox):
    playback_finished = Signal(bool, str)

    def __init__(self, parent=None, playback_factory=PlaybackWindow) -> None:
        super().__init__("Video de alerta", parent)
        self._playback_factory = playback_factory
        self._video_path: Path | None = None
        self._playback: PlaybackWindow | None = None
        self._shutting_down = False
        self._automatic = False

        self.path_field = QLineEdit()
        self.path_field.setReadOnly(True)
        self.path_field.setObjectName("videoPath")
        self.path_field.setPlaceholderText("Ningún video seleccionado")
        self.path_field.setAccessibleName("Video seleccionado")
        self.choose_button = QPushButton("Elegir video…")
        self.play_button = QPushButton("Probar video")
        selection = QWidget()
        selection.setProperty("role", "plain")
        selection_layout = QVBoxLayout(selection)
        selection_layout.setContentsMargins(0, 0, 0, 0)
        selection_layout.setSpacing(5)
        selection_layout.addWidget(self.path_field)
        selection_buttons = QHBoxLayout()
        selection_buttons.addWidget(self.choose_button)
        selection_buttons.addWidget(self.play_button)
        selection_buttons.addStretch()
        selection_layout.addLayout(selection_buttons)

        self.volume_label = QLabel("Volumen: 50 %")
        self.volume_slider = ScrollSafeSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(50)
        self.volume_slider.setAccessibleName("Volumen del video")
        self.mute_checkbox = QCheckBox("Silenciar")
        self.fullscreen_checkbox = QCheckBox("Pantalla completa al probar")
        self.fullscreen_checkbox.setToolTip("Solo afecta a Probar video; las alertas automáticas usan pantalla completa.")
        audio = QWidget()
        audio.setProperty("role", "plain")
        audio_layout = QVBoxLayout(audio)
        audio_layout.setContentsMargins(0, 0, 0, 0)
        audio_levels = QHBoxLayout()
        audio_levels.addWidget(self.volume_label)
        audio_levels.addWidget(self.volume_slider, 1)
        audio_layout.addLayout(audio_levels)
        audio_options = ResponsiveColumns(
            self.mute_checkbox, self.fullscreen_checkbox, breakpoint=360, stretch=(1, 2)
        )
        audio_layout.addWidget(audio_options)

        self.message = QLabel(
            "Elige un video de tu equipo. Pulsa «Probar video» para reproducirlo."
        )
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        layout = QVBoxLayout(self)
        self.columns = ResponsiveColumns(selection, audio, breakpoint=680, stretch=(3, 2))
        layout.addWidget(self.columns)
        layout.addWidget(self.message)

        self.choose_button.clicked.connect(self.choose_video)
        self.play_button.clicked.connect(self.play_video)
        self.volume_slider.valueChanged.connect(self._audio_changed)
        self.mute_checkbox.toggled.connect(self._audio_changed)
        self._update_controls()

    def _update_controls(self) -> None:
        idle = self._playback is None and not self._shutting_down
        self.choose_button.setEnabled(idle)
        self.play_button.setEnabled(idle and self._video_path is not None)
        self.fullscreen_checkbox.setEnabled(idle)
        self.volume_slider.setEnabled(not self._shutting_down)
        self.mute_checkbox.setEnabled(not self._shutting_down)

    @Slot()
    def choose_video(self) -> None:
        if self._playback is not None or self._shutting_down:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Elegir video local",
            str(self._video_path.parent) if self._video_path else "",
            VIDEO_FILTER,
        )
        if not filename:
            return
        try:
            path = validate_video_path(filename)
        except ValueError as exc:
            self.message.setText(str(exc))
            return
        self._video_path = path
        self.path_field.setText(path.name)
        self.path_field.setToolTip(str(path))
        self.message.setText("Video seleccionado. Puedes probarlo sin iniciar la cámara.")
        self._update_controls()

    @property
    def is_playing(self) -> bool:
        return self._playback is not None

    @property
    def has_video(self) -> bool:
        return self._video_path is not None and not self._shutting_down

    @Slot()
    def play_video(self) -> None:
        self._start(automatic=False)

    def start_automatic(self) -> bool:
        return self._start(automatic=True)

    def _start(self, *, automatic: bool) -> bool:
        if self._playback is not None or self._video_path is None or self._shutting_down:
            return False
        try:
            path = validate_video_path(self._video_path)
        except ValueError as exc:
            self.message.setText(str(exc))
            return False
        try:
            window = self._playback_factory(self.window())
        except RuntimeError as exc:
            self.message.setText(f"No se pudo preparar el reproductor: {exc}")
            return False
        self._playback = window
        self._automatic = automatic
        self._update_controls()
        self.message.setText(
            "Alerta automática en pantalla completa; se repite hasta recuperación o Esc."
            if automatic else "Abriendo video. Usa Esc o «Cerrar» para terminar la prueba."
        )
        window.finished.connect(self._playback_finished)
        try:
            options = dict(
                volume=self.volume_slider.value(),
                muted=self.mute_checkbox.isChecked(),
                fullscreen=automatic or self.fullscreen_checkbox.isChecked(),
            )
            if automatic:
                options["repeat"] = True
            window.start_video(path, **options)
        except (ValueError, RuntimeError) as exc:
            window.fail(str(exc))
        return self._playback is window

    def stop_automatic(self, message: str) -> None:
        if self._playback is not None and self._automatic:
            self._playback.finish(message)

    @Slot()
    def _audio_changed(self) -> None:
        volume = self.volume_slider.value()
        self.volume_label.setText(f"Volumen: {volume} %")
        if self._playback is not None:
            self._playback.set_audio(volume, self.mute_checkbox.isChecked())

    @Slot(str)
    def _playback_finished(self, message: str) -> None:
        if self._playback is None:
            return
        window = self._playback
        automatic, self._automatic = self._automatic, False
        self._playback = None
        window.deleteLater()
        self.message.setText(message)
        self._update_controls()
        self.playback_finished.emit(automatic, message)

    def shutdown(self) -> None:
        self._shutting_down = True
        self._update_controls()
        if self._playback is not None:
            self._playback.close()