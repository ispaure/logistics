"""Prepare a TestFlight build, then explicitly choose whether to upload it."""
import argparse
from datetime import datetime
import os
import json
from pathlib import Path
import subprocess
import sys

from .deployment_confirmation import gui_input

ROOT = Path(__file__).resolve().parents[1]


def next_build(root=ROOT):
    existing = [int(path.name) for path in (root / 'build/testflight').glob('*')
                if path.name.isdigit()]
    from build_manager.versions import next_number
    history = Path(os.environ.get('LOGISTICS_BUILD_HISTORY', root / 'build')) / 'testflight'
    existing.extend(int(path.name) for path in history.glob('*') if path.name.isdigit())
    number = next_number(root / '.tools/build-manager/ios-build.json', existing=existing,
                         minimum=int(datetime.now().strftime('%Y%m%d')) * 10 + 1)
    if number > 999999999:
        raise ValueError('No automatic nine-digit build number is available.')
    return str(number)


def reserve_build(value=None):
    from build_manager.versions import reserve_number
    history = Path(os.environ.get('LOGISTICS_BUILD_HISTORY', ROOT / 'build')) / 'testflight'
    existing = [int(path.name) for path in history.glob('*') if path.name.isdigit()]
    existing.extend(int(path.name) for path in (ROOT / 'build/testflight').glob('*') if path.name.isdigit())
    return str(reserve_number(ROOT / '.tools/build-manager/ios-build.json', existing=existing,
        minimum=int(datetime.now().strftime('%Y%m%d')) * 10 + 1, maximum=999999999, override=value))


def deploy(build, *, ask=input, prepare_only=False, archive_arguments=()):
    if not build.isdigit() or not 0 < int(build) <= 999999999:
        raise ValueError('Use a positive build number of at most nine digits.')
    command = [sys.executable, '-m', 'mobile_build.deployment.testflight_tools']
    for step in ('plan', 'archive', 'export'):
        extra = list(archive_arguments) if step == 'archive' else []
        subprocess.run([*command, step, '--build-number', build, *extra], cwd=ROOT.parent, check=True)
    print('\nVerified build ' + build + ': ' + str(ROOT / 'build/testflight' / build / 'export'))
    if os.environ.get('LOGISTICS_MANAGER_ARTIFACT_REPORT'):
        from .manager_settings import record_prepared_artifact
        from .testflight_external import settings
        record = json.loads((ROOT / 'build/testflight' / build / 'release.json').read_text())
        verified = json.loads((ROOT / 'build/testflight' / build / 'export-verified.json').read_text())
        record_prepared_artifact(dict(provider='TestFlight', release=record, verified=verified,
                                      destination=settings(),
                                      workspace=str(ROOT / 'build/testflight' / build)))
    if prepare_only:
        print('Build prepared and verified. Nothing uploaded or sent to testers.')
        return
    try:
        answer = ask('Upload this verified build to TestFlight and the configured tester group? [y/N] ')
    except EOFError:
        answer = ''
    if answer.strip().lower() not in ('y', 'yes'):
        print('Build prepared. Nothing uploaded. You can upload this build later with python -m mobile_build.deployment.testflight_tools.')
        return
    subprocess.run([*command, 'upload', '--build-number', build], cwd=ROOT.parent, check=True,
                   env=dict(os.environ, TESTFLIGHT_UPLOAD='1'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-number', help='Optional explicit unique, increasing build number')
    parser.add_argument('--prepare-only', action='store_true', help='Prepare and verify without any upload prompt')
    parser.add_argument('--profile', type=Path, help='Existing manual app provisioning profile')
    parser.add_argument('--inbox-profile', type=Path, help='Existing manual Inbox provisioning profile')
    parser.add_argument('--widget-profile', type=Path, help='Existing manual widget provisioning profile')
    parser.add_argument('--widget-actions-profile', type=Path, help='Existing manual widget actions provisioning profile')
    parser.add_argument('--watch-profile', type=Path, help='Existing manual Watch provisioning profile')
    parser.add_argument('--watch-widget-profile', type=Path, help='Existing manual Watch widget provisioning profile')
    parser.add_argument('--gui', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        number = reserve_build(args.build_number)
        arguments = []
        if args.profile:
            arguments += ['--profile', str(args.profile)]
        if args.inbox_profile:
            arguments += ['--inbox-profile', str(args.inbox_profile)]
        if args.widget_profile:
            arguments += ['--widget-profile', str(args.widget_profile)]
        if args.widget_actions_profile:
            arguments += ['--widget-actions-profile', str(args.widget_actions_profile)]
        for name in ('watch_profile', 'watch_widget_profile'):
            if getattr(args, name):
                arguments += ['--' + name.replace('_', '-'), str(getattr(args, name))]
        if args.gui:
            deploy(number, ask=gui_input, prepare_only=args.prepare_only, archive_arguments=arguments)
        else:
            deploy(number, prepare_only=args.prepare_only, archive_arguments=arguments)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('TestFlight stopped: ' + str(error), file=sys.stderr)
        print('See mobile_build/build/testflight/<build>/logs/ for build details.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
