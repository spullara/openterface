"""Manual hardware smoke checks."""
import argparse
from pathlib import Path
from .capture import CaptureError, capture_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshot', type=Path, help='Save a target screenshot as PNG')
    args = parser.parse_args()
    if args.screenshot:
        try:
            args.screenshot.write_bytes(capture_frame())
        except (CaptureError, OSError) as exc:
            parser.exit(1, f'{exc}\n')
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
