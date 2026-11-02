import base64
from concurrent.futures import Future
import json
import os
import socket
import threading

import pytest

from kvmuse.bridge import Bridge, BridgeError
from kvmuse.viewer_bridge import MAX_BODY, MAX_REPORTS, ViewerBridge, validate_reports
from kvmuse.viewer_camera import CameraStream
from kvmuse.viewer_core import SerialWorker, keyboard


class FakeSerial:
    connected = True
    def __init__(self):
        self.batches = []
        self.fail = False
    def submit(self, reports):
        future = Future()
        self.batches.append(reports)
        if self.fail:
            future.set_exception(RuntimeError('Device unplugged'))
        else:
            future.set_result('ok')
        return future


@pytest.fixture
def endpoint(tmp_path):
    serial = FakeSerial()
    camera = CameraStream()
    camera.frame = (4, 2, bytes([90] * 24))
    active = []
    bridge = ViewerBridge(serial, camera, activity=active.append, directory=tmp_path / 'private')
    bridge.start()
    yield bridge, serial, active
    bridge.close()


def client(bridge):
    return Bridge.discover(bridge.path)


def test_bridge_contract_and_cleanup(endpoint):
    owner, serial, active = endpoint
    bridge = client(owner)
    assert bridge.status == {'serial': {'present': True}, 'capture': {'available': True}}
    from kvmuse.capture import image_resolution
    assert image_resolution(bridge.request('/frame?max_width=2')) == (2, 1)
    assert bridge.request('/keys', {'reports': [keyboard([4]), keyboard()]}) == b'ok'
    encoded = base64.b64encode(bytes(keyboard([5])[1:])).decode()
    bridge.request('/text', {'keyboard_base64': encoded})
    bridge.request('/mouse', {'reports': [[4, 2, 1, 0, 8, 0, 8, 0], [5, 1, 0, 1, 0, 0]]})
    bridge.request('/wake', {})
    assert len(serial.batches) == 4
    assert active == [True, False] * 4
    assert serial.batches[1] == [keyboard([5])]
    path = owner.path
    owner.close()
    assert not path.exists()


def test_authentication_and_limits(endpoint):
    owner, serial, active = endpoint
    wrong = Bridge(owner.http.server_port, 'wrong-token')
    with pytest.raises(BridgeError, match='401'):
        wrong.request('/status')
    bridge = client(owner)
    for path, value in [('/keys', {'reports': [[4, 2, 0, 0, 0, 0, 0, 0]]}),
                        ('/keys', {'reports': [[2, 0, 1, 4, 0, 0, 0, 0, 0]]}),
                        ('/mouse', {'reports': [[4, 2, 0, 0, 16, 0, 0, 0]]}),
                        ('/mouse', {'reports': [[5, 1, 0, 128, 0, 0]]}),
                        ('/text', {'keyboard_base64': '???'}),
                        ('/text', {'keyboard_base64': base64.b64encode(b'a').decode()}),
                        ('/keys', {'reports': [[True]]}),
                        ('/keys', []),
                        ('/frame?max_width=0', None),
                        ('/frame?max_width=999999', None)]:
        with pytest.raises(BridgeError, match='400'):
            bridge.request(path, value)
    with pytest.raises(BridgeError, match='404'):
        bridge.request('/unknown')
    with pytest.raises(BridgeError, match='413'):
        bridge.request('/keys', {'reports': ['x' * MAX_BODY]})
    assert serial.batches == [] and active == []


def test_maximum_text_and_failure(endpoint):
    owner, serial, active = endpoint
    bridge = client(owner)
    encoded = base64.b64encode(bytes(8 * MAX_REPORTS)).decode()
    bridge.request('/text', {'keyboard_base64': encoded})
    assert len(serial.batches[0]) == MAX_REPORTS
    too_large = base64.b64encode(bytes(8 * (MAX_REPORTS + 1))).decode()
    with pytest.raises(BridgeError, match='400|413'):
        bridge.request('/text', {'keyboard_base64': too_large})
    serial.fail = True
    with pytest.raises(BridgeError, match='503.*Device unplugged'):
        bridge.request('/wake', {})
    assert active[-2:] == [True, False]


def test_second_instance_and_owned_discovery(endpoint):
    owner, _, _ = endpoint
    second = ViewerBridge(owner.serial, owner.camera, directory=owner.directory)
    original = owner.path.read_bytes()
    with pytest.raises(RuntimeError, match='Another KVM Viewer'):
        second.start()
    second.close()
    assert owner.path.read_bytes() == original
    owner.path.write_text(json.dumps({'port': 1, 'token': 'different owner'}))
    owner.close()
    assert owner.path.exists()


@pytest.mark.skipif(os.name != 'nt', reason='Windows ACL check')
def test_windows_discovery_acl(endpoint):
    import win32api
    import win32con
    import win32security
    owner, _, _ = endpoint
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        for path in (owner.directory, owner.path):
            security = win32security.GetFileSecurity(str(path), win32security.DACL_SECURITY_INFORMATION)
            acl = security.GetSecurityDescriptorDacl()
            assert acl.GetAceCount() == 1
            assert acl.GetAce(0)[2] == sid
    finally:
        token.Close()


def test_bad_http_framing(endpoint):
    owner, serial, _ = endpoint
    for headers in ('Content-Length: 2\r\nContent-Length: 2',
                    'Transfer-Encoding: chunked', 'Content-Length: -1'):
        request = (f'POST /wake HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer {owner.token}\r\n'
                   f'{headers}\r\n\r\n{{}}').encode()
        with socket.create_connection(('127.0.0.1', owner.http.server_port), timeout=2) as connection:
            connection.sendall(request)
            assert b'400' in connection.recv(1024).split(b'\r\n')[0]
    assert serial.batches == []


def test_bridge_batches_do_not_interleave_with_manual_input(tmp_path):
    entered, unblock = threading.Event(), threading.Event()
    sent = []
    class Device:
        def __init__(self, _):
            pass
        def open(self):
            return self
        def _send(self, command, payload):
            sent.append([command, *payload])
            if payload[2:3] == b'\x04':
                entered.set()
                assert unblock.wait(3)
        def close(self):
            pass
    worker = SerialWorker(device_factory=Device)
    owner = ViewerBridge(worker, CameraStream(), directory=tmp_path)
    try:
        worker.submit(reconnect=True).result(2)
        owner.start()
        bridge = client(owner)
        error = []
        def send_bridge():
            try:
                bridge.request('/keys', {'reports': [keyboard([4]), keyboard()]})
            except Exception as exc:
                error.append(exc)
        request = threading.Thread(target=send_bridge)
        request.start()
        assert entered.wait(2)
        manual = worker.submit([keyboard([5]), keyboard()])
        unblock.set()
        request.join(3)
        manual.result(2)
        assert not request.is_alive() and not error
        assert sent[:4] == [keyboard([4]), keyboard(), keyboard([5]), keyboard()]
    finally:
        unblock.set()
        owner.close()
        worker.close()
