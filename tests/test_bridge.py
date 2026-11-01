import json
import base64
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO
import pytest
from PIL import Image
from kvmuse.bridge import Bridge, BridgeError
from kvmuse import capture, server

@pytest.fixture
def endpoint(tmp_path):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path, self.headers.get('Authorization')))
            self.send_response(200 if self.path == '/status' else 503)
            self.end_headers()
            self.wfile.write(b'{"path":"bridge"}' if self.path == '/status' else b'Camera unavailable')
        def do_POST(self):
            calls.append((self.path, self.headers.get('Authorization'), json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            self.send_response(503)
            self.end_headers()
            self.wfile.write(b'Serial unavailable')
        def log_message(self, *args): pass
    http = HTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    path = tmp_path / 'bridge.json'
    path.write_text(json.dumps({'port': http.server_port, 'token': 'secret'}))
    yield path, calls
    http.shutdown(); thread.join(); http.server_close()

def test_discovery_token_and_no_midrequest_fallback(endpoint, monkeypatch):
    path, calls = endpoint
    bridge = Bridge.discover(path)
    assert calls == [('/status', 'Bearer secret')]
    monkeypatch.setattr(Bridge, 'discover', lambda: bridge)
    monkeypatch.setattr(server, 'CH9329', lambda: pytest.fail('Must not open serial'))
    with pytest.raises(BridgeError, match='Serial unavailable'):
        server.type_text('a')
    assert calls[-1][0:2] == ('/text', 'Bearer secret')
    assert base64.b64decode(calls[-1][2]['keyboard_base64'])[:8] == bytes([0, 0, 4, 0, 0, 0, 0, 0])
    with pytest.raises(BridgeError, match='Camera unavailable'):
        server.screenshot()

def test_missing_and_malformed(tmp_path):
    path = tmp_path / 'bridge.json'
    assert Bridge.discover(path) is None
    path.write_text('oops')
    with pytest.raises(BridgeError): Bridge.discover(path)

def test_unavailable_status(tmp_path):
    import socket
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    path = tmp_path / 'bridge.json'
    path.write_text(json.dumps({'port': port, 'token': 'secret'}))
    assert Bridge.discover(path) is None

def test_black_frame_and_hint(monkeypatch):
    def png(color):
        output = BytesIO(); Image.new('RGB', (64, 36), color).save(output, 'PNG'); return output.getvalue()
    assert capture.is_black_frame(png('black'))
    assert not capture.is_black_frame(png('white'))
    monkeypatch.setattr(Bridge, 'discover', lambda: None)
    monkeypatch.setattr(capture, 'capture_frame', lambda: png('black'))
    assert 'wake_display' in server.screenshot()[1]


def test_text_boundary(monkeypatch):
    calls = []
    class FakeBridge:
        def request(self, path, payload):
            calls.append((path, payload))
            return b'ok'
    monkeypatch.setattr(Bridge, 'discover', lambda: FakeBridge())
    async def run():
        await server.mcp.call_tool('type_text', {'text': 'A' * 4096})
        assert len(calls) == 1
        payload = calls[0][1]
        raw = base64.b64decode(payload['keyboard_base64'])
        assert len(raw) == 8193 * 8
        assert raw[:8] == bytes([2, 0, 4, 0, 0, 0, 0, 0])
        assert len(json.dumps(payload).encode()) <= ((8193 * 8 + 2) // 3) * 4 + 128
        with pytest.raises(Exception, match='4096'):
            await server.mcp.call_tool('type_text', {'text': 'A' * 4097})
        assert len(calls) == 1
    asyncio.run(run())
