# kvmuse

Control an Openterface Mini-KVM through MCP over stdio. The host requires macOS,
Python 3.11+, uv, ffmpeg, and Apple command line tools (swift).

## Setup

Connect the serial and HDMI capture devices, then install dependencies:

```sh
uv sync
claude mcp add kvmuse -- uv run --directory /Users/sam/Developer/kvmuse kvmuse-mcp
```

Grant Camera access to the host app in System Settings > Privacy & Security >
Camera, then restart the app. Capture returns a clear error if access is missing.
The server selects one Openterface serial device automatically at 115200 baud.
Disconnect extra matching devices if selection fails.

Tools: screenshot, type_text, press_key, mouse_move, mouse_click, mouse_scroll,
and kvm_status. Screenshots return PNG image content. Status reports device
presence and capture errors; it does not send input or verify the HDMI signal.
Mouse coordinates are fractions from 0 to 1. Scroll accepts -127 to 127 steps.
Text requires a US target keyboard layout and supports up to 4096 characters.
Keys use raw USB HID codes on macOS and Windows. The cmd/gui modifier maps to
Command on macOS and the Windows key on Windows. press_key accepts esc,
F1-F12, ctrl-alt-del, and ctrl/shift/alt/cmd/gui/win modifiers.

Run the server directly with `uv run kvmuse-mcp`. Run tests with `uv run pytest`.
