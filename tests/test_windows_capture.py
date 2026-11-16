from pathlib import Path
from types import SimpleNamespace
import struct
import pytest
from kvmuse import capture as c


def test_windows_discovery(monkeypatch):
    monkeypatch.setattr(c.sys, 'platform', 'win32')
    monkeypatch.setattr(c, '_ffmpeg', lambda: 'ffmpeg')
    listing = Path('tests/fixtures/dshow.txt').read_bytes()
    def run(command):
        assert 'swift' not in command
        assert 'dshow' in command
        return SimpleNamespace(stderr=listing, returncode=1)
    monkeypatch.setattr(c, '_run', run)
    assert c.discover_device() == '@device_pnp_camera'


def test_dshow_duplicates_and_audio():
    listing = '\n'.join(['"USB Video" (video)', 'Alternative name "first"',
                         '"USB Video" (video)', 'Alternative name "second"',
                         '"Openterface" (audio)', 'Alternative name "audio"'])
    devices = c.parse_dshow_devices(listing)
    assert devices == [('first', 'USB Video'), ('second', 'USB Video')]
    with pytest.raises(c.CaptureError, match='Multiple'):
        c.select_device(devices)
    assert c.parse_dshow_devices('garbage\n"USB" (audio)') == []


def test_windows_capture_fallback(monkeypatch):
    monkeypatch.setattr(c.sys, 'platform', 'win32')
    monkeypatch.setattr(c, 'discover_device', lambda: 'Camera with spaces')
    monkeypatch.setattr(c, '_ffmpeg', lambda: 'ffmpeg')
    png = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', 1280, 720)
    calls = []
    def run(command):
        calls.append(command)
        assert 'video=Camera with spaces' in command
        assert '-pixel_format' not in command
        assert 'scale=min(iw\\,640):-1' in command
        return SimpleNamespace(returncode=1 if len(calls) == 1 else 0,
                               stdout=png, stderr=b'unsupported mode')
    monkeypatch.setattr(c, '_run', run)
    assert c.capture_frame(640) == png
    assert [cmd[cmd.index('-video_size') + 1] for cmd in calls] == ['1920x1080', '1280x720']


def test_windows_access_error(monkeypatch):
    monkeypatch.setattr(c.sys, 'platform', 'win32')
    monkeypatch.setattr(c, 'discover_device', lambda: 'Openterface')
    monkeypatch.setattr(c, '_ffmpeg', lambda: 'ffmpeg')
    monkeypatch.setattr(c, '_run', lambda _: SimpleNamespace(returncode=1, stderr=b'busy camera'))
    with pytest.raises(c.CaptureError, match='allow desktop apps.*busy camera'):
        c.capture_frame()


def test_unsupported_host(monkeypatch):
    monkeypatch.setattr(c.sys, 'platform', 'freebsd')
    with pytest.raises(c.CaptureError, match='macOS and Windows'):
        c.discover_device()


def test_missing_ffmpeg(monkeypatch):
    monkeypatch.setattr(c.sys, 'platform', 'win32')
    monkeypatch.setattr(c.shutil, 'which', lambda _: None)
    with pytest.raises(c.CaptureError, match='ffmpeg is missing'):
        c._ffmpeg()
