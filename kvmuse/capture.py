"""Bounded, single-frame AVFoundation capture on macOS."""
import re
import shutil
import struct
import subprocess
import sys


class CaptureError(RuntimeError):
    """Capture could not produce an image."""


def _run(command, timeout=15):
    try:
        return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise CaptureError('Camera operation timed out. Check Camera access and the HDMI connection.') from exc
    except OSError as exc:
        raise CaptureError(f'Cannot run {command[0]}: {exc}') from exc


def check_permission():
    if sys.platform != 'darwin':
        raise CaptureError('AVFoundation capture requires macOS.')
    swift = shutil.which('swift')
    if not swift:
        raise CaptureError('Install Apple command line tools to check Camera permission (swift is missing).')
    result = _run([swift, '-e', 'import AVFoundation; print(AVCaptureDevice.authorizationStatus(for: .video).rawValue)'])
    if result.returncode or result.stdout.strip() != b'3':
        raise CaptureError('Camera access is not authorized or could not be checked. Grant Camera access to the host app in System Settings > Privacy & Security > Camera, then restart it.')


def parse_devices(output):
    """Return video devices only; ffmpeg writes this listing to stderr."""
    devices = []
    video = False
    for line in output.splitlines():
        if 'AVFoundation video devices:' in line:
            video = True
        elif 'AVFoundation audio devices:' in line:
            video = False
        elif video:
            match = re.search(r'\[(\d+)\]\s+(.+?)\s*$', line)
            if match:
                devices.append((int(match[1]), match[2]))
    return devices


def select_device(devices):
    for name in ('openterface', 'macrosilicon', 'usb'):
        matches = [index for index, label in devices if name in label.lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise CaptureError('Multiple matching capture cameras found. Disconnect unused capture cameras.')
    raise CaptureError('No Openterface/MACROSILICON USB capture camera found.')


def _ffmpeg():
    executable = shutil.which('ffmpeg')
    if executable:
        return executable
    from pathlib import Path
    fallback = Path('/opt/homebrew/bin/ffmpeg')
    if fallback.is_file():
        return str(fallback)
    raise CaptureError('ffmpeg is missing. Install ffmpeg before capturing.')


def discover_device():
    check_permission()
    result = _run([_ffmpeg(), '-hide_banner', '-f', 'avfoundation', '-list_devices', 'true', '-i', ''])
    return select_device(parse_devices(result.stderr.decode(errors='replace')))


def image_resolution(png):
    """Read the captured PNG dimensions without an imaging dependency."""
    if len(png) < 24 or png[:8] != b'\x89PNG\r\n\x1a\n' or png[12:16] != b'IHDR':
        raise CaptureError('ffmpeg did not return a PNG image.')
    return struct.unpack('>II', png[16:24])


def capture_frame(max_width=None):
    """Return PNG bytes at 1920x1080, optionally scaled down to max_width."""
    if max_width is not None and (type(max_width) is not int or max_width < 1):
        raise ValueError('max_width must be a positive integer')
    device = discover_device()
    command = [_ffmpeg(), '-hide_banner', '-loglevel', 'error', '-nostdin',
               '-f', 'avfoundation', '-pixel_format', 'uyvy422', '-framerate', '30',
               '-video_size', '1920x1080', '-i', f'{device}:none', '-frames:v', '1']
    if max_width is not None:
        command += ['-vf', f'scale=min(iw\\,{max_width}):-1']
    command += ['-c:v', 'png', '-f', 'image2pipe', 'pipe:1']
    result = _run(command)
    if result.returncode:
        detail = result.stderr.decode(errors='replace')[-2000:]
        raise CaptureError(f'Capture failed. Check Camera access and HDMI signal. {detail}')
    image_resolution(result.stdout)
    return result.stdout
