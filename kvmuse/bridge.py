"""Authenticated loopback client. A failed operation is never retried directly."""
import json
from pathlib import Path
import urllib.request
import urllib.error
from .ch9329 import CH9329

class BridgeError(RuntimeError):
    pass

class Bridge:
    def __init__(self, port, token):
        if type(port) is not int or not 1 <= port <= 65535 or not isinstance(token, str) or not token:
            raise BridgeError('Invalid Viewer bridge discovery file. Restart KVM Viewer.')
        self.url = f'http://127.0.0.1:{port}'
        self.token = token

    def request(self, path, payload=None):
        request = urllib.request.Request(self.url + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'})
        try:
            # Ignore proxy settings and never forward the token on redirects.
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):
                    return None
            with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raise BridgeError(f'Viewer bridge error ({exc.code}): {exc.read(4096).decode(errors="replace")}') from exc
        except (OSError, urllib.error.URLError) as exc:
            raise BridgeError(f'Viewer bridge did not complete the request: {exc}. No direct retry was made.') from exc

    @classmethod
    def discover(cls, path=None):
        path = path or Path.home() / '.kvmuse/bridge.json'
        try:
            value = json.loads(path.read_text())
            bridge = cls(value['port'], value['token'])
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise BridgeError('Cannot read Viewer bridge discovery file. Restart KVM Viewer.') from exc
        try:
            bridge.status = json.loads(bridge.request('/status'))
        except BridgeError as exc:
            if isinstance(exc.__cause__, urllib.error.HTTPError):
                raise
            return None
        except ValueError as exc:
            raise BridgeError('Viewer returned invalid status.') from exc
        return bridge

class Reports(CH9329):
    """Use the existing HID encoder without opening a serial device."""
    def __init__(self):
        super().__init__()
        self.reports = []
    def _send(self, command, payload):
        self.reports.append([command, *payload])
