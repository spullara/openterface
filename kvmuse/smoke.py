"""Manual hardware smoke checks."""
import argparse
from pathlib import Path
from .ch9329 import CH9329, list_devices
from .capture import CaptureError, capture_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshot', type=Path, help='Save a target screenshot as PNG')
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--port")
    parser.add_argument("--type")
    args = parser.parse_args()
    if args.list:
        print("\n".join(list_devices()) or "No Openterface serial device found.")
        return
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
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
