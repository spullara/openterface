"""CH9329 reports, verified against Openterface SerialProtocolCommands.swift."""
import math
import threading
import serial
from serial.tools import list_ports
from .hid_keys import KEYS, text_keys

def build_packet(command, payload=b""):
    body = bytes((0x57, 0xAB, 0, command, len(payload))) + bytes(payload)
    return body + bytes((sum(body) & 255,))

def list_devices():
    return [p.device for p in list_ports.comports()
            if p.vid == 0x1A86 and p.pid == 0xFE0C]

class CH9329:
    def __init__(self, port=None, *, timeout=1):
        self.port, self.timeout = port, timeout
        self.serial = None
        self._lock = threading.RLock()

    def open(self):
        if self.serial is None:
            devices = [self.port] if self.port else list_devices()
            if len(devices) != 1:
                raise RuntimeError("Connect one Openterface device or specify --port.")
            self.serial = serial.Serial(devices[0], 115200, timeout=self.timeout,
                                        write_timeout=self.timeout)
        return self

    def close(self):
        if self.serial is not None:
            try:
                self.key_release_all()
            finally:
                self.serial.close()
                self.serial = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *args):
        self.close()

    def _read(self, count):
        data = bytearray()
        while len(data) < count:
            chunk = self.serial.read(count-len(data))
            if not chunk:
                raise TimeoutError("CH9329 response timed out.")
            data.extend(chunk)
        return bytes(data)

    def _send(self, command, payload):
        with self._lock:
            if self.serial is None:
                raise RuntimeError("Serial device is not open.")
            self.serial.reset_input_buffer()
            packet = build_packet(command, payload)
            if self.serial.write(packet) != len(packet):
                raise IOError("Incomplete serial write.")
            header = self._read(5)
            if header[:3] != b"\x57\xab\x00" or header[3] != command | 0x80:
                raise IOError("Invalid CH9329 response header.")
            tail = self._read(header[4]+1)
            if sum(header + tail[:-1]) & 255 != tail[-1]:
                raise IOError("Invalid CH9329 response checksum.")
            if tail[:-1] != b"\x00":
                raise IOError(f"CH9329 rejected command: {tail[:-1].hex()}")

    def key_press(self, keys, modifiers=0):
        keys = [KEYS[k.lower()] if isinstance(k, str) else k for k in keys]
        if len(keys) > 6:
            raise ValueError("At most six keys can be held.")
        self._send(2, bytes([modifiers, 0] + keys + [0]*(6-len(keys))))

    def key_release_all(self):
        self.key_press([])

    def type_text(self, text):
        reports = text_keys(text)
        with self._lock:
            try:
                for key, modifier in reports:
                    self.key_press([key], modifier)
                    self.key_release_all()
            finally:
                self.key_release_all()

    def mouse_move_abs(self, x_frac, y_frac):
        if not all(math.isfinite(v) and 0 <= v <= 1 for v in (x_frac, y_frac)):
            raise ValueError("Mouse coordinates must be between 0 and 1.")
        x, y = (round(v*4095) for v in (x_frac, y_frac))
        self._send(4, bytes([2, 0, x & 255, x >> 8, y & 255, y >> 8, 0]))

    def _relative(self, dx=0, dy=0, wheel=0, buttons=0):
        if not all(isinstance(v, int) and -127 <= v <= 127 for v in (dx, dy, wheel)):
            raise ValueError("Relative movement and scroll must be integers from -127 to 127.")
        self._send(5, bytes([1, buttons, dx & 255, dy & 255, wheel & 255]))

    def mouse_move_rel(self, dx, dy):
        self._relative(dx, dy)

    def mouse_scroll(self, delta):
        self._relative(wheel=delta)

    def mouse_click(self, button="left"):
        buttons = {"left": 1, "right": 2, "middle": 4}
        mask = buttons[button]
        with self._lock:
            try:
                self._relative(buttons=mask)
            finally:
                self._relative()
