"""Windows KVM Viewer. Install with: uv sync --extra viewer."""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', help='Explicit serial COM port, for example COM3')
    parser.add_argument('--no-connect', action='store_true', help='Preview video without opening serial or sending input')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.exit(1, 'This Viewer runs on Windows. On macOS use the Swift Viewer in viewer/.\n')
    try:
        from .viewer_ui import run
    except ImportError as exc:
        parser.exit(1, f'Viewer dependencies are missing. Run: uv sync --extra viewer\n{exc}\n')
    return run(args.port, args.no_connect)


if __name__ == '__main__':
    raise SystemExit(main())
