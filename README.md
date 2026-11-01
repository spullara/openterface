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

## Loopback / multi-monitor setups

In a loopback setup, the host and target are the same Mac. KVM input affects that live Mac.
Capture shows only the monitor that the KVM HDMI connection drives.
Spotlight and other UI can open on the main display, outside the capture.

Place a TextEdit document on the KVM monitor. Give TextEdit focus before typing, for example with `open -a TextEdit`.
Allow time for focus to change. Text goes to the focused app, even when that app is on another monitor.
TextEdit can automatically capitalize the first letter.
Camera permission is per app. Terminal permission does not grant access to the agent host app.

For a mouse check, place the pointer near the center of the KVM monitor.
Run this command in the Terminal that has Camera permission:

```sh
mkdir -p /tmp/kvmuse-e2e
uv run python -m kvmuse.smoke --mouse-demo --screenshot /tmp/kvmuse-e2e/mouse.png
```

Watch the pointer during the sequence. It moves right, down, left, then up, with no clicks.
The relative offsets sum to zero. Screen edges and pointer acceleration can prevent an exact return to the starting pixel.
The final screenshot records the screen after movement. It does not prove the path, and HDMI capture can omit the cursor.

## Unlock and keep awake (manual use only)

Close the Viewer before these commands: they need sole access to the serial port.
Only a person may run these commands. Agents must never run them with a password.
Never put a password in arguments, chat, logs, or scripts. Both commands use a
hidden terminal prompt and reject unsupported US-layout characters before input.

Run `uv run python -m kvmuse.unlock` with the target login password field selected.
It wakes with Shift, clears the field, types the password, and presses Enter.
Check the target screen yourself. This command cannot confirm login success.

Run `uv run python -m kvmuse.keep_awake --dry-run` to print the steps without
opening the serial port or asking for a password. On an unlocked macOS target,
run `uv run python -m kvmuse.keep_awake` to open Terminal and change power and
screen-saver settings. Use an administrator password. Both accept `--port PATH`.
The command uses fixed delays and cannot inspect prompts. Watch the target:
if Terminal or sudo does not open as expected, interrupt the command. A missing
sudo prompt can expose typed password text in the target shell. Verify the final
settings output; sending input does not prove that a command succeeded.

These settings reduce physical-access protection. Keep the target in a secure
place. They do not disable the login password, managed lock policies, or FileVault.
After a restart, FileVault can require a person to unlock the startup disk.

## KVM Viewer (macOS 14 or later)

Build the native viewer with Swift 6 and Xcode:

```sh
cd viewer
swift test
./build.sh
cd ..
open "viewer/build/KVM Viewer.app"
```

Allow Camera access at first launch. If access is denied, enable KVM Viewer in
System Settings > Privacy & Security > Camera, then restart the app.
The viewer selects the Openterface camera at 1080p30, with a 720p30 fallback.

Control starts OFF. With the viewer focused, press **Ctrl+Option+Cmd+K** to toggle
control. The badge shows the mode. When control is ON, keyboard input, pointer
movement, left/right clicks, dragging, and scrolling go to the target.
The same hotkey releases control. Leaving the window also releases held input.
Use the KVM menu-bar item to toggle always-on-top mode or reconnect serial.
Stop direct serial clients before starting the viewer.

The app uses one serial queue and a shared latest-frame buffer. The agent bridge
is a separate task. Sam must check video, input, and the escape hotkey on hardware.
