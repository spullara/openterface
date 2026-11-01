"""Manual hardware smoke checks."""
import argparse
import time
from pathlib import Path
from .ch9329 import CH9329, list_devices
from .capture import CaptureError, capture_frame


def mouse_demo(device):
    """Send a small relative square without clicks or wheel input."""
    for dx, dy in ((40, 0), (0, 40), (-40, 0), (0, -40)):
        device.mouse_move_rel(dx, dy)
        time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshot', type=Path, help='Save a target screenshot as PNG')
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--port")
    parser.add_argument("--type")
    parser.add_argument("--mouse-demo", action="store_true",
                        help="Move in a small relative square without clicks")
    args = parser.parse_args()
    if args.mouse_demo and args.type is not None:
        parser.error("Use --mouse-demo and --type separately.")
    if args.list:
        print("\n".join(list_devices()) or "No Openterface serial device found.")
        return
    if args.mouse_demo:
        try:
            with CH9329(args.port) as device:
                mouse_demo(device)
            print("Mouse square sent; serial acknowledgements received. No clicks sent.")
        except (OSError, RuntimeError, ValueError) as exc:
            parser.exit(1, f"KVM error: {exc}\n")
    if args.type is not None:
        try:
            with CH9329(args.port) as device:
                device.type_text(args.type)
            print("Text sent; serial acknowledgements received.")
        except (OSError, RuntimeError, ValueError) as exc:
            parser.exit(1, f"KVM error: {exc}\n")
        return
    if args.screenshot:
        try:
            args.screenshot.write_bytes(capture_frame())
        except (CaptureError, OSError) as exc:
            parser.exit(1, f'{exc}\n')
    elif not args.mouse_demo:
        parser.print_help()


if __name__ == '__main__':
    main()
