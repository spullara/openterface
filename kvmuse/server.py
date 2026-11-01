"""MCP tools for an Openterface KVM, served over stdio."""
import threading
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP, Image
from pydantic import Field

from . import capture
from .ch9329 import CH9329, list_devices
from .hid_keys import KEYS, MODIFIERS, text_keys

mcp = FastMCP('kvmuse')
_control_lock = threading.Lock()


def _control(operation):
    # Serialize complete gestures, including their release reports.
    with _control_lock, CH9329() as device:
        operation(device)
    return 'ok'


@mcp.tool()
def screenshot() -> Image:
    """Capture the HDMI input as PNG. Requires macOS Camera permission."""
    return Image(data=capture.capture_frame(), format='png')


@mcp.tool()
def type_text(text: Annotated[str, Field(max_length=4096)]) -> str:
    """Type text using the target's US keyboard layout (maximum 4096 characters)."""
    text_keys(text)
    return _control(lambda device: device.type_text(text))


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
    return _control(lambda device: device.mouse_move_abs(x, y))


@mcp.tool()
def mouse_click(button: Literal['left', 'right', 'middle'] = 'left',
                double: bool = False) -> str:
    """Click a mouse button once, or twice when double is true."""
    def click(device):
        for _ in range(2 if double else 1):
            device.mouse_click(button)
    return _control(click)


@mcp.tool()
def mouse_scroll(amount: Annotated[int, Field(ge=-127, le=127)]) -> str:
    """Scroll wheel steps from -127 to 127; positive values scroll up."""
    return _control(lambda device: device.mouse_scroll(amount))


@mcp.tool()
def kvm_status() -> dict:
    """Report serial presence and capture availability without sending HID input.

    Camera denial or discovery failure is reported as an error, with bounded waits.
    """
    result = {}
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


def main():
    mcp.run(transport='stdio')


if __name__ == '__main__':
    main()
