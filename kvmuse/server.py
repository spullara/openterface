"""MCP tools for an Openterface KVM, served over stdio."""
import threading
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP, Image
from pydantic import Field

from . import capture
from .bridge import Bridge, Reports
from .ch9329 import CH9329, list_devices
from .hid_keys import KEYS, MODIFIERS, text_keys

mcp = FastMCP('kvmuse')
_control_lock = threading.Lock()


def _control(operation, endpoint="/keys"):
    bridge = Bridge.discover()
    if bridge is not None:
        device = Reports()
        operation(device)
        return bridge.request(endpoint, {"reports": device.reports}).decode()
    # Serialize complete gestures, including their release reports.
    with _control_lock, CH9329() as device:
        operation(device)
    return 'ok'


@mcp.tool()
def screenshot() -> list:
    """Capture HDMI as PNG through Viewer, or direct capture with Camera permission."""
    bridge = Bridge.discover()
    data = bridge.request('/frame') if bridge else capture.capture_frame()
    result = [Image(data=data, format='png')]
    if capture.is_black_frame(data):
        result.append('The display may be asleep. Call wake_display, wait, then take another screenshot.')
    return result


@mcp.tool()
def type_text(text: Annotated[str, Field(max_length=4096)]) -> str:
    """Type text using the target's US keyboard layout (maximum 4096 characters)."""
    text_keys(text)
    return _control(lambda device: device.type_text(text), "/text")


@mcp.tool()
def press_key(key: str, modifiers: list[str] | None = None) -> str:
    """Press and release a named HID key, including esc, F1-F12 or ctrl-alt-del.

    Modifiers: ctrl, shift, alt, cmd, gui, win. cmd/gui map to the Windows key.
    """
    key = key.lower()
    names = list(modifiers or [])
    if key == 'ctrl-alt-del':
        key = 'delete'
        names += ['ctrl', 'alt']
    key = {'esc': 'escape'}.get(key, key)
    if key not in KEYS:
        raise ValueError(f'Unknown key: {key}')
    mask = 0
    for name in names:
        if name.lower() not in MODIFIERS:
            raise ValueError(f'Unknown modifier: {name}')
        mask |= MODIFIERS[name.lower()]
    def press(device):
        try:
            device.key_press([key], mask)
        finally:
            device.key_release_all()
    return _control(press)


@mcp.tool()
def mouse_move(x: Annotated[float, Field(ge=0, le=1)],
               y: Annotated[float, Field(ge=0, le=1)]) -> str:
    """Move to absolute screen fractions: top-left 0,0; bottom-right 1,1."""
    return _control(lambda device: device.mouse_move_abs(x, y), "/mouse")


@mcp.tool()
def mouse_click(button: Literal['left', 'right', 'middle'] = 'left',
                double: bool = False) -> str:
    """Click a mouse button once, or twice when double is true."""
    def click(device):
        for _ in range(2 if double else 1):
            device.mouse_click(button)
    return _control(click, "/mouse")


@mcp.tool()
def mouse_scroll(amount: Annotated[int, Field(ge=-127, le=127)]) -> str:
    """Scroll wheel steps from -127 to 127; positive values scroll up."""
    return _control(lambda device: device.mouse_scroll(amount), "/mouse")


@mcp.tool()
def kvm_status() -> dict:
    """Report serial presence and capture availability without sending HID input.

    Camera denial or discovery failure is reported as an error, with bounded waits.
    """
    bridge = Bridge.discover()
    if bridge is not None:
        return {**bridge.status, "path": "bridge"}
    result = {"path": "direct"}
    try:
        ports = list_devices()
        result['serial'] = {'present': bool(ports), 'ports': ports}
    except Exception as exc:
        result['serial'] = {'present': False, 'error': str(exc)}
    try:
        result['capture'] = {'available': True, 'device': capture.discover_device()}
    except capture.CaptureError as exc:
        result['capture'] = {'available': False, 'error': str(exc)}
    return result


@mcp.tool()
def wake_display() -> str:
    """Wake the target with Shift and a one-pixel mouse wiggle."""
    bridge = Bridge.discover()
    if bridge is not None:
        return bridge.request('/wake', {}).decode()
    def wake(device):
        try:
            device.key_press([], 2)
        finally:
            device.key_release_all()
        device.mouse_move_rel(1, 0)
        device.mouse_move_rel(-1, 0)
    with _control_lock, CH9329() as device:
        wake(device)
    return 'ok'


def main():
    mcp.run(transport='stdio')


if __name__ == '__main__':
    main()
