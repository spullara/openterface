"""Bounded FFmpeg camera capture on macOS and Windows."""
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
                              timeout=timeout, check=False,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as exc:
        raise CaptureError('Camera operation timed out. Check Camera access and the HDMI connection.') from exc
    except OSError as exc:
        raise CaptureError(f'Cannot run {command[0]}: {exc}') from exc


def check_permission():
    if sys.platform == 'win32':
        return  # DirectShow reports access errors when opening the camera.
    if sys.platform != 'darwin':
        raise CaptureError('Camera capture supports macOS and Windows hosts.')
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


def parse_dshow_devices(output):
    """Use DirectShow alternative names so duplicate friendly names stay distinct."""
    devices = []
    pending = None
    for line in output.splitlines():
        match = re.search(r'"(.*)" \((video|audio|none)\)\s*$', line)
        if match:
            pending = len(devices) if match[2] == 'video' else None
            if pending is not None:
                devices.append((match[1], match[1]))
        elif pending is not None:
            alternative = re.search(r'Alternative name "(.*)"\s*$', line)
            if alternative:
                devices[pending] = (alternative[1], devices[pending][1])
                pending = None
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
    if sys.platform == 'darwin' and fallback.is_file():
        return str(fallback)
    raise CaptureError('ffmpeg is missing. Install ffmpeg before capturing.')


def discover_device():
    check_permission()
    if sys.platform == 'win32':
        result = _run([_ffmpeg(), '-hide_banner', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'])
        return select_device(parse_dshow_devices(result.stderr.decode(errors='replace')))
    result = _run([_ffmpeg(), '-hide_banner', '-f', 'avfoundation', '-list_devices', 'true', '-i', ''])
    return select_device(parse_devices(result.stderr.decode(errors='replace')))


def input_command(device, size='1920x1080'):
    command = [_ffmpeg(), '-hide_banner', '-loglevel', 'error', '-nostdin']
    if sys.platform == 'win32':
        return command + ['-f', 'dshow', '-rtbufsize', '64M', '-framerate', '30',
                          '-video_size', size, '-i', f'video={device}']
    if sys.platform == 'darwin':
        return command + ['-f', 'avfoundation', '-pixel_format', 'uyvy422', '-framerate', '30',
                          '-video_size', size, '-i', f'{device}:none']
    raise CaptureError('Camera capture supports macOS and Windows hosts.')


def capture_error(detail):
    if sys.platform == 'win32':
        return CaptureError('Capture failed. Check Windows Settings > Privacy & security > Camera '
                            '(allow desktop apps), close other camera apps, and check HDMI. ' + detail)
    return CaptureError('Capture failed. Check Camera access and HDMI signal. ' + detail)


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
    for size in ('1920x1080', '1280x720'):
        command = input_command(device, size) + ['-frames:v', '1']
        if max_width is not None:
            command += ['-vf', f'scale=min(iw\\,{max_width}):-1']
        command += ['-c:v', 'png', '-f', 'image2pipe', 'pipe:1']
        result = _run(command)
        if not result.returncode:
            image_resolution(result.stdout)
            return result.stdout
    raise capture_error(result.stderr.decode(errors='replace')[-2000:])


def is_black_frame(data: bytes) -> bool:
    """Return true when at least 99 percent of sampled pixels are dark."""
    from io import BytesIO
    from PIL import Image
    with Image.open(BytesIO(data)) as image:
        image = image.convert('RGB')
        image.thumbnail((64, 36))
        pixels = list(image.get_flattened_data())
        return bool(pixels) and sum(max(pixel) <= 24 for pixel in pixels) / len(pixels) >= .99
