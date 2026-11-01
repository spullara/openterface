"""User-operated macOS target power settings command."""
import argparse
import sys
import time

from .ch9329 import CH9329
from .unlock import read_password, tap, validate_password

POWER = 'sudo pmset -a displaysleep 0 sleep 0 disksleep 0'
SCREENSAVER = 'defaults -currentHost write com.apple.screensaver idleTime -int 0'
CHECK = 'pmset -g; defaults -currentHost read com.apple.screensaver idleTime'


def line(driver, text):
    driver.type_text(text)
    tap(driver, ['enter'])
    time.sleep(1)


def keep_awake(driver, password):
    validate_password(password)
    tap(driver, ['space'], 8)
    time.sleep(1)
    driver.type_text('Terminal')
    tap(driver, ['enter'])
    time.sleep(2)
    tap(driver, ['n'], 8)
    time.sleep(1)
    line(driver, 'sudo -k')
    line(driver, POWER)
    line(driver, password)
    line(driver, SCREENSAVER)
    line(driver, CHECK)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    if args.dry_run:
        print('Open Terminal: Cmd+Space, Terminal, Enter, Cmd+N')
        print('sudo -k\n' + POWER + '\n[hidden password]\n' + SCREENSAVER + '\n' + CHECK)
        return 0
    try:
        password = read_password()
        with CH9329(args.port) as driver:
            keep_awake(driver, password)
    except (Exception, KeyboardInterrupt):
        print('Keep-awake stopped. Check the target screen and serial connection.', file=sys.stderr)
        return 1
    print('Settings input sent. Check the output on the target.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
