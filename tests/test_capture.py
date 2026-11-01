from pathlib import Path
from types import SimpleNamespace
import struct
import subprocess
import pytest
from kvmuse import capture as c


def test_listing():
    devices = c.parse_devices(Path('tests/fixtures/avfoundation.txt').read_text())
    assert devices == [(0, 'FaceTime HD Camera'), (1, 'Openterface')]
    assert c.select_device(devices) == 1


@pytest.mark.parametrize('name', ['MACROSILICON', 'USB Video'])
def test_fallback(name):
    assert c.select_device([(2, name)]) == 2


def test_missing_and_ambiguous():
    for devices in [[], [(0, 'FaceTime')], [(0, 'USB A'), (1, 'USB B')]]:
        with pytest.raises(c.CaptureError):
            c.select_device(devices)


@pytest.mark.parametrize('status', [b'0', b'1', b'2', b'', b'garbage'])
def test_permission_denied(monkeypatch, status):
    monkeypatch.setattr(c.sys, 'platform', 'darwin')
    monkeypatch.setattr(c.shutil, 'which', lambda _: '/usr/bin/swift')
    monkeypatch.setattr(c, '_run', lambda cmd: SimpleNamespace(returncode=0, stdout=status))
    with pytest.raises(c.CaptureError, match='System Settings'):
        c.capture_frame()


def test_timeout(monkeypatch):
    def run(cmd, **kwargs):
        assert kwargs['timeout'] == 15
        raise subprocess.TimeoutExpired(cmd, 15)
    monkeypatch.setattr(c.subprocess, 'run', run)
    with pytest.raises(c.CaptureError, match='timed out'):
        c._run(['ffmpeg'])


def test_capture(monkeypatch):
    png = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', 640, 360)
    monkeypatch.setattr(c, 'discover_device', lambda: 1)
    monkeypatch.setattr(c, '_ffmpeg', lambda: 'ffmpeg')
    def run(cmd):
        assert cmd[cmd.index('-pixel_format') + 1] == 'uyvy422'
        assert cmd[cmd.index('-video_size') + 1] == '1920x1080'
        assert cmd[cmd.index('-framerate') + 1] == '30'
        assert 'scale=min(iw\\,640):-1' in cmd
        return SimpleNamespace(returncode=0, stdout=png)
    monkeypatch.setattr(c, '_run', run)
    assert c.capture_frame(640) == png
    assert c.image_resolution(png) == (640, 360)


@pytest.mark.parametrize('width', [0, -1, True, 2.5])
def test_bad_width(width):
    with pytest.raises(ValueError):
        c.capture_frame(width)


def test_bad_image():
    with pytest.raises(c.CaptureError):
        c.image_resolution(b'garbage')
