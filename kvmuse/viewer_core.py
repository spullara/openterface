"""GUI-independent Windows Viewer input state and serial ownership."""
from collections import deque
from concurrent.futures import Future
import threading
import time

from .ch9329 import CH9329


def keyboard(keys=(), modifiers=0):
    keys = sorted(keys)
    if len(keys) > 6:
        keys = [1] * 6  # USB ErrorRollOver, not a stuck partial chord.
    return [2, modifiers, 0, *keys, *([0] * (6 - len(keys)))]


RELEASE = [keyboard(), [5, 1, 0, 0, 0, 0]]
WAKE = [keyboard(modifiers=2), keyboard(), [5, 1, 0, 1, 0, 0], [5, 1, 0, 255, 0, 0]]


class InputState:
    def __init__(self):
        self.control = False
        self.keys = set()
        self.modifiers = 0
        self.buttons = 0
        self.suppress_click = False
        self.last_f13 = None

    def release(self):
        self.control = False
        self.keys.clear()
        self.modifiers = self.buttons = 0
        self.suppress_click = False
        self.last_f13 = None
        return RELEASE

    def f13(self, now=None):
        now = time.monotonic() if now is None else now
        release = self.last_f13 is not None and 0 <= now - self.last_f13 <= .4
        self.last_f13 = now
        return release

    def key(self, usage, down):
        if not self.control or usage is None:
            return []
        if 224 <= usage <= 231:
            bit = 1 << (usage - 224)
            self.modifiers = (self.modifiers | bit) if down else (self.modifiers & ~bit)
        elif down:
            self.keys.add(usage)
        else:
            self.keys.discard(usage)
        return [keyboard(self.keys, self.modifiers)]

    def pointer(self, x, y, width, height, aspect, *, pressed=0, released=0, wheel=0):
        if width <= 0 or height <= 0:
            return []
        video_width = min(width, height * aspect)
        video_height = video_width / aspect
        left, top = (width - video_width) / 2, (height - video_height) / 2
        inside = left <= x <= left + video_width and top <= y <= top + video_height
        if not self.control:
            if inside and pressed == 1:
                self.control = self.suppress_click = True
            return []
        if self.suppress_click:
            if released == 1:
                self.suppress_click = False
            return []
        # Ignore letterbox presses, but always forward releases for held buttons.
        if not inside and not (self.buttons or released):
            return []
        self.buttons = (self.buttons | pressed) & ~released
        px = round(max(0, min(1, (x - left) / video_width)) * 4095)
        py = round(max(0, min(1, (y - top) / video_height)) * 4095)
        return [[4, 2, self.buttons, px & 255, px >> 8, py & 255, py >> 8,
                 max(-127, min(127, wheel)) & 255]]


# Windows Set-1 physical scan codes, independent of the host keyboard layout.
SCANS = {}
for row, usages in [(0x10, [20, 26, 8, 21, 23, 28, 24, 12, 18, 19]),
                    (0x1e, [4, 22, 7, 9, 10, 11, 13, 14, 15]),
                    (0x2c, [29, 27, 6, 25, 5, 17, 16])]:
    SCANS.update({row + i: usage for i, usage in enumerate(usages)})
SCANS.update({i + 2: 30 + i for i in range(10)})
SCANS.update({0x01: 41, 0x0c: 45, 0x0d: 46, 0x0e: 42, 0x0f: 43,
              0x1a: 47, 0x1b: 48, 0x1c: 40, 0x1d: 224, 0x27: 51,
              0x28: 52, 0x29: 53, 0x2a: 225, 0x2b: 49, 0x33: 54,
              0x34: 55, 0x35: 56, 0x36: 229, 0x37: 85, 0x38: 226,
              0x39: 44, 0x3a: 57, 0x45: 83, 0x46: 71, 0x47: 95,
              0x48: 96, 0x49: 97, 0x4a: 86, 0x4b: 92, 0x4c: 93,
              0x4d: 94, 0x4e: 87, 0x4f: 89, 0x50: 90, 0x51: 91,
              0x52: 98, 0x53: 99, 0x56: 100, 0x57: 68, 0x58: 69})
SCANS.update({0x3b + i: 58 + i for i in range(10)})
SCANS.update({0x100 + k: v for k, v in {
    0x1c: 88, 0x1d: 228, 0x35: 84, 0x37: 70, 0x38: 230, 0x47: 74,
    0x48: 82, 0x49: 75, 0x4b: 80, 0x4d: 79, 0x4f: 77, 0x50: 81,
    0x51: 78, 0x52: 73, 0x53: 76, 0x5b: 227, 0x5c: 231, 0x5d: 101}.items()})


def windows_usage(scan, virtual_key):
    # Qt 6 uses E000 for extended keys; normalize to the table's 0x100 prefix.
    if scan & 0xff00 == 0xe000:
        scan = 0x100 | (scan & 255)
    if virtual_key == 0x13:
        return 72  # Pause shares NumLock's scan on some keyboards.
    if virtual_key == 0x7c:
        return 104  # F13 is reserved by the Viewer.
    return SCANS.get(scan)


class SerialWorker:
    """A single owner; complete bridge batches cannot interleave with UI input."""
    def __init__(self, port=None, device_factory=None, status=lambda _: None):
        self.port, self.status = port, status
        self.factory = device_factory or (lambda port: CH9329(port, timeout=.3))
        self.pending = deque()
        self.condition = threading.Condition()
        self.stopping = False
        self.connected = False
        self.thread = threading.Thread(target=self._run, daemon=True, name='kvm-serial')
        self.thread.start()

    def submit(self, reports=None, *, reconnect=False, priority=False):
        future = Future()
        future.deadline = time.monotonic() + 24
        with self.condition:
            if self.stopping:
                future.set_exception(RuntimeError('Viewer is closing.'))
                return future
            if priority:
                while self.pending:
                    _, _, cancelled = self.pending.popleft()
                    cancelled.set_exception(RuntimeError('Input cancelled to release control.'))
            if len(self.pending) >= 256:
                future.set_exception(RuntimeError('Serial queue is full. Release control and reconnect.'))
                return future
            self.pending.append((reconnect, reports or [], future))
            self.condition.notify()
        return future

    def _run(self):
        device = None
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.pending or self.stopping)
                if not self.pending:
                    break
                reconnect, reports, future = self.pending.popleft()
            try:
                if reconnect:
                    if device:
                        device.close()
                    device = None
                    self.connected = False
                    device = self.factory(self.port).open()
                    self.connected = True
                    self.status('Serial connected')
                if device is None:
                    raise RuntimeError('Serial is not connected. Use Reconnect.')
                for report in reports:
                    if self.stopping:
                        raise RuntimeError('Viewer is closing; batch stopped.')
                    if time.monotonic() > future.deadline:
                        raise RuntimeError('Serial batch timed out; remaining input cancelled.')
                    device._send(report[0], bytes(report[1:]))
                future.set_result('ok')
            except Exception as exc:
                self.connected = False
                if device:
                    # A failed batch may have left input held. Best effort release.
                    for report in RELEASE:
                        try:
                            device._send(report[0], bytes(report[1:]))
                        except Exception:
                            break
                    try:
                        device.close()
                    except Exception:
                        pass
                    device = None
                with self.condition:
                    while self.pending:
                        _, _, pending = self.pending.popleft()
                        pending.set_exception(RuntimeError('Serial disconnected; batch cancelled.'))
                self.status(f'Serial error: {exc}')
                future.set_exception(exc)
        if device:
            for report in RELEASE:
                try:
                    device._send(report[0], bytes(report[1:]))
                except Exception:
                    break
            try:
                device.close()
            except Exception:
                pass
        self.connected = False

    def close(self):
        with self.condition:
            self.stopping = True
            while self.pending:
                _, _, future = self.pending.popleft()
                future.set_exception(RuntimeError('Viewer is closing.'))
            self.condition.notify()
        self.thread.join(timeout=6)
