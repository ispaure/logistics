"""Prepare a TestFlight build, then explicitly choose whether to upload it."""
import argparse
from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys

try:
    from .deployment_confirmation import gui_input
except ImportError:
    from deployment_confirmation import gui_input

ROOT = Path(__file__).resolve().parent


def next_build(root=ROOT):
    existing = [int(path.name) for path in (root / 'build/testflight').glob('*')
                if path.name.isdigit()]
    number = max(int(datetime.now().strftime('%Y%m%d')) * 10 + 1, max(existing, default=0) + 1)
    if number > 999999999:
        raise ValueError('No automatic nine-digit build number is available.')
    return str(number)


def deploy(build, *, ask=input):
    if not build.isdigit() or not 0 < int(build) <= 999999999:
        raise ValueError('Use a positive build number of at most nine digits.')
    command = [sys.executable, str(ROOT / 'testflight_tools.py')]
    for step in ('plan', 'archive', 'export'):
        subprocess.run([*command, step, '--build-number', build], check=True)
    print('\nVerified build ' + build + ': ' + str(ROOT / 'build/testflight' / build / 'export'))
    try:
        answer = ask('Upload this verified build to TestFlight and the configured tester group? [y/N] ')
    except EOFError:
        answer = ''
    if answer.strip().lower() not in ('y', 'yes'):
        print('Build prepared. Nothing uploaded. You can upload this build later with testflight_tools.py.')
        return
    subprocess.run([*command, 'upload', '--build-number', build], check=True,
                   env=dict(os.environ, TESTFLIGHT_UPLOAD='1'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-number', help='Optional explicit unique, increasing build number')
    parser.add_argument('--gui', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.gui:
            deploy(args.build_number or next_build(), ask=gui_input)
        else:
            deploy(args.build_number or next_build())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('TestFlight stopped: ' + str(error), file=sys.stderr)
        print('See Mobile/build/testflight/<build>/logs/ for build details.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
