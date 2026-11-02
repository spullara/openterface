"""Conservative Mac hardware smoke sequence; run with python -m kvmuse.e2e."""
import argparse
from pathlib import Path
import time
import tempfile

from .capture import capture_frame, check_permission
from .server import press_key, type_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial-only', action='store_true')
    parser.add_argument('--output', type=Path, default=Path(tempfile.gettempdir()) / 'kvmuse-e2e')
    args = parser.parse_args()
    if not args.serial_only:
        check_permission()
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / 'before.png').write_bytes(capture_frame())
    try:
        press_key('space', ['cmd'])
        time.sleep(1)
        type_text('kvmuse test')
        print('Keyboard press/release reports acknowledged by CH9329.', flush=True)
        time.sleep(1)
        if not args.serial_only:
            (args.output / 'after.png').write_bytes(capture_frame())
            print(f'Inspect {args.output}/before.png and after.png for visible text.')
    finally:
        press_key('esc')
        print('Escape acknowledged. No Enter key sent.', flush=True)
    if args.serial_only:
        print('Serial proof only: target focus and visible text are not verified.')


if __name__ == '__main__':
    main()
