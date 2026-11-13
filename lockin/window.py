"""Interfaz; solo este hilo modifica los widgets."""

from PySide6.QtCore import QRectF, QTimer, Qt, Slot
from PySide6.QtGui import QColor, QCloseEvent, QImage, QPainter, QPen, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QStackedWidget,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lockin.camera import CameraWorker
from lockin.widgets import ScrollSafeComboBox
from lockin.theme import apply_theme, set_tone
from lockin.session_view import SessionView, text_label
from lockin.face import AnalysisWorker
from lockin.face_panel import FacePanel
from lockin.calibration_view import CalibrationView
from lockin.eye_panel import EyePanel
from lockin.posture_panel import PosturePanel
from lockin.video import VideoPanel
from lockin.alert_panel import AlertPanel
from lockin.alerts_view import AlertsView
from lockin.navigation import Navigation, ui_icon
from lockin.devices import (
    CameraDevice, CameraDiscoveryWorker, camera_labels, list_cameras,
)


class Preview(QLabel):
    def __init__(self) -> None:
        super().__init__()
        self._original = QPixmap()
        self._face_boxes = ()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.setObjectName("cameraPreview")
        self.reset("La cámara está detenida.")

    def reset(self, message: str) -> None:
        self._face_boxes = ()
        self._original = QPixmap()
        self.clear()
        self.setText(message)

    def show_image(self, image: QImage) -> None:
        self._original = QPixmap.fromImage(image)
        self._redraw()

    @Slot(object)
    def set_face_boxes(self, boxes) -> None:
        boxes = tuple(boxes)
        if boxes != self._face_boxes:
            self._face_boxes = boxes
            self._redraw()

    def _redraw(self) -> None:
        if self._original.isNull():
            return
        displayed = self._original.scaled(
            self.contentsRect().size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if self._face_boxes and not displayed.isNull():
            # Dibuja sobre la copia escalada: QLabel centra imagen y recuadros
            # juntos, incluso cuando hay bandas laterales o la ventana cambia.
            painter = QPainter(displayed)
            color = "#32e676" if len(self._face_boxes) == 1 else "#f0b429"
            painter.setPen(QPen(QColor(color), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            width = displayed.width() / displayed.devicePixelRatio()
            height = displayed.height() / displayed.devicePixelRatio()
            for left, top, right, bottom in self._face_boxes:
                painter.drawRect(QRectF(
                    left * width, top * height,
                    (right - left) * width, (bottom - top) * height,
                ))
            painter.end()
        self.setPixmap(displayed)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._redraw()


class MainWindow(QMainWindow):
    def __init__(self, worker_factory=CameraWorker, device_provider=list_cameras,
                 analysis_factory=AnalysisWorker) -> None:
        super().__init__()
        self._worker_factory = worker_factory
        self._device_provider = device_provider
        self._worker: CameraWorker | None = None
        self._discovery: CameraDiscoveryWorker | None = None
        self._previous_device: CameraDevice | None = None
        self._active_device: CameraDevice | None = None
        self._stopping = False
        self._closing = False
        self._ui_disposed = False
        self._has_error = False

        self.setWindowTitle("LockIn")
        self.resize(1180, 800)
        apply_theme(self)
        self.setMinimumSize(640, 600)

        self.camera_selector = ScrollSafeComboBox()
        self.camera_selector.setAccessibleName("Cámara")
        self.camera_selector.setPlaceholderText("Selecciona una cámara")
        self.camera_selector.setMinimumContentsLength(5)
        self.camera_selector.setSizeAdjustPolicy(
            ScrollSafeComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.refresh_button = QPushButton("Actualizar")
        self.refresh_button.setToolTip("Actualizar cámaras disponibles; requiere detener la captura.")
        self.start_button = QPushButton("Iniciar cámara")
        self.stop_button = QPushButton("Detener cámara")
        self.stop_button.setEnabled(False)

        self.face_panel = FacePanel(self, worker_factory=analysis_factory)
        self.eye_panel = EyePanel(self)
        self.face_panel.analysis_started.connect(self.eye_panel.bind_worker)
        self.face_panel.analysis_updated.connect(self.eye_panel.update_snapshot)
        self.face_panel.analysis_stopped.connect(self.eye_panel.reset)
        self.posture_panel = PosturePanel(self)
        self.face_panel.analysis_started.connect(self.posture_panel.bind_worker)
        self.face_panel.analysis_updated.connect(self.posture_panel.update_snapshot)
        self.face_panel.analysis_stopped.connect(self.posture_panel.reset)
        self.face_panel.calibration_requested.connect(self.posture_panel.calibration_requested)
        self.video_panel = VideoPanel(self)
        self.alert_panel = AlertPanel(
            self.video_panel, self,
            eye_duration=self.eye_panel.hold_seconds.value,
            posture_settings=self.posture_panel.settings,
        )
        self.face_panel.analysis_started.connect(self.alert_panel.source_started)
        self.face_panel.analysis_updated.connect(self.alert_panel.update_snapshot)
        self.face_panel.analysis_stopped.connect(self.alert_panel.source_stopped)
        self.face_panel.calibration_requested.connect(self.alert_panel.posture_calibration_requested)
        self.eye_panel.calibration_requested.connect(self.alert_panel.eye_calibration_requested)
        for spin in (
            self.eye_panel.hold_seconds, self.posture_panel.angle_limit,
            self.posture_panel.head_seconds, self.posture_panel.absence_seconds,
        ):
            spin.valueChanged.connect(self.alert_panel.invalidate_measurements)
        self.preview = Preview()
        self.face_panel.face_boxes_changed.connect(self.preview.set_face_boxes)
        self.status = QLabel("Estado: detenida")
        self.status.setProperty("role", "footer")
        self.status.setWordWrap(True)
        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.TextFormat.PlainText)
        privacy = QLabel("Procesamiento local · Sin grabación")
        privacy.setWordWrap(True)
        privacy.setToolTip("La cámara se procesa en tu equipo. No se guardan ni envían imágenes ni se captura audio del micrófono.")

        self.session = SessionView(
            self.camera_selector, self.start_button, self.stop_button, self.refresh_button,
            self.status, self.detail, self.eye_panel, self.posture_panel, self.alert_panel,
        )
        self.session.preview_host.layout().addWidget(self.preview)
        self.session.video_host.layout().addWidget(self.video_panel)

        self.nav = Navigation()
        brand = QWidget()
        brand.setObjectName("brandGroup")
        brand.setAccessibleName("LockIn")
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(5)
        mark = QLabel()
        mark.setPixmap(ui_icon("lockin-mark").pixmap(38, 34))
        brand_layout.addWidget(mark)
        wordmark = QLabel("LockIn")
        wordmark.setObjectName("brand")
        brand_layout.addWidget(wordmark)
        self.setWindowIcon(ui_icon("lockin-mark"))
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(176)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(8, 22, 8, 16)
        sidebar_layout.setSpacing(22)
        sidebar_layout.addWidget(brand, 0, Qt.AlignmentFlag.AlignHCenter)
        sidebar_layout.addWidget(self.nav, 1)
        privacy.setProperty("role", "muted")
        privacy.setObjectName("privacy")
        shield = QLabel()
        shield.setPixmap(ui_icon("shield").pixmap(20, 20))
        local = QHBoxLayout()
        local.addWidget(shield)
        local.addWidget(privacy, 1)
        sidebar_layout.addLayout(local)
        self.pages = QStackedWidget()
        self.session_scroll = self._scroll_page(self.session)
        self.pages.addWidget(self.session_scroll)

        self.calibration_view = CalibrationView(
            self.face_panel, self.eye_panel, self.posture_panel, self.alert_panel
        )
        self.calibration_preview_host = self.calibration_view.preview_host
        self.calibration_scroll = self._scroll_page(self.calibration_view)
        self.pages.addWidget(self.calibration_scroll)

        self.alerts_view = AlertsView(self.alert_panel, self.posture_panel, self.eye_panel)
        self.alerts_video_host = self.alerts_view.video_host
        self.alerts_scroll = self._scroll_page(self.alerts_view)
        self.pages.addWidget(self.alerts_scroll)

        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(18, 8, 18, 8)
        self.processing_status = text_label("Análisis: detenido", "footer")
        footer_layout.addWidget(self.processing_status, 1)
        footer_layout.addWidget(self.status)
        self.detail.setProperty("role", "footer")
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.pages, 1)
        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(18, 2, 18, 2)
        detail_layout.addWidget(self.detail)
        root.addWidget(detail_container)
        root.addWidget(footer)
        content = QWidget()
        content.setLayout(root)
        central = QWidget()
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(sidebar)
        shell.addWidget(content, 1)
        self.setCentralWidget(central)
        self.nav.currentChanged.connect(self._page_changed)
        self.face_panel.analysis_updated.connect(self.session.update_snapshot)
        self.face_panel.analysis_stopped.connect(self.session.reset_signals)
        self.alert_panel.presentation_changed.connect(self._refresh_presentation)

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(33)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._shutdown_notice = QTimer(self)
        self._shutdown_notice.setSingleShot(True)
        self._shutdown_notice.setInterval(5000)
        self._shutdown_notice.timeout.connect(self._slow_shutdown)

        self.camera_selector.currentIndexChanged.connect(self._selection_changed)
        self.refresh_button.clicked.connect(self.refresh_cameras)
        self.start_button.clicked.connect(self.start_camera)
        self.stop_button.clicked.connect(self.stop_camera)
        # Solo consulta metadatos; la captura no se crea hasta pulsar Iniciar.
        self.refresh_cameras()

    @staticmethod
    def _scroll_page(content):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll

    @Slot(int)
    def _page_changed(self, index):
        if self._ui_disposed:
            return
        self.pages.setCurrentIndex(index)
        preview_host = self.calibration_preview_host if index == 1 else self.session.preview_host
        if self.preview.parentWidget() is not preview_host:
            preview_host.layout().addWidget(self.preview)
        if index in (0, 2):
            video_host = self.session.video_host if index == 0 else self.alerts_video_host
            if self.video_panel.parentWidget() is not video_host:
                video_host.layout().addWidget(self.video_panel)
        self._refresh_presentation()

    @Slot()
    def _refresh_presentation(self):
        if self._ui_disposed:
            return
        self.session.refresh()
        snapshot = self.face_panel._last
        processing = (
            "detenido" if self.face_panel._worker is None or self._stopping
            else "error" if snapshot is not None and snapshot.phase == "error"
            else "activo" if snapshot is not None and snapshot.phase == "ready"
            else "iniciando"
        )
        self.processing_status.setText("Análisis: " + processing)
        set_tone(self.status, "danger" if self._has_error else "good" if self.status.text() == "Estado: activa" else "neutral")

    def _update_controls(self) -> None:
        idle = self._worker is None and self._discovery is None and not self._closing
        selected = isinstance(self.camera_selector.currentData(), CameraDevice)
        self.camera_selector.setEnabled(idle and self.camera_selector.count() > 0
                                        and self.camera_selector.itemData(0) is not None)
        self.refresh_button.setEnabled(idle)
        self.start_button.setEnabled(idle and selected)
        self._refresh_presentation()

    @Slot(int)
    def _selection_changed(self, _index: int) -> None:
        self.camera_selector.setToolTip(self.camera_selector.currentText())
        self._update_controls()

    @Slot()
    def refresh_cameras(self) -> None:
        if self._worker is not None or self._discovery is not None or self._closing:
            return
        self._previous_device = self.camera_selector.currentData()
        self.detail.setText("Buscando cámaras disponibles…")
        scan = CameraDiscoveryWorker(self._device_provider)
        self._discovery = scan
        scan.finished.connect(self._discovery_finished)
        self._update_controls()
        scan.start()

    @Slot()
    def _discovery_finished(self) -> None:
        scan = self._discovery
        if scan is None:
            return
        if not scan.wait(0):
            QTimer.singleShot(10, self._discovery_finished)
            return
        self._discovery = None
        scan.deleteLater()
        self._shutdown_notice.stop()
        if self._closing:
            self._close_if_idle()
            return

        self.camera_selector.blockSignals(True)
        try:
            self.camera_selector.clear()
            self._has_error = scan.error is not None
            if scan.error:
                self.camera_selector.addItem("No se pudo consultar la lista")
                self.camera_selector.setCurrentIndex(0)
                self.status.setText("Estado: error")
                self.detail.setText(scan.error)
            elif not scan.devices:
                self.camera_selector.addItem("No se encontraron cámaras")
                self.camera_selector.setCurrentIndex(0)
                self.status.setText("Estado: detenida")
                self.detail.setText(
                    "Conecta una cámara y pulsa «Actualizar cámaras». "
                    "No se ha iniciado ninguna captura."
                )
            else:
                for label, device in zip(camera_labels(scan.devices), scan.devices):
                    self.camera_selector.addItem(label, device)
                selected_index = 0
                if self._previous_device is not None:
                    selected_index = next(
                        (i for i, device in enumerate(scan.devices)
                         if device.identity == self._previous_device.identity), -1
                    )
                self.camera_selector.setCurrentIndex(selected_index)
                self.status.setText("Estado: detenida")
                if selected_index == -1:
                    self.detail.setText(
                        "La cámara anterior ya no está en la lista. Selecciona otra cámara."
                    )
                else:
                    self.detail.setText(
                        "Elige una cámara y pulsa «Iniciar cámara» para ver la imagen."
                    )
        finally:
            self.camera_selector.blockSignals(False)
        self._selection_changed(self.camera_selector.currentIndex())

    @Slot()
    def start_camera(self) -> None:
        if self._worker is not None or self._discovery is not None or self._closing:
            return
        selected = self.camera_selector.currentData()
        if not isinstance(selected, CameraDevice):
            return
        self._active_device = selected
        self._stopping = False
        self._has_error = False
        self.stop_button.setEnabled(True)
        self.status.setText("Estado: iniciando")
        self.detail.setText(f"Abriendo «{selected.name}»; puedes detenerla mientras inicia.")
        self.preview.reset("Iniciando cámara…")

        worker = self._worker_factory(selected)
        self._worker = worker
        self._update_controls()
        worker.active.connect(self._camera_active)
        worker.failed.connect(self._camera_failed)
        worker.finished.connect(self._camera_finished)
        self._preview_timer.start()
        worker.start()

    @Slot()
    def stop_camera(self) -> None:
        if self._worker is None or self._stopping:
            return
        self._stopping = True
        self.alert_panel.cancel_for_stop()
        self.stop_button.setEnabled(False)
        self._preview_timer.stop()
        self.preview.reset("Deteniendo cámara…")
        self.detail.setText("Deteniendo la captura y liberando la cámara…")
        self.face_panel.request_stop()
        self._worker.request_stop()
        self._shutdown_notice.start()
        self._refresh_presentation()

    @Slot()
    def _camera_active(self) -> None:
        if self._stopping or self._closing or self._has_error:
            return
        self.face_panel.start(self._worker)
        self.status.setText("Estado: activa")
        self.detail.setText(f"«{self._active_device.name}» en funcionamiento.")
        self._refresh_presentation()

    @Slot(str)
    def _camera_failed(self, message: str) -> None:
        if self._stopping or self._closing:
            return
        self._has_error = True
        self.face_panel.request_stop()
        self.status.setText("Estado: error")
        self.detail.setText(message)
        self._preview_timer.stop()
        self.stop_button.setEnabled(False)
        self.preview.reset("No hay imagen disponible.")
        self._refresh_presentation()

    @Slot()
    def _refresh_preview(self) -> None:
        if self._worker is not None and not self._stopping and not self._has_error:
            image = self._worker.take_latest_frame()
            if image is not None:
                self.preview.show_image(image)

    @Slot()
    def _camera_finished(self) -> None:
        if self._worker is None:
            return
        self.face_panel.request_stop()
        if not self._worker.wait(0) or not self.face_panel.finish_stop():
            QTimer.singleShot(10, self._camera_finished)
            return
        self._preview_timer.stop()
        self._shutdown_notice.stop()
        self._worker.deleteLater()
        self._worker = None
        self.stop_button.setEnabled(False)
        self._update_controls()
        if not self._has_error or self._stopping:
            self.status.setText("Estado: detenida")
            self.detail.setText("Cámara liberada. Puedes volver a iniciarla.")
            self.preview.reset("La cámara está detenida.")
        self._refresh_presentation()
        self._close_if_idle()

    def _close_if_idle(self) -> None:
        if self._closing and self._worker is None and self._discovery is None:
            QTimer.singleShot(0, self.close)

    @Slot()
    def _slow_shutdown(self) -> None:
        if self._worker is not None or self._discovery is not None:
            self.detail.setText(
                "El controlador tarda en responder. Se espera su devolución "
                "para terminar de forma segura; la ventana sigue respondiendo."
            )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._ui_disposed:
            event.accept()
            return
        self.alerts_view.shutdown()
        self.calibration_view.shutdown()
        self.session.shutdown()
        self.alert_panel.shutdown()
        self.video_panel.shutdown()
        if self._worker is None and self._discovery is None:
            self._ui_disposed = True
            # Qt destruye la presentación en su hilo, después de terminar trabajadores.
            # Evita dejar la jerarquía compleja de widgets a la recolección de Python.
            self.centralWidget().deleteLater()
            event.accept()
            return
        self._closing = True
        self._update_controls()
        if self._worker is not None:
            self.stop_camera()
        else:
            self.detail.setText("Esperando a que termine la consulta de cámaras…")
            self._shutdown_notice.start()
        event.ignore()
