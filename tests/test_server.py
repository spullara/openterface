import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from kvmuse import server


def test_stdio_status_without_hardware():
    # Patch only the hardware boundaries in the child, retaining real MCP transport.
    code = '''
from kvmuse import server
server.list_devices = lambda: []
def unavailable():
    raise server.capture.CaptureError("Camera access is not authorized")
server.capture.discover_device = unavailable
server.main()
'''
    async def run():
        async with stdio_client(StdioServerParameters(command=sys.executable, args=['-c', code])) as streams:
            async with ClientSession(*streams) as client:
                await client.initialize()
                tools = await client.list_tools()
                assert {t.name for t in tools.tools} == {
                    'screenshot', 'type_text', 'press_key', 'mouse_move',
                    'mouse_click', 'mouse_scroll', 'kvm_status'}
                result = await client.call_tool('kvm_status', {})
                assert not result.isError
                status = json.loads(result.content[0].text)
                assert status['serial']['present'] is False
                assert 'Camera access' in status['capture']['error']
                result = await client.call_tool('screenshot', {})
                assert result.isError
                assert 'Camera access' in result.content[0].text
                for name, args in [('mouse_move', {'x': 2, 'y': 0}),
                                   ('mouse_scroll', {'amount': 128}),
                                   ('mouse_click', {'button': 'invalid'})]:
                    assert (await client.call_tool(name, args)).isError
    asyncio.run(asyncio.wait_for(run(), timeout=20))


def test_gestures(monkeypatch):
    calls = []
    class Device:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def key_press(self, keys, mask): calls.append((keys, mask))
        def key_release_all(self): calls.append('release')
        def mouse_click(self, button): calls.append(button)
    monkeypatch.setattr(server, 'CH9329', Device)
    server.press_key('ctrl-alt-del')
    assert calls == [(['delete'], 5), 'release']
    calls.clear()
    server.mouse_click('right', True)
    assert calls == ['right', 'right']
