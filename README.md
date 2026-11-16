# kvmuse

Control an Openterface Mini-KVM through MCP over stdio on Linux, macOS or Windows 10/11.
The host requires Python 3.11+, uv, and FFmpeg. Python 3.13 is recommended for the
Windows Viewer. macOS direct capture also requires Apple command line tools (Swift).
The host OS is independent of the target: a Windows host can control a Mac or PC.

## Linux setup

Install Python 3.11 or later, uv, and FFmpeg with V4L2 support. On Debian or
Ubuntu, install the runtime libraries with:

```sh
sudo apt install ffmpeg libegl1 libopengl0 libxcb-cursor0 libxkbcommon-x11-0
uv sync --extra viewer
uv run kvmuse-viewer
```

The Qt viewer provides live HDMI video, keyboard and mouse control, and the
local MCP bridge. For video only, use `uv run kvmuse-viewer --no-connect`.
For MCP without the viewer, run `uv run kvmuse-mcp`.

Your user needs access to the capture camera (`/dev/video*`) and serial device
(`/dev/ttyUSB*`). On Debian and Ubuntu, add your user to `video` and `dialout`
with `sudo usermod -aG video,dialout "$USER"`, then log out and back in.
Other distributions can use a different serial access group. Use `--port
/dev/ttyUSB0` to select a serial device explicitly. Close other camera apps.
Capture uses V4L2 MJPEG at 30 fps, trying 1920×1080 then 1280×720.
The bridge discovery file is `~/.kvmuse/bridge.json`, readable only by your user.
Desktop shortcuts can be intercepted by the window manager or compositor.

## Windows setup (PowerShell)

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and a
[Windows FFmpeg build](https://ffmpeg.org/download.html#build-windows) with DirectShow
support. Put both executables on PATH, open a new PowerShell window, and check:

```powershell
uv --version
ffmpeg -hide_banner -devices
```

The FFmpeg device list must contain `dshow`. From this repository, install either
the MCP server alone or the server plus desktop Viewer:

```powershell
# MCP server only (no Qt required)
uv sync --python 3.13

# Server and desktop Viewer
uv sync --python 3.13 --extra viewer
uv run --extra viewer kvmuse-viewer
```

Connect the Openterface host USB cable and the target HDMI cable. The Viewer
selects one matching camera and serial device automatically. It tries 1080p30,
then 720p30. Close other camera/KVM apps before starting. To select a serial port:

```powershell
uv run python -m kvmuse.smoke --list
uv run --extra viewer kvmuse-viewer --port COM3
```

Use the port reported on your machine. If no port appears, check Device Manager
under Ports (COM & LPT), reconnect USB, and install the device manufacturer's
serial driver if Windows reports a missing driver. Serial communication uses 115200 baud.

If capture fails, open Windows Settings > Privacy & security > Camera (Windows 11)
or Settings > Privacy > Camera (Windows 10). Enable camera access and access for
desktop apps. Close other programs using the device. Discovery can find a camera
even when Windows blocks opening it; `screenshot` or Viewer video confirms capture.

For the MCP connection, use these fields in Intent or another stdio MCP client:

- Command: the full executable path from `(Get-Command uv).Source`.
- Arguments: `run`, `--directory`, `C:\path\to\kvmuse`, `kvmuse-mcp`.

Each argument is a separate field, including a repository path containing spaces.
Use `uv run kvmuse-mcp` to run the server directly. Its stdout is the MCP transport.

### Windows Viewer controls

Control starts OFF. Click **Take control** or click the video; the first click is
consumed. With the Viewer focused and control ON, physical keys, modifiers,
pointer movement, left/right/middle clicks, dragging, and scrolling go to the
target. Text tools still require a US target keyboard layout.

- **Release control**, **Ctrl+Alt+K**, or two **F13** presses within 0.4 seconds
  release input. Ctrl+Alt+K also takes control when it is OFF.
- Leaving the window, reconnecting, input failures, and closing release held keys
  and mouse buttons. Release cancels queued input batches; a batch already being
  sent finishes or fails before the release reports run.
- **Wake target** sends Shift and a small relative mouse movement out and back.
- **Always on top** keeps the window above other windows. **Reconnect** retries
  both video and serial after a device or access problem.
- **Agent typing** indicates MCP input. Sustained black frames show a possible
  sleep hint; black video can also mean no HDMI signal.

Windows reserves some shortcuts, including Ctrl+Alt+Delete and often Win shortcuts;
the Viewer cannot capture these reliably. Send `press_key("ctrl-alt-del")` through
MCP when needed. Remote Desktop must pass F13 through for the double-tap shortcut;
the Release control button works without it. Only keys delivered to the focused
Viewer can be forwarded; this app does not install a system-wide keyboard hook.

The Viewer shares video and serial with MCP using the authenticated loopback
bridge described below. Run only one Viewer at a time. Other direct serial clients
must be closed. Camera work runs off the UI thread, with one latest frame and a
stall timeout; serial input uses one worker with bounded queues and ACK timeouts.
An input batch that exceeds its time budget fails and releases input; do not retry
an operation blindly after an error because some input may already have arrived.

Preview without opening serial or sending input at startup:

```powershell
uv run --extra viewer kvmuse-viewer --no-connect
```

The Reconnect button can subsequently open serial. To run automated tests:

```powershell
uv run --extra viewer pytest
```

Before relying on control, use a visible, disposable text field on the target.
Check typing, modifiers, dragging, scrolling, focus-loss release, both release
shortcuts, disconnect/reconnect, and an MCP screenshot while the Viewer runs.
Automated tests use fake serial devices and do not prove visible target input.
There is no bundled Windows installer; launch through uv as shown above.

## macOS setup

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
kvm_status, and wake_display. Screenshots return PNG image content. Status reports device
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
| `wake_display` | None | Sends Shift and a one-pixel mouse wiggle |
| `kvm_status` | None | Reports serial presence and capture discovery |

## Hardware smoke sequence

This sequence requires an unlocked macOS target with Command-Space assigned to Spotlight,
even when the host runs Windows. It is not a Windows-target test.
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

The app uses one serial queue and a shared latest-frame buffer. The agent bridge is included. Sam must check video, input, and the escape hotkey on hardware.

Viewer control through Remote Desktop: click the video or **Take control** to
start. The first video click is not sent to the target. Use **Release control**
to stop. Two F13 presses within 0.4 seconds also release control; F13 is reserved
while control is on. The original hotkey and release on focus loss still work.
Remote Desktop must pass F13 through for that shortcut; the buttons need no shortcut.
**Wake target** sends Shift press/release and a one-unit relative mouse move out
and back. A nearly black video for two seconds shows a possible-sleep hint.
A black image can also mean that the target has no video output.

### Agent bridge

While KVM Viewer runs, the MCP tools use its camera and serial connection.
The Viewer listens only on `127.0.0.1`, on a random port. Discovery data and a
random bearer token are stored in `~/.kvmuse/bridge.json` with mode `0600` on macOS.
The Windows Viewer uses `%USERPROFILE%\.kvmuse\bridge.json` and restricts directory
and file access to the current Windows user. Neither Viewer exposes the bridge
outside the local machine. The Windows Viewer removes its own discovery file on exit.
All endpoints require this token. Do not share the file.

`kvm_status` reports `path: bridge` or `path: direct`. Direct access is used only
when discovery is missing or the status endpoint does not answer. A failed
bridge operation returns an MCP error; it is never repeated through direct access.
Agent input works with Viewer control OFF and uses the same serial queue as
manual input. The Viewer shows “Agent typing” during agent input.

`screenshot` returns the latest PNG and adds a sleep hint for a nearly black
frame. `wake_display` sends Shift down/up and a one-pixel mouse wiggle. Wait
briefly after waking, then capture again. A black frame can also mean no HDMI signal.

Bridge API: `GET /status`, `GET /frame?max_width=1280`, `POST /wake`, and
`POST /keys`, `/text`, `/mouse`. The `/keys` and `/mouse` bodies contain `reports`, an array of
CH9329 command-plus-payload byte arrays. The Python client encodes named keys,
US-layout text, and mouse operations before sending a complete batch. The Viewer
validates report lengths and ranges and executes each batch without interleaving
manual reports. No serial device is opened by the Python bridge client.

Viewer builds select the first Apple Development signing identity by SHA-1; set `KVMUSE_SIGN_IDENTITY` to another identity SHA-1 hash to override it (ad-hoc fallback repeats the Camera prompt).

The `/text` body uses `keyboard_base64`: base64 of eight-byte keyboard reports. The body limit is derived from 8193 reports (4096 presses, 4096 releases, one final release), base64 expansion, and 128 bytes of JSON overhead. Shift is included in each press report.
