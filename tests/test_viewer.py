import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from concurrent.futures import Future
import threading

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from kvmuse.viewer_core import InputState, RELEASE, SerialWorker, keyboard, windows_usage
from kvmuse.viewer_camera import CameraStream
from kvmuse.viewer_ui import Window


def test_input_click_drag_and_letterbox():
    state = InputState()
    assert state.pointer(10, 5, 200, 200, 2, pressed=1) == []
    assert not state.control  # Top letterbox.
    assert state.pointer(100, 100, 200, 200, 2, pressed=1) == []
    assert state.control and state.suppress_click
    assert state.pointer(100, 100, 200, 200, 2, released=1) == []
    assert not state.suppress_click
    report = state.pointer(100, 100, 200, 200, 2, pressed=1)[0]
    assert report == [4, 2, 1, 0, 8, 0, 8, 0]
    assert state.pointer(-50, -50, 200, 200, 2)[0][2] == 1
    assert state.pointer(-50, -50, 200, 200, 2, released=1)[0][2] == 0
    assert state.pointer(100, 100, 200, 200, 2, wheel=-1)[0][-1] == 255


def test_keys_modifiers_and_release():
    state = InputState()
    assert state.key(4, True) == []
    state.control = True
    assert state.key(225, True) == [keyboard(modifiers=2)]
    assert state.key(4, True) == [keyboard([4], 2)]
    assert state.key(4, False) == [keyboard([], 2)]
    state.key(228, True)
    assert state.modifiers == 18
    assert state.release() == RELEASE
    assert not state.control and not state.keys and state.modifiers == state.buttons == 0
    assert keyboard(range(4, 11))[3:] == [1] * 6
    assert state.f13(1) is False
    assert state.f13(1.3) is True
    assert state.f13(2) is False


def test_physical_key_mapping():
    assert windows_usage(0x10, 0) == 20  # Physical Q even with another layout.
    assert windows_usage(0x11d, 0) == 228  # Right Ctrl.
    assert windows_usage(0xe04b, 0) == 80
    assert windows_usage(0x45, 0x13) == 72
    assert windows_usage(0, 0x7c) == 104
    assert windows_usage(0xffff, 0) is None


class Device:
    def __init__(self, port=None):
        self.sent = []
        self.fail = False
        self.closed = False

    def open(self):
        return self

    def _send(self, cmd, payload):
        if self.fail:
            raise OSError('Device unplugged')
        self.sent.append([cmd, *payload])

    def close(self):
        self.closed = True


def test_serial_batches_ack_failure_and_shutdown():
    device = Device()
    worker = SerialWorker(device_factory=lambda _: device)
    try:
        worker.submit(reconnect=True).result(2)
        first = worker.submit([keyboard([4]), keyboard()])
        second = worker.submit([keyboard([5]), keyboard()])
        first.result(2)
        second.result(2)
        assert device.sent[:4] == [keyboard([4]), keyboard(), keyboard([5]), keyboard()]
        device.fail = True
        with pytest.raises(OSError, match='unplugged'):
            worker.submit([keyboard([6])]).result(2)
        assert not worker.connected and device.closed
    finally:
        worker.close()
    assert not worker.thread.is_alive()
    with pytest.raises(RuntimeError, match='closing'):
        worker.submit(RELEASE).result()


def test_serial_release_cancels_queued_batches():
    entered, unblock = threading.Event(), threading.Event()
    device = Device()
    original = device._send
    def send(cmd, payload):
        if payload[2:3] == b'\x04':
            entered.set()
            assert unblock.wait(2)
        original(cmd, payload)
    device._send = send
    worker = SerialWorker(device_factory=lambda _: device)
    try:
        worker.submit(reconnect=True).result(2)
        running = worker.submit([keyboard([4])])
        assert entered.wait(2)
        pending = worker.submit([keyboard([5])])
        release = worker.submit(RELEASE, priority=True)
        unblock.set()
        running.result(2)
        release.result(2)
        with pytest.raises(RuntimeError, match='cancelled'):
            pending.result()
        assert device.sent[-2:] == RELEASE
    finally:
        unblock.set()
        worker.close()


class FakeSerial:
    connected = True
    def __init__(self):
        self.sent = []
        self.closed = False
    def submit(self, reports=None, **kwargs):
        self.sent.append((reports, kwargs))
        future = Future()
        future.set_result('ok')
        return future
    def close(self):
        self.closed = True


class FakeCamera:
    def start(self):
        pass
    def close(self):
        self.closed = True
    def latest(self):
        return 1, (4, 2, bytes([100] * 24))


class FakeBridge:
    def __init__(self, *args):
        pass
    def start(self):
        pass
    def close(self):
        self.closed = True


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app):
    window = Window(no_connect=True, serial=FakeSerial(), camera=FakeCamera(), bridge_factory=FakeBridge)
    window.show()
    window.activateWindow()
    app.processEvents()
    yield window
    window.close()
    app.processEvents()


def key_event(window, event_type, key, scan, virtual=0, modifiers=Qt.KeyboardModifier.NoModifier):
    event = QKeyEvent(event_type, key, modifiers, scan, virtual, 0)
    return window.eventFilter(window.video, event)


def test_qt_control_shortcuts_focus_and_frame(window, app):
    assert not window.state.control
    window.toggle_control()
    assert window.state.control
    assert key_event(window, QEvent.Type.KeyPress, Qt.Key.Key_A, 0x1e, 0x41)
    assert window.serial.sent[-1][0] == [keyboard([4])]
    # F13 never reaches the target, and the double tap releases held input.
    key_event(window, QEvent.Type.KeyPress, Qt.Key.Key_F13, 0, 0x7c)
    key_event(window, QEvent.Type.KeyRelease, Qt.Key.Key_F13, 0, 0x7c)
    key_event(window, QEvent.Type.KeyPress, Qt.Key.Key_F13, 0, 0x7c)
    assert not window.state.control
    assert window.serial.sent[-1][0] == RELEASE
    modifiers = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
    key_event(window, QEvent.Type.KeyPress, Qt.Key.Key_K, 0x25, 0x4b, modifiers)
    assert window.state.control
    window.eventFilter(window, QEvent(QEvent.Type.WindowDeactivate))
    assert not window.state.control
    assert not window.state.keys
    window.update_frame()
    assert window.video.image.size().width() == 4
    window.close()
    assert window.serial.closed and window.camera.closed and window.bridge.closed


def test_camera_png_scaling_and_unavailable():
    camera = CameraStream()
    with pytest.raises(RuntimeError, match='No camera frame'):
        camera.png()
    camera.frame = (4, 2, bytes([255] * 24))
    from kvmuse.capture import image_resolution
    assert image_resolution(camera.png(2)) == (2, 1)


def test_qt_camera_error_and_black_hint_release_input(window, monkeypatch):
    window.state.control = True
    window.state.key(4, True)
    window.camera_status('Camera disconnected')
    assert not window.state.control and not window.state.keys
    assert window.serial.sent[-1][0] == RELEASE
    window.camera.latest = lambda: (2, (4, 2, bytes(24)))
    window.black_since = 1
    monkeypatch.setattr('kvmuse.viewer_ui.time.monotonic', lambda: 4)
    window.update_frame()
    assert not window.hint.isHidden()
    window.camera.latest = lambda: (3, (4, 2, bytes([255] * 24)))
    window.update_frame()
    assert window.hint.isHidden()
