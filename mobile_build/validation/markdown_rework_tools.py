"""Run isolated Markdown acceptance or keyboard checks on an Apple simulator."""
import argparse
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time

from ..tools import stage

REPO = Path(__file__).resolve().parents[2]
BUNDLE = 'io.github.ispaure.logisticsmarkdownqa'


def sim(*arguments, check=True):
    return subprocess.run(['xcrun', 'simctl', *arguments], check=check,
                          capture_output=True, text=True, timeout=40).stdout.strip()


def prepare(source, directory, *, native_library=None, creation=False):
    payload, app = directory / 'payload', directory / 'Markdown QA.app'
    stage(REPO, payload, allow_dirty=True)
    shutil.copytree(source, app, symlinks=True)
    for name in ('logisticsmobile', 'mobile', 'features', 'services', 'commonUtils'):
        target = app / 'app' / name
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(payload / name, target)
    shutil.copytree(REPO / 'mobile_build/native_tests/tests', app / 'app/tests', dirs_exist_ok=True)
    shutil.copyfile(payload / 'source.json', app / 'app/markdown-qa-source.json')
    (app / 'app/logisticsmobile/__main__.py').write_text(
        'import sys\nfrom pathlib import Path\n'
        "support = Path(__file__).resolve().parents[2] / 'Frameworks/MarkdownQASupport.dylib'\n"
        'if support.exists():\n import ctypes\n ctypes.CDLL(str(support))\n'
        "if '--creation' in sys.argv:\n"
        ' from tests.logisticsmobile.document_creation_probe import main\n'
        "elif '--keyboard' in sys.argv:\n"
        ' from tests.logisticsmobile.editor_keyboard_probe import main\n'
        "elif '--adaptive' in sys.argv:\n"
        ' from tests.logisticsmobile.markdown_adaptive_probe import main\nelse:\n'
        ' from tests.logisticsmobile.markdown_rework_probe import main\nmain().main_loop()\n')
    path = app / 'Info.plist'
    info = plistlib.loads(path.read_bytes())
    info.update(CFBundleIdentifier='io.github.ispaure.logisticscreationqa' if creation else BUNDLE,
                CFBundleDisplayName='Creation QA' if creation else 'Markdown QA', MainModule='logisticsmobile')
    path.write_bytes(plistlib.dumps(info))
    if native_library is not None:
        shutil.copyfile(native_library, app / 'Frameworks/MarkdownQASupport.dylib')
    subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app)],
                   check=True, capture_output=True, timeout=40)
    return app


def run(source, device, output, *, keyboard=False, adaptive=False, creation=False, timeout=240, native_library=None):
    if output.exists():
        raise ValueError('Choose a fresh evidence output directory.')
    devices = json.loads(sim('list', 'devices', 'available', '--json'))['devices']
    if not any(row['udid'] == device for rows in devices.values() for row in rows):
        raise ValueError('Choose an available Apple simulator UUID.')
    output.mkdir(parents=True)
    cache = None
    installed = False
    console = None
    bundle = 'io.github.ispaure.logisticscreationqa' if creation else BUNDLE
    folder = ('document-creation-evidence' if creation else 'editor-keyboard-evidence' if keyboard else
              'markdown-adaptive-evidence' if adaptive else 'markdown-rework-evidence')
    with TemporaryDirectory(prefix='logistics-markdown-qa-') as build:
        app = prepare(source, Path(build), native_library=native_library, creation=creation)
        shutil.copyfile(app / 'app/markdown-qa-source.json', output / 'source.json')
        try:
            sim('terminate', device, bundle, check=False)
            sim('install', device, str(app))
            installed = True
            cache = Path(sim('get_app_container', device, bundle, 'data')) / 'Library/Caches' / folder
            report = cache / 'result.json'
            report.unlink(missing_ok=True)
            with (output / 'native-console.log').open('w') as stream:
                console = subprocess.Popen(['xcrun', 'simctl', 'launch', '--console-pty', device, bundle,
                    *(['--creation'] if creation else ['--keyboard'] if keyboard else ['--adaptive'] if adaptive else [])], stdout=stream, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if report.is_file():
                    try:
                        result = json.loads(report.read_text())
                    except json.JSONDecodeError:
                        time.sleep(.1)
                        continue
                    if not result.get('success'):
                        raise RuntimeError(result.get('error', 'Native Markdown acceptance failed.'))
                    errors = (output / 'native-console.log').read_text(errors='replace')
                    if any(marker in errors for marker in ('Error in handler:', 'Exception in callback',
                                                           'Task exception was never retrieved', 'Application startup failed')):
                        raise RuntimeError('Native callback errors; inspect native-console.log.')
                    if creation:
                        sim('io', device, 'screenshot', str(output / 'choose-location.png'))
                    return result
                if console.poll() is not None:
                    raise RuntimeError('QA application exited before producing evidence; inspect native-console.log.')
                startup = cache.parent / 'markdown-qa-python.log'
                if startup.is_file() and 'Application startup failed' in startup.read_text(errors='replace'):
                    raise RuntimeError('QA startup failed; inspect markdown-qa-python.log.')
                time.sleep(.25)
            raise TimeoutError('Native Markdown acceptance timed out; inspect retained evidence.')
        finally:
            try:
                if cache is not None and cache.exists():
                    shutil.copytree(cache, output / 'evidence', dirs_exist_ok=True)
                if cache is not None and (cache.parent / 'markdown-qa-python.log').exists():
                    shutil.copyfile(cache.parent / 'markdown-qa-python.log', output / 'markdown-qa-python.log')
            finally:
                if installed:
                    sim('terminate', device, bundle, check=False)
                    if console is not None:
                        try:
                            console.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            console.terminate()
                    sim('uninstall', device, bundle)
                    if bundle in sim('listapps', device):
                        raise RuntimeError('Temporary Markdown QA app cleanup failed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', required=True, type=Path, help='An existing Logistics simulator .app')
    parser.add_argument('--device', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--keyboard', action='store_true')
    parser.add_argument('--adaptive', action='store_true', help='Observe real window/fold/keyboard changes until a cache finish signal')
    parser.add_argument('--creation', action='store_true', help='Verify local and LocalCrypt document creation')
    parser.add_argument('--timeout', type=int, default=240)
    parser.add_argument('--native-library', type=Path, help='Optional current native helper library for an older cached simulator shell')
    args = parser.parse_args()
    if sum((args.keyboard, args.adaptive, args.creation)) > 1:
        parser.error('Choose one probe mode.')
    report = run(args.app, args.device, args.output, keyboard=args.keyboard, adaptive=args.adaptive, creation=args.creation,
                 timeout=args.timeout, native_library=args.native_library)
    print(json.dumps(dict(success=report['success'], keyboard=args.keyboard)))
