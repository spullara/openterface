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

## Intent connection

Add a stdio MCP server in the host application's MCP settings. Use these fields:

- Command: the absolute path from `command -v uv`.
- Arguments: `run`, `--directory`, `/Users/sam/Developer/kvmuse`, `kvmuse-mcp`.

Replace the repository path if you move this checkout. Restart the connection after changes.

## Tool reference

| Tool | Arguments | Result |
| --- | --- | --- |
| `screenshot` | None | PNG of the HDMI input |
| `type_text` | `text` | Types US-layout text, maximum 4096 characters |
| `press_key` | `key`, optional `modifiers` list | Presses and releases a key |
| `mouse_move` | `x`, `y` from 0 to 1 | Moves the pointer to screen fractions |
| `mouse_click` | `button`: left/right/middle, `double`: boolean | Clicks at the current pointer position |
| `mouse_scroll` | `amount` from -127 to 127 | Sends wheel steps, positive upward |
| `kvm_status` | None | Reports serial presence and capture discovery |

## Hardware smoke sequence

The target must be an unlocked Mac with Command-Space assigned to Spotlight.
The sequence opens Spotlight, types `kvmuse test`, and sends Escape in cleanup.
It never sends Enter. Do not use this sequence while someone operates the target.

```sh
uv run python -m kvmuse.e2e --output /tmp/kvmuse-e2e
```

Inspect `before.png` and `after.png`. The second image must show the typed text.
Capture calls have subprocess timeouts. Serial operations require successful ACKs.
An ACK proves chip acceptance, not visible input on the target.

Without Camera access, run only the serial sequence:

```sh
uv run python -m kvmuse.e2e --serial-only
```

Mouse proof requires a visible, safe target. After capture works, select an empty
area or a test field before a mouse click. Do not click an unknown screen.

## Troubleshooting

- **Camera permission:** Grant access to the app that starts the server, then restart that app.
  A headless process cannot reliably show the permission prompt. Status 0 means permission is not set.
  Run this command from the same host context: `swift -e 'import AVFoundation; print(AVCaptureDevice.authorizationStatus(for: .video).rawValue)'`.
  Status 3 means authorized. A Terminal grant does not prove that Intent has access.
- **Device not found:** Reconnect the host USB cable. Run `uv run python -m kvmuse.smoke --list`.
  The current serial port is `/dev/cu.usbmodem11201`. Port names can change after reconnection.
  The server requires exactly one matching device. The smoke CLI accepts `--port` for an explicit port.
- **Serial permission or timeout:** Close other KVM applications that use the serial port.
  Make sure that the host USB connection is present. The driver uses 115200 baud.
- **Capture error or blank image:** Make sure that the target HDMI output is active and the capture device is connected.
  The capture device name is `Openterface`. The capture module supplies explicit format, frame rate, and size settings.
- **Incorrect text:** Select a US keyboard layout on the target. Text entry does not use the clipboard.
