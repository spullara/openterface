import pytest
from kvmuse.ch9329 import CH9329, build_packet
from kvmuse.hid_keys import text_keys

class Port:
    def __init__(self):
        self.packets = []
        self.response = b""
    def reset_input_buffer(self):
        pass
    def write(self, packet):
        self.packets.append(packet)
        self.response = build_packet(packet[3] | 128, b"\0")
        return len(packet)
    def read(self, n):
        result, self.response = self.response[:n], self.response[n:]
        return result

@pytest.fixture
def device():
    d = CH9329()
    d.serial = Port()
    return d

def test_known_frame():
    assert build_packet(1) == bytes.fromhex("57 ab 00 01 00 03")

def test_keyboard(device):
    device.key_press(["a"], 2)
    device.key_release_all()
    assert device.serial.packets == [
        build_packet(2, bytes([2, 0, 4, 0, 0, 0, 0, 0])),
        build_packet(2, bytes(8))]
    with pytest.raises(ValueError):
        device.key_press([4]*7)

def test_text(device):
    assert text_keys("aA!?\n") == [(4, 0), (4, 2), (30, 2), (56, 2), (40, 0)]
    with pytest.raises(ValueError):
        device.type_text("hello🙂")
    assert not device.serial.packets

def test_mouse(device):
    device.mouse_move_abs(0, 1)
    device.mouse_move_rel(-1, 127)
    device.mouse_scroll(-2)
    device.mouse_click("right")
    assert [p[5:-1] for p in device.serial.packets] == [
        bytes([2, 0, 0, 0, 255, 15, 0]),
        bytes([1, 0, 255, 127, 0]),
        bytes([1, 0, 0, 0, 254]),
        bytes([1, 2, 0, 0, 0]), bytes([1, 0, 0, 0, 0])]
    with pytest.raises(ValueError):
        device.mouse_move_abs(float("nan"), 0)
    with pytest.raises(ValueError):
        device.mouse_move_rel(128, 0)

def test_timeout(device):
    device.serial.read = lambda n: b""
    with pytest.raises(TimeoutError):
        device.key_release_all()

def test_bad_checksum(device):
    device.serial.read = lambda n: b"\x57\xab\x00\x82\x01" if n == 5 else b"\0\0"
    with pytest.raises(IOError, match="checksum"):
        device.key_release_all()


def test_mouse_demo_packet_sequence(device, monkeypatch):
    from kvmuse import smoke
    monkeypatch.setattr(smoke.time, 'sleep', lambda seconds: None)
    smoke.mouse_demo(device)
    assert device.serial.packets == [
        build_packet(5, bytes([1, 0, 40, 0, 0])),
        build_packet(5, bytes([1, 0, 0, 40, 0])),
        build_packet(5, bytes([1, 0, 216, 0, 0])),
        build_packet(5, bytes([1, 0, 0, 216, 0])),
    ]
