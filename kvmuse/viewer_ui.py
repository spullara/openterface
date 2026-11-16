"""Qt window for the Viewer; worker threads never touch widgets."""
import time

from PySide6.QtCore import QEvent, QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout, QLabel,
                              QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from .viewer_bridge import ViewerBridge
from .viewer_camera import CameraStream
from .viewer_core import InputState, SerialWorker, WAKE, native_usage


class Events(QObject):
    serial = Signal(str)
    camera = Signal(str)
    activity = Signal(bool)
    failure = Signal(str)


class Video(QWidget):
    def __init__(self, window):
        super().__init__()
        self.owner = window
        self.image = QImage()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(480, 270)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#101318'))
        if not self.image.isNull():
            width = min(self.width(), self.height() * self.image.width() / self.image.height())
            height = width * self.image.height() / self.image.width()
            painter.drawImage(QRectF((self.width() - width) / 2, (self.height() - height) / 2,
                                     width, height), self.image)
        else:
            painter.setPen(QColor('#ced4df'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Waiting for HDMI video')

    def pointer(self, event, pressed=0, released=0, wheel=0):
        if not self.owner.isActiveWindow():
            return
        self.setFocus()
        state = self.owner.state
        if not self.owner.serial.connected and not state.control:
            return
        position = event.position()
        aspect = self.image.width() / self.image.height() if not self.image.isNull() else 16 / 9
        before = state.control
        reports = state.pointer(position.x(), position.y(), self.width(), self.height(), aspect,
                                pressed=pressed, released=released, wheel=wheel)
        self.owner.send(reports)
        if before != state.control:
            self.owner.refresh()

    @staticmethod
    def button(event):
        return {Qt.MouseButton.LeftButton: 1, Qt.MouseButton.RightButton: 2,
                Qt.MouseButton.MiddleButton: 4}.get(event.button(), 0)

    def mousePressEvent(self, event):
        self.pointer(event, pressed=self.button(event))

    def mouseReleaseEvent(self, event):
        self.pointer(event, released=self.button(event))

    def mouseMoveEvent(self, event):
        self.pointer(event)

    def wheelEvent(self, event):
        self.pointer(event, wheel=round(event.angleDelta().y() / 120))


class Window(QMainWindow):
    def __init__(self, port=None, no_connect=False, *, serial=None, camera=None,
                 bridge_factory=ViewerBridge):
        super().__init__()
        self.setWindowTitle('KVM Viewer')
        self.resize(1000, 650)
        self.state = InputState()
        self.events = Events()
        self.closing = False
        self.serial_text = 'Serial disconnected'
        self.camera_text = 'Video starting'
        self.agent = False
        self.last_sequence = 0
        self.black_since = None
        self.serial = serial or SerialWorker(port, status=self.events.serial.emit)
        self.camera = camera or CameraStream(status=self.events.camera.emit)
        self.bridge = None
        self.video = Video(self)
        self.badge = QLabel()
        self.badge.setWordWrap(True)
        self.toggle = QPushButton('Take control')
        self.wake = QPushButton('Wake target')
        self.reconnect_button = QPushButton('Reconnect')
        self.top = QCheckBox('Always on top')
        self.hint = QLabel('Display may be asleep. Use Wake target; black video can also mean no HDMI signal.')
        self.hint.setWordWrap(True)
        self.hint.hide()
        shortcuts = QLabel('Release: Ctrl+Alt+K or F13 twice. Leaving the window releases input.')
        shortcuts.setWordWrap(True)
        buttons = QHBoxLayout()
        for widget in (self.toggle, self.wake, self.reconnect_button, self.top):
            buttons.addWidget(widget)
        layout = QVBoxLayout()
        layout.addWidget(self.video, 1)
        layout.addWidget(self.hint)
        layout.addWidget(self.badge)
        layout.addLayout(buttons)
        layout.addWidget(shortcuts)
        content = QWidget()
        content.setLayout(layout)
        self.setCentralWidget(content)
        self.toggle.clicked.connect(self.toggle_control)
        self.wake.clicked.connect(self.wake_target)
        self.reconnect_button.clicked.connect(self.reconnect)
        self.top.toggled.connect(self.floating)
        self.events.serial.connect(self.serial_status)
        self.events.camera.connect(self.camera_status)
        self.events.failure.connect(self.input_failure)
        self.events.activity.connect(self.agent_activity)
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.update_frame)
        QApplication.instance().installEventFilter(self)
        try:
            self.bridge = bridge_factory(self.serial, self.camera, self.events.activity.emit)
            self.bridge.start()  # Claim ownership before opening either device.
            self.camera.start()
            self.timer.start()
            if not no_connect:
                self.reconnect_serial()
        except Exception:
            self.cleanup()
            raise
        self.refresh()

    def send(self, reports, priority=False):
        if not reports or self.closing:
            return
        future = self.serial.submit(reports, priority=priority)
        def complete(result):
            error = result.exception()
            if error and not self.closing and not str(error).startswith('Input cancelled to release control.'):
                self.events.failure.emit(str(error))
        future.add_done_callback(complete)

    def release(self):
        reports = self.state.release()
        if self.serial.connected:
            self.send(reports, priority=True)
        self.refresh()

    def toggle_control(self):
        if self.state.control:
            self.release()
        elif self.serial.connected:
            self.state.control = True
            self.state.last_f13 = None
            self.video.setFocus()
            self.refresh()

    def wake_target(self):
        self.release()
        self.send(WAKE)

    def reconnect_serial(self):
        future = self.serial.submit(reconnect=True)
        future.add_done_callback(lambda result: self.events.failure.emit(str(result.exception()))
                                 if result.exception() and not self.closing else None)

    def reconnect(self):
        if getattr(self, 'restart_thread', None) and self.restart_thread.is_alive():
            return
        self.release()
        self.reconnect_button.setEnabled(False)
        # Discovery and camera teardown can take seconds; keep the window responsive.
        import threading
        def restart():
            self.camera.close()
            if self.closing:
                return
            self.camera = CameraStream(status=self.events.camera.emit)
            self.bridge.camera = self.camera
            self.last_sequence = 0
            self.camera.start()
            self.events.camera.emit('Video starting')
        self.restart_thread = threading.Thread(target=restart, daemon=True)
        self.restart_thread.start()
        self.reconnect_serial()

    def serial_status(self, message):
        self.serial_text = message
        if not self.serial.connected:
            self.state.release()
        self.reconnect_button.setEnabled(True)
        self.refresh()

    def camera_status(self, message):
        self.camera_text = message
        if not message.startswith('Video connected') and message != 'Video starting':
            self.release()
        self.reconnect_button.setEnabled(True)
        self.refresh()

    def input_failure(self, message):
        self.serial_text = message
        self.release()

    def agent_activity(self, active):
        self.agent = active
        self.refresh()

    def refresh(self):
        mode = 'Control ON' if self.state.control else 'Control OFF — click video or Take control'
        self.badge.setText(('Agent typing · ' if self.agent else '') + mode + '\n' +
                           self.camera_text + ' · ' + self.serial_text)
        self.toggle.setText('Release control' if self.state.control else 'Take control')
        self.toggle.setEnabled(self.serial.connected)
        self.wake.setEnabled(self.serial.connected)

    def floating(self, checked):
        self.release()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        self.show()

    def update_frame(self):
        sequence, frame = self.camera.latest()
        if frame is None:
            if not self.video.image.isNull():
                self.video.image = QImage()
                self.video.update()
            self.black_since = None
            self.hint.hide()
            return
        if sequence == self.last_sequence:
            return
        self.last_sequence = sequence
        width, height, data = frame
        self.video.image = QImage(data, width, height, width * 3, QImage.Format.Format_RGB888).copy()
        self.video.update()
        # Sample without encoding a PNG on the UI thread.
        samples = [max(data[i:i + 3]) for y in range(0, height, max(1, height // 36))
                   for x in range(0, width, max(1, width // 64)) for i in [(y * width + x) * 3]]
        black = bool(samples) and sum(value <= 24 for value in samples) / len(samples) >= .99
        self.black_since = (self.black_since or time.monotonic()) if black else None
        self.hint.setVisible(self.black_since is not None and time.monotonic() - self.black_since >= 2)

    def eventFilter(self, watched, event):
        if self.closing:
            return False
        if event.type() == QEvent.Type.ApplicationDeactivate or (
                watched is self and event.type() in (QEvent.Type.WindowDeactivate, QEvent.Type.Hide)):
            if self.state.control:
                self.release()
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease) or not self.isActiveWindow():
            return False
        if isinstance(watched, QWidget) and watched.window() is not self:
            return False
        down = event.type() == QEvent.Type.KeyPress
        toggle = event.key() == Qt.Key.Key_K and (
            event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        ) == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        if toggle:
            if down and not event.isAutoRepeat():
                self.toggle_control()
            return True
        if not self.state.control:
            return False
        usage = native_usage(event.nativeScanCode(), event.nativeVirtualKey(),
                             QApplication.platformName())
        if event.key() == Qt.Key.Key_F13 or usage == 104:
            if down and not event.isAutoRepeat() and self.state.f13():
                self.release()
            return True
        if event.isAutoRepeat():
            return True
        if down:
            self.state.last_f13 = None
        self.send(self.state.key(usage, down))
        return True

    def cleanup(self):
        if self.closing:
            return
        self.closing = True
        self.state.release()
        self.timer.stop()
        QApplication.instance().removeEventFilter(self)
        if self.bridge:
            self.bridge.close()
        # Stop serial first: held input is released before waiting for video discovery.
        self.serial.close()
        self.camera.close()
        restart = getattr(self, 'restart_thread', None)
        if restart:
            restart.join(timeout=18)
            self.camera.close()

    def closeEvent(self, event):
        self.cleanup()
        event.accept()


def run(port=None, no_connect=False):
    app = QApplication.instance() or QApplication([])
    try:
        window = Window(port, no_connect)
    except Exception as exc:
        QMessageBox.critical(None, 'KVM Viewer could not start', str(exc))
        return 1
    window.show()
    app.aboutToQuit.connect(window.cleanup)
    return app.exec()
