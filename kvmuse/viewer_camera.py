"""Continuous FFmpeg capture with one latest frame and a stall watchdog."""
from io import BytesIO
import subprocess
import tempfile
import threading
import time

from PIL import Image
from . import capture


class CameraStream:
    def __init__(self, status=lambda _: None):
        self.status = status
        self.lock = threading.Lock()
        self.frame = None
        self.sequence = 0
        self.process = None
        self.stopping = threading.Event()
        self.last_read = time.monotonic()
        self.thread = threading.Thread(target=self._run, daemon=True, name='kvm-camera')
        self.watchdog = threading.Thread(target=self._watch, daemon=True, name='kvm-camera-watch')

    def start(self):
        self.thread.start()
        self.watchdog.start()

    def latest(self):
        with self.lock:
            return self.sequence, self.frame

    def png(self, max_width=1280):
        _, frame = self.latest()
        if frame is None:
            raise capture.CaptureError('No camera frame is available. Reconnect the camera.')
        width, height, data = frame
        image = Image.frombytes('RGB', (width, height), data)
        if width > max_width:
            image = image.resize((max_width, max(1, round(height * max_width / width))))
        output = BytesIO()
        image.save(output, 'PNG')
        return output.getvalue()

    def _watch(self):
        while not self.stopping.wait(.25):
            process = self.process
            if process and process.poll() is None and time.monotonic() - self.last_read > 10:
                process.kill()

    def _run(self):
        try:
            device = capture.discover_device()
            detail = ''
            for width, height in ((1920, 1080), (1280, 720)):
                if self.stopping.is_set():
                    return
                command = capture.input_command(device, f'{width}x{height}')
                command += ['-an', '-pix_fmt', 'rgb24', '-f', 'rawvideo', 'pipe:1']
                self.last_read = time.monotonic()
                with tempfile.TemporaryFile() as errors:
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    self.process = process
                    connected = False
                    try:
                        while not self.stopping.is_set():
                            remaining = width * height * 3
                            chunks = []
                            while remaining:
                                chunk = process.stdout.read(remaining)
                                if not chunk:
                                    break
                                chunks.append(chunk)
                                remaining -= len(chunk)
                            if remaining:
                                break
                            self.last_read = time.monotonic()
                            with self.lock:
                                self.frame = (width, height, b''.join(chunks))
                                self.sequence += 1
                            if not connected:
                                connected = True
                                self.status(f'Video connected ({width}x{height}, 30 fps)')
                    finally:
                        if process.poll() is None:
                            process.kill()
                        process.wait(timeout=3)
                        process.stdout.close()
                        self.process = None
                    errors.seek(0, 2)
                    errors.seek(max(0, errors.tell() - 2000))
                    detail = errors.read().decode(errors='replace')
                if connected:
                    break  # A disconnected live camera requires explicit reconnect.
            if not self.stopping.is_set():
                raise capture.capture_error(detail or 'Camera stopped or timed out.')
        except Exception as exc:
            if not self.stopping.is_set():
                self.status(str(exc))
        finally:
            with self.lock:
                self.frame = None

    def close(self):
        self.stopping.set()
        process = self.process
        if process and process.poll() is None:
            process.kill()
        if self.thread.ident:
            self.thread.join(timeout=18)  # Includes bounded discovery if still running.
        if self.watchdog.ident:
            self.watchdog.join(timeout=1)
