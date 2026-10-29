"""Run the native toolbar audit in an owned scratch build and simulator."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time
from uuid import uuid4

from build_manager.apple_simulators import AppleSimulators
from logistics_build.build_retention import scratch
from .duo_pose_tools import prepare, REPO

BUNDLE = 'io.github.ispaure.logisticsconventionsqa'


def run(source, output, *, family='iPhone Duo', timeout=240, device=None, sweep=False,
        duoctl=None, pose=None, extended=False, appearance=None, content_size=None,
        extended_only=False, reader_space=False):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    client = AppleSimulators()
    runtime, model = next((runtime, row['deviceTypeIdentifier'])
                          for runtime, rows in client.devices()['devices'].items()
                          for row in rows if row.get('isAvailable') and row['name'] == family)
    name = 'Build Manager Toolbar QA ' + uuid4().hex
    owned = device is None
    cache, installed = None, False
    with scratch(REPO) as workspace:
        app = prepare(source, workspace / 'build')
        entrypoint = (
            ('from tests.logisticsmobile.reader_space_probe import ReaderSpaceProbe\n'
             f'ReaderSpaceProbe("Reader Layout QA", "{BUNDLE}").main_loop()\n') if reader_space else
            'from tests.logisticsmobile.toolbar_conventions_probe import main\nmain().main_loop()\n')
        for package in ('logisticsmobile', 'tests/logisticsmobile'):
            (app / 'app' / package / '__main__.py').write_text(entrypoint)
            for bytecode in (app / 'app' / package / '__pycache__').glob('__main__*.pyc'):
                bytecode.unlink()
        info = app / 'Info.plist'
        value = plistlib.loads(info.read_bytes())
        (output / 'native-build.json').write_text(json.dumps(dict(
            sdk=value.get('DTSDKName'), minimum_os=value.get('MinimumOSVersion'),
            runtime=runtime, device_type=model, restaged_native_shell=True), indent=2))
        value['CFBundleIdentifier'] = BUNDLE
        info.write_bytes(plistlib.dumps(value))
        # This panel audit does not launch production app extensions. Their
        # containing-app identifiers must not leak into the disposable QA copy.
        for directory in ('PlugIns', 'Extensions'):
            shutil.rmtree(app / directory, ignore_errors=True)
        subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app)], check=True,
                       capture_output=True)
        shutil.copyfile(app / 'app/fold-source.json', output / 'source.json')
        try:
            if owned:
                device = client.create(name, model, runtime)
            (output / 'lease.json').write_text(json.dumps(dict(device=device, name=name)))
            if owned:
                client.boot(device)
            if appearance is not None or content_size is not None:
                if not owned:
                    raise ValueError('Accessibility/appearance overrides require an owned simulator.')
                if appearance is not None:
                    client.invoke('ui', device, 'appearance', appearance)
                if content_size is not None:
                    client.invoke('ui', device, 'content_size', content_size)
            if pose is not None:
                if duoctl is None or not owned or 'Duo' not in family:
                    raise ValueError('Automated poses require an explicit simulator tool and an owned Duo.')
                tool = [sys.executable, str(duoctl), '-d', device]
                for attempt in range(3):
                    try:
                        subprocess.run([*tool, 'hinge', str({'closed': 0, 'partial': 127, 'open': 180}[pose])],
                                       check=True, timeout=60)
                        break
                    except subprocess.CalledProcessError:
                        if attempt == 2:
                            raise
                        time.sleep(1)  # A fresh boot can publish displays before HID is ready.
                state = subprocess.check_output([*tool, 'state'], text=True, timeout=30)
                (output / 'simulator-pose.json').write_text(state)
            client.invoke('install', device, str(app))
            installed = True
            cache = Path(client.invoke('get_app_container', device, BUNDLE, 'data')) / 'Library/Caches/toolbar-qa'
            if reader_space:
                cache = cache.parent
            arguments = [flag for flag, enabled in (('--sweep', sweep), ('--extended', extended or extended_only),
                         ('--extended-only', extended_only)) if enabled]
            client.invoke('launch', device, BUNDLE, *arguments)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                result = cache / ('reader-space-result.json' if reader_space else 'result.json')
                if result.exists():
                    report = json.loads(result.read_text())
                    if not report['success']:
                        raise RuntimeError(report.get('error', 'Toolbar audit failed'))
                    print(json.dumps(dict(success=True, screens=len(report.get('screens', [])), device=device)), flush=True)
                    return report
                time.sleep(.5)
            raise TimeoutError('Native toolbar audit timed out')
        finally:
            try:
                if cache is not None and cache.exists():
                    if reader_space:
                        (output / 'evidence').mkdir(exist_ok=True)
                        for artifact_name in ('reader-space.png', 'reader-space-result.json'):
                            if (cache / artifact_name).exists():
                                shutil.copyfile(cache / artifact_name, output / 'evidence' / artifact_name)
                    else:
                        shutil.copytree(cache, output / 'evidence', dirs_exist_ok=True)
            finally:
                if device is not None:
                    if owned:
                        client.remove(device, name)
                    elif installed:
                        try:
                            client.invoke('terminate', device, BUNDLE)
                        except RuntimeError:
                            pass  # An already exited QA app still needs uninstalling.
                        client.invoke('uninstall', device, BUNDLE)
                        if BUNDLE in client.invoke('listapps', device):
                            raise RuntimeError('QA app cleanup failed: ' + BUNDLE)
                    (output / 'cleanup.json').write_text(json.dumps(dict(device=device,
                        simulator_removed=owned, qa_app_removed=True)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--family', default='iPhone Duo')
    parser.add_argument('--timeout', type=int, default=240)
    parser.add_argument('--device', help='Existing booted simulator; remove only the QA app afterward')
    parser.add_argument('--sweep', action='store_true', help='Rotate each panel through both landscape directions and back')
    parser.add_argument('--duoctl', type=Path, help='Reviewed external simulator-only tool; never bundled in the app')
    parser.add_argument('--pose', choices=('closed', 'partial', 'open'))
    parser.add_argument('--extended', action='store_true', help='Also audit forms, settings categories, paired documents and notebooks')
    parser.add_argument('--appearance', choices=('light', 'dark'))
    parser.add_argument('--content-size', help='Native simctl content-size category, on owned simulators only')
    parser.add_argument('--extended-only', action='store_true', help='Run only the additional panel inventory')
    parser.add_argument('--reader-space', action='store_true', help='Check the portrait comic title and footer layout')
    args = parser.parse_args()
    if not os.environ.get('DEVELOPER_DIR'):
        from ..select_ios_sdk import choose, installed
        os.environ['DEVELOPER_DIR'] = choose(installed())[0]
    run(args.app, args.output, family=args.family, timeout=args.timeout, device=args.device,
        sweep=args.sweep, duoctl=args.duoctl, pose=args.pose, extended=args.extended,
        appearance=args.appearance, content_size=args.content_size,
        extended_only=args.extended_only, reader_space=args.reader_space)
