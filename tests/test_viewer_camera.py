import threading
import time

from kvmuse import viewer_camera as module
from kvmuse.capture import image_resolution


def test_stream_fallback_latest_frame_and_shutdown(monkeypatch):
    monkeypatch.setattr(module.capture, 'discover_device', lambda: 'Openterface')
    monkeypatch.setattr(module.capture, 'input_command', lambda device, size: ['ffmpeg', size])
    processes = []
    ready = threading.Event()
    statuses = []
    class Output:
        def __init__(self, process):
            self.process = process
            self.first = True
        def read(self, count):
            if len(processes) == 1:
                return b''
            if self.first:
                self.first = False
                return bytes([100]) * count
            assert self.process.killed.wait(4)
            return b''
        def close(self):
            pass
    class Process:
        def __init__(self, command, **kwargs):
            self.command = command
            self.killed = threading.Event()
            self.stdout = Output(self)
            processes.append(self)
        def poll(self):
            return 0 if self.killed.is_set() else None
        def kill(self):
            self.killed.set()
        def wait(self, **kwargs):
            return 0
    monkeypatch.setattr(module.subprocess, 'Popen', Process)
    def status(message):
        statuses.append(message)
        if message.startswith('Video connected'):
            ready.set()
    camera = module.CameraStream(status=status)
    try:
        camera.start()
        assert ready.wait(3)
        assert camera.latest()[0] == 1
        assert image_resolution(camera.png(640)) == (640, 360)
        assert [process.command[1] for process in processes] == ['1920x1080', '1280x720']
    finally:
        camera.close()
    assert not camera.thread.is_alive() and not camera.watchdog.is_alive()
    assert all(process.killed.is_set() for process in processes)
    assert camera.latest()[1] is None


def test_stall_watchdog_kills_camera():
    killed = threading.Event()
    class Process:
        def poll(self):
            return None
        def kill(self):
            killed.set()
    camera = module.CameraStream()
    camera.process = Process()
    camera.last_read = time.monotonic() - 11
    camera.watchdog.start()
    try:
        assert killed.wait(2)
    finally:
        camera.close()
    assert not camera.watchdog.is_alive()
