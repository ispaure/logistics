"""Bounded native app launch and strict test-mode UI evidence verification."""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import signal
import shutil
import subprocess
import sys
import time

PREFIX = 'LOGISTICS_NATIVE_UI_RESULT='
REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_ui_contract',
    Path(__file__).parent / 'native_tests/tests/logisticsmobile/__init__.py')
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def read_report(path):
    reports = []
    chunks = []
    for line in Path(path).read_text(errors='replace').splitlines():
        if 'LOGISTICS_NATIVE_UI_CHUNK=' in line:
            chunks.append(json.loads(line.split('LOGISTICS_NATIVE_UI_CHUNK=', 1)[1]))
        if PREFIX in line:
            reports.append(json.loads(line.split(PREFIX, 1)[1]))
    if chunks:
        if (reports or any(item.get('index') != index or item.get('count') != len(chunks)
                           or item.get('encoding') != 'base64' or not isinstance(item.get('data'), str) for index, item in enumerate(chunks))):
            raise ValueError('Incomplete or duplicate native report chunks.')
        reports.append(json.loads(base64.b64decode(''.join(item['data'] for item in chunks), validate=True)))
    if len(reports) != 1:
        raise ValueError('Expected one native app UI report.')
    return reports[0]


def verify(path, target, output, *, local_manifest=None):
    return verify_report(read_report(path), target, output, local_manifest=local_manifest)


def verify_report(report, target, output, *, local_manifest=None):
    source = report.get('source', {})
    if not isinstance(source, dict):
        raise ValueError('Invalid native app source manifest.')
    backend = 'toga_android.' if target == 'android' else 'toga_iOS.'
    expected_root = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    expected_shared = subprocess.check_output(['git', '-C', str(REPO / 'Python/commonUtils'), 'rev-parse', 'HEAD'], text=True).strip()
    if (report.get('schema') != 1 or report.get('suite') != 'logistics-native-ui'
            or report.get('success') is not True or report.get('target') != target
            or not isinstance(report.get('backend'), str) or not report['backend'].startswith(backend)
            or report.get('cases') != list(contract.CASES) or report.get('expected_cases') != list(contract.CASES)
            or report.get('error') or (local_manifest is None and source.get('dirty') is not False)
            or source.get('logistics_commit') != expected_root or source.get('commonUtils_commit') != expected_shared):
        raise ValueError('Native app UI checks failed or came from a different source/backend.')
    if local_manifest is not None:
        expected = json.loads(Path(local_manifest).read_text())
        if source != expected or len(source.get('source_sha256', '')) != 64:
            raise ValueError('Local native report came from a different staged snapshot.')
    Path(output).write_text(json.dumps(report, indent=2) + '\n')
    return report



def simulator_report(device, started_ns, *, diagnostics=None):
    """Read only a result written during this run, never a previous success."""
    result = subprocess.run(['xcrun', 'simctl', 'get_app_container', device,
        'io.github.ispaure.logisticsmobile', 'data'], capture_output=True, text=True,
        timeout=30, check=False)
    if result.returncode:
        return None
    path = Path(result.stdout.strip()) / 'Library/Caches/logistics-native-ui-result.json'
    if diagnostics is not None:
        diagnostics = Path(diagnostics)
        diagnostics.mkdir(exist_ok=True)
        # Fatal native crashes cannot write the final JSON. Capture their stack
        # before returning, and never leave the previous device's result here.
        for name in ('cached.json', 'error.txt', 'fault.log'):
            target = diagnostics / ('ios-native-ui-' + name)
            target.unlink(missing_ok=True)
            source = path.with_name('logistics-native-ui-' + name) if name != 'cached.json' else path
            if source.is_file() and source.stat().st_mtime_ns >= started_ns:
                shutil.copyfile(source, target)
    if not path.is_file() or path.stat().st_mtime_ns < started_ns:
        return None
    raw = path.read_text()
    return json.loads(raw)


def run(target, device, *, local=False, require_independent_windows=False, require_duo=False, no_update=False):
    if no_update:
        if target != 'ios':
            raise ValueError('Shared test application reuse is supported only for iOS.')
        verify_prebuilt_ios()
    command = [sys.executable, '-m', 'briefcase', 'run', 'android' if target == 'android' else 'iOS',
               '--test', '--no-input', '--device', device]
    if no_update:
        command.append('--no-update')
    if target == 'android':
        command.extend(['--Xemulator=-no-window', '--Xemulator=-no-audio', '--Xemulator=-no-snapshot-load', '--Xemulator=-gpu',
                        '--Xemulator=swiftshader_indirect', '--shutdown-on-exit'])
    logs = Path('logs')
    logs.mkdir(exist_ok=True)
    path = logs / (target + '-native-ui.log')
    started_ns = time.time_ns()
    if target == 'ios':
        (logs / 'ios-native-ui-device.json').write_text(json.dumps(dict(
            device=device, started_ns=started_ns)) + '\n')
    # Include cold startup, installation, all native cases and the visual audit.
    # Software-rendered Android audits need the published 40-minute budget.
    # iOS also exercises the added rotation matrix; allow 30 minutes per device.
    timeout = 2400 if target == 'android' else 1800
    with path.open('w') as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise RuntimeError(f'Native app UI run exceeded {timeout // 60} minutes; see retained logs.') from None
    output = logs / (target + ('-native-ui-local.json' if local else '-native-ui.json'))
    manifest = Path('payload/source.json') if local else None
    report = None
    if target == 'ios' and code in (0, 200):
        # A complete report already proves every case and exact source. Avoid
        # depending on a responsive CoreSimulator service after app shutdown.
        # Briefcase can also lose its exit marker after the full report arrives.
        try:
            incoming = read_report(path)
        except ValueError:
            incoming = None
        if incoming is not None:
            (logs / 'ios-native-ui-stdout.json').write_text(json.dumps(incoming, indent=2) + '\n')
            transport = 'stdout'
        else:
            # The cache is atomic and fresh for this device/run; it still has
            # to satisfy the same complete case, backend and source contract.
            incoming = simulator_report(device, started_ns, diagnostics=logs)
            transport = 'simulator-file'
        if incoming is not None:
            if incoming.get('error'):
                print('Native iOS report error: ' + str(incoming['error']), flush=True)
            report = verify_report(incoming, target, output, local_manifest=manifest)
            (logs / 'ios-report-transport.json').write_text(json.dumps(dict(
                transport=transport, device=device, briefcase_exit_code=code)) + '\n')
    if report is None:
        if code:
            print(path.read_text(errors='replace')[-10000:])
            raise RuntimeError(f'Native app UI run failed ({code}); see retained logs.')
        report = verify(path, target, output, local_manifest=manifest)
    if require_independent_windows and report.get('independent_windows_tested') is not True:
        raise ValueError('This run did not verify independent system windows.')
    if require_duo:
        verify_duo_rotation(report)
    return report


def verify_prebuilt_ios():
    """Fail instead of silently rebuilding a missing or mismatched shared app."""
    project = Path('build/logisticsmobile/ios/xcode')
    app = project / 'build/Debug-iphonesimulator/Logistics Mobile.app'
    if not (project / 'briefcase.toml').is_file() or not (app / 'Logistics Mobile').is_file():
        raise ValueError('Shared iOS test application or Briefcase metadata is missing.')
    with (app / 'Info.plist').open('rb') as stream:
        info = plistlib.load(stream)
    if info.get('MainModule') != 'tests.logisticsmobile':
        raise ValueError('Shared iOS application was not built in test mode.')
    source = json.loads((app / 'app/mobile/source.json').read_text())
    expected = json.loads(Path('payload/source.json').read_text())
    root = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    shared = subprocess.check_output(['git', '-C', str(REPO / 'Python/commonUtils'), 'rev-parse', 'HEAD'], text=True).strip()
    if (source != expected or source.get('dirty') is not False
            or source.get('logistics_commit') != root or source.get('commonUtils_commit') != shared):
        raise ValueError('Shared iOS test application came from a different source.')



def verify_duo_rotation(report):
    """Require native Duo observations and both rotation directions per panel."""
    review = report.get('ui_review') or {}
    samples = review.get('rotation_samples', [])
    required = {'portrait', 'landscape-left', 'landscape-right'}
    panels = {row.get('panel') for row in samples}
    if (not {'workspaces', 'folder', 'comic', 'documentation'} <= panels
            or not all(row.get('pose', {}).get('duo_capable') for row in samples)
            or any(not required <= {row.get('orientation') for row in samples if row.get('panel') == panel}
                   for panel in panels)):
        raise ValueError('This run did not verify the native iPhone Duo rotation matrix.')


def select_ios_device(data, *, ipad=False, duo=False):
    """Select a distinct hardware family, including renamed simulator instances."""
    def matches(device):
        identity = device.get('deviceTypeIdentifier', '') or device['name']
        if duo:
            return 'iPhone-Duo' in identity or 'iPhone Duo' in identity
        if ipad:
            return 'iPad' in identity
        return 'iPhone' in identity and 'Duo' not in identity
    devices = [d for runtime, items in data['devices'].items() if '.iOS-' in runtime
               for d in items if d.get('isAvailable') and matches(d)]
    if not devices:
        raise RuntimeError('No available ' + ('iPhone Duo (iOS 27.1+)' if duo else 'iPad' if ipad else 'ordinary iPhone') + ' Simulator device.')
    return sorted(devices, key=lambda d: d['state'] != 'Booted')[0]['udid']


def ios_device(*, ipad=False, duo=False):
    data = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json']))
    return select_ios_device(data, ipad=ipad, duo=duo)


def ios_diagnostics():
    """Preserve startup stderr and crash reports after a failed native gate."""
    logs = Path('logs').resolve()
    logs.mkdir(exist_ok=True)
    receipt = logs / 'ios-native-ui-device.json'
    recorded = json.loads(receipt.read_text()) if receipt.is_file() else {}
    device = recorded.get('device') or ios_device()
    if recorded.get('started_ns'):
        simulator_report(device, recorded['started_ns'], diagnostics=logs)
    command = ['xcrun', 'simctl', 'spawn', device, 'log', 'show', '--last', '10m',
               '--style', 'compact', '--predicate',
               'process == "Logistics Mobile" OR eventMessage CONTAINS "io.github.ispaure.logisticsmobile"']
    with (logs / 'ios-system.log').open('w') as output:
        subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=60, check=False)
    # This diagnostic replay never counts as a passing test. Native constructor
    # failures can write directly to fd 2 before Python's OS logging exists.
    try:
        result = subprocess.run(['xcrun', 'simctl', 'launch',
            '--stdout=' + str(logs / 'ios-launch.stdout'), '--stderr=' + str(logs / 'ios-launch.stderr'),
            device, 'io.github.ispaure.logisticsmobile'], capture_output=True, timeout=60)
        (logs / 'ios-launch.result').write_bytes(result.stdout + result.stderr)
    except subprocess.TimeoutExpired:
        (logs / 'ios-launch.result').write_text('Diagnostic launch timed out.')
    for source in (Path.home() / 'Library/Logs/DiagnosticReports').glob('*.ips'):
        if source.stat().st_size <= 10 * 1024 * 1024:
            header = source.read_text(errors='replace')[:8192]
            if 'logistics' in header.lower():
                shutil.copyfile(source, logs / source.name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'ios-device', 'ios-ipad', 'ios-duo', 'ios-diagnostics'))
    parser.add_argument('target', choices=('android', 'ios'), nargs='?')
    parser.add_argument('--device')
    parser.add_argument('--local', action='store_true', help='Verify this exact local payload; not release evidence')
    parser.add_argument('--require-independent-windows', action='store_true')
    parser.add_argument('--require-duo', action='store_true')
    parser.add_argument('--no-update', action='store_true', help='Reuse an already built test application')
    args = parser.parse_args()
    if args.command == 'ios-device':
        print(ios_device())
    elif args.command == 'ios-ipad':
        print(ios_device(ipad=True))
    elif args.command == 'ios-duo':
        print(ios_device(duo=True))
    elif args.command == 'ios-diagnostics':
        ios_diagnostics()
    else:
        if not args.target or not args.device:
            parser.error('run requires a target and --device')
        run(args.target, args.device, local=args.local, require_independent_windows=args.require_independent_windows,
            require_duo=args.require_duo, no_update=args.no_update)
