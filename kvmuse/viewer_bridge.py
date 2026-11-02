"""Authenticated, bounded loopback bridge compatible with the Swift Viewer."""
import base64
import binascii
from concurrent.futures import TimeoutError as FutureTimeout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
from urllib.parse import parse_qs, urlsplit

from .bridge import Bridge
from .viewer_core import WAKE

MAX_REPORTS = 8193
MAX_BODY = ((MAX_REPORTS * 8 + 2) // 3) * 4 + 128


def private_path(path, directory=False):
    """Protect the discovery token with the current user's Windows ACL."""
    if os.name == 'nt':
        import win32api
        import win32con
        import win32security
        import ntsecuritycon
        token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
        try:
            sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
            acl = win32security.ACL()
            flags = (win32con.OBJECT_INHERIT_ACE | win32con.CONTAINER_INHERIT_ACE) if directory else 0
            acl.AddAccessAllowedAceEx(win32security.ACL_REVISION, flags, ntsecuritycon.FILE_ALL_ACCESS, sid)
            win32security.SetNamedSecurityInfo(str(path), win32security.SE_FILE_OBJECT,
                win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
                None, None, acl, None)
        finally:
            token.Close()
    else:
        path.chmod(0o700 if directory else 0o600)


def validate_reports(path, value):
    if path == '/text':
        encoded = value.get('keyboard_base64')
        if not isinstance(encoded, str):
            raise ValueError('Expected keyboard_base64.')
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError('Invalid keyboard base64.') from None
        if len(raw) % 8 or len(raw) > MAX_REPORTS * 8:
            raise ValueError('Invalid keyboard report count or size.')
        reports = [[2, *raw[i:i + 8]] for i in range(0, len(raw), 8)]
    else:
        reports = value.get('reports')
    if not isinstance(reports, list) or len(reports) > MAX_REPORTS + 1:
        raise ValueError('Invalid report count.')
    for report in reports:
        if not isinstance(report, list) or not report or any(type(b) is not int or not 0 <= b <= 255 for b in report):
            raise ValueError('Expected report bytes.')
        command = report[0]
        if command not in (2, 4, 5) or len(report) != {2: 9, 4: 8, 5: 6}[command]:
            raise ValueError('Invalid command or report length.')
        if (path == '/mouse') != (command != 2):
            raise ValueError('Wrong report type for this endpoint.')
        if command == 2 and report[2] != 0:
            raise ValueError('Keyboard reserved byte must be zero.')
        if command in (4, 5) and (report[1] != (2 if command == 4 else 1) or report[2] > 7):
            raise ValueError('Invalid mouse mode or buttons.')
        if command == 4 and (report[4] > 15 or report[6] > 15):
            raise ValueError('Mouse coordinates must be in 0..4095.')
        if command == 5 and 128 in report[3:]:
            raise ValueError('Relative mouse values must be in -127..127.')
    return reports


class LimitedServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, *args):
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(*args)

    def process_request(self, request, address):
        if self.slots.acquire(blocking=False):
            try:
                super().process_request(request, address)
            except Exception:
                self.slots.release()
                raise
        else:
            self.shutdown_request(request)

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class ViewerBridge:
    def __init__(self, serial, camera, activity=lambda _: None, directory=None):
        self.serial, self.camera, self.activity = serial, camera, activity
        self.directory = Path(directory) if directory is not None else Path.home() / '.kvmuse'
        self.path = self.directory / 'bridge.json'
        self.token = secrets.token_urlsafe(48)
        self.http = self.thread = self.lockfile = None
        self.activity_lock = threading.Lock()
        self.active_requests = 0

    def _activity(self, delta):
        with self.activity_lock:
            self.active_requests += delta
            self.activity(self.active_requests > 0)

    def start(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        private_path(self.directory, directory=True)
        self.lockfile = (self.directory / 'viewer.lock').open('a+b')
        try:
            self.lockfile.seek(0, 2)
            if self.lockfile.tell() == 0:
                self.lockfile.write(b'0')
                self.lockfile.flush()
            self.lockfile.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.lockfile.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.lockfile.close()
            self.lockfile = None
            raise RuntimeError('Another KVM Viewer is running. Close it first.') from exc
        try:
            if Bridge.discover(self.path) is not None:
                raise RuntimeError('Another KVM Viewer bridge is running. Close it first.')
            owner = self
            class Handler(BaseHTTPRequestHandler):
                def setup(self):
                    super().setup()
                    self.connection.settimeout(5)

                def log_message(self, *_):
                    pass

                def respond(self, code, body, content_type='text/plain'):
                    body = body.encode() if isinstance(body, str) else body
                    self.send_response(code)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.wfile.write(body)

                def do_GET(self):
                    self.handle_api()

                def do_POST(self):
                    self.handle_api()

                def handle_api(self):
                    try:
                        authorization = self.headers.get_all('Authorization', [])
                        if len(authorization) != 1 or not secrets.compare_digest(
                                authorization[0].encode('utf-8'), f'Bearer {owner.token}'.encode('ascii')):
                            self.respond(401, 'Unauthorized')
                            return
                        if len(str(self.headers).encode()) > 8192 or self.headers.get('Transfer-Encoding') is not None:
                            raise ValueError('Invalid request headers.')
                        target = urlsplit(self.path)
                        if self.command == 'GET':
                            if target.path == '/status':
                                ready = owner.camera.latest()[1] is not None
                                self.respond(200, json.dumps({'serial': {'present': owner.serial.connected},
                                    'capture': {'available': ready}}), 'application/json')
                            elif target.path == '/frame':
                                query = parse_qs(target.query)
                                widths = query.get('max_width', ['1280'])
                                if len(widths) != 1:
                                    raise ValueError('Expected one max_width.')
                                width = int(widths[0])
                                if not 1 <= width <= 4096:
                                    raise ValueError('max_width must be in 1..4096.')
                                self.respond(200, owner.camera.png(width), 'image/png')
                            else:
                                self.respond(404, 'Unknown endpoint')
                            return
                        if target.path not in ('/keys', '/text', '/mouse', '/wake'):
                            self.respond(404, 'Unknown endpoint')
                            return
                        lengths = self.headers.get_all('Content-Length', [])
                        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
                            raise ValueError('Expected one Content-Length.')
                        length = int(lengths[0])
                        if length > MAX_BODY:
                            self.respond(413, 'Request body too large')
                            return
                        body = self.rfile.read(length)
                        if len(body) != length:
                            raise ValueError('Incomplete request body.')
                        value = json.loads(body)
                        if not isinstance(value, dict):
                            raise ValueError('Expected a JSON object.')
                        reports = WAKE if target.path == '/wake' else validate_reports(target.path, value)
                        owner._activity(1)
                        try:
                            owner.serial.submit(reports).result(timeout=25)
                            self.respond(200, 'ok')
                        finally:
                            owner._activity(-1)
                    except (ValueError, UnicodeError) as exc:
                        self.respond(400, str(exc))
                    except (OSError, RuntimeError, FutureTimeout) as exc:
                        self.respond(503, str(exc) or 'Serial batch timed out; it was not retried.')

            self.http = LimitedServer(('127.0.0.1', 0), Handler)
            temporary = self.directory / ('.bridge-' + secrets.token_hex(12))
            try:
                temporary.touch(mode=0o600)
                private_path(temporary)
                temporary.write_text(json.dumps({'port': self.http.server_port, 'token': self.token}), encoding='utf-8')
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
            self.thread = threading.Thread(target=self.http.serve_forever, daemon=True, name='kvm-bridge')
            self.thread.start()
        except Exception:
            self.close()
            raise

    def close(self):
        if self.thread:
            self.http.shutdown()
            self.thread.join(timeout=2)
            self.thread = None
        if self.http:
            self.http.server_close()
            self.http = None
        try:
            if self.path.exists() and json.loads(self.path.read_text(encoding='utf-8')).get('token') == self.token:
                self.path.unlink()
        except (OSError, ValueError):
            pass
        if self.lockfile:
            self.lockfile.close()
            self.lockfile = None
