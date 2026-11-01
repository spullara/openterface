"""User-operated unlock command. Never supply passwords through agents."""
import argparse
import getpass
import sys
import time
import warnings

from .ch9329 import CH9329
from .hid_keys import text_keys


def read_password():
    # Do not permit getpass to fall back to echoed stdin.
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        password = getpass.getpass('Target password: ')
    validate_password(password)
    return password


def validate_password(password):
    if not password or any(ord(c) < 32 or ord(c) == 127 for c in password):
        raise ValueError('Password must contain only printable US-layout characters.')
    try:
        text_keys(password)
    except ValueError:
        raise ValueError('Password contains an unsupported US-layout character.') from None


def tap(driver, keys, modifiers=0):
    try:
        driver.key_press(keys, modifiers)
    finally:
        driver.key_release_all()


def unlock(driver, password):
    validate_password(password)
    tap(driver, [], 2)
    time.sleep(2)
    tap(driver, ['a'], 8)
    tap(driver, ['backspace'])
    driver.type_text(password)
    tap(driver, ['enter'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port')
    args = parser.parse_args(argv)
    try:
        password = read_password()
        with CH9329(args.port) as driver:
            unlock(driver, password)
    except (Exception, KeyboardInterrupt):
        print('Unlock stopped. Check the target screen and serial connection.', file=sys.stderr)
        return 1
    print('Unlock input sent. Check the target screen.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
