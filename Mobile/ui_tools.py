"""Bounded native app launch and strict test-mode UI evidence verification."""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import time

PREFIX = 'LOGISTICS_NATIVE_UI_RESULT='
REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_ui_contract',
    Path(__file__).parent / 'native_tests/tests/logisticsmobile/__init__.py')
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def verify(path, target, output, *, local_manifest=None):
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
    return verify_report(reports[0], target, output, local_manifest=local_manifest)


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



def simulator_report(device, started_ns):
    """Read only a result written during this run, never a previous success."""
    result = subprocess.run(['xcrun', 'simctl', 'get_app_container', device,
        'io.github.ispaure.logisticsmobile', 'data'], capture_output=True, text=True,
        timeout=30, check=False)
    if result.returncode:
        return None
    path = Path(result.stdout.strip()) / 'Library/Caches/logistics-native-ui-result.json'
    if not path.is_file() or path.stat().st_mtime_ns < started_ns:
        return None
    return json.loads(path.read_text())


def run(target, device, *, local=False, require_independent_windows=False):
    command = ['briefcase', 'run', 'android' if target == 'android' else 'iOS',
               '--test', '--no-input', '--device', device]
    if target == 'android':
        command.extend(['--Xemulator=-no-window', '--Xemulator=-no-audio', '--Xemulator=-no-snapshot-load', '--Xemulator=-gpu',
                        '--Xemulator=swiftshader_indirect', '--shutdown-on-exit'])
    logs = Path('logs')
    logs.mkdir(exist_ok=True)
    path = logs / (target + '-native-ui.log')
    started_ns = time.time_ns()
    # Include cold startup, installation, all native cases and the visual audit.
    # Hosted Android software rendering can finish the 32 core cases but still
    # exceed 15 minutes in the audit. Keep both platforms bounded at 25 minutes.
    timeout = 1500
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
    # Briefcase returns 200 when Apple's log stream closes before its exit
    # marker, even after every native test passed. The cache result is written
    # atomically before exit and must pass the same complete source contract.
    cached = simulator_report(device, started_ns) if target == 'ios' and code in (0, 200) else None
    output = logs / (target + ('-native-ui-local.json' if local else '-native-ui.json'))
    manifest = Path('payload/source.json') if local else None
    if cached is not None:
        report = verify_report(cached, target, output, local_manifest=manifest)
        (logs / 'ios-report-transport.json').write_text(json.dumps(dict(
            transport='simulator-file', device=device, briefcase_exit_code=code)) + '\n')
    else:
        if code:
            print(path.read_text(errors='replace')[-10000:])
            raise RuntimeError(f'Native app UI run failed ({code}); see retained logs.')
        report = verify(path, target, output, local_manifest=manifest)
    if require_independent_windows and report.get('independent_windows_tested') is not True:
        raise ValueError('This run did not verify independent system windows.')
    return report


def ios_device(*, ipad=False):
    data = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json']))
    devices = [d for runtime, items in data['devices'].items() if '.iOS-' in runtime
               for d in items if d.get('isAvailable') and d['name'].startswith('iPad' if ipad else 'iPhone')]
    if not devices:
        raise RuntimeError('No available requested iOS Simulator device.')
    return sorted(devices, key=lambda d: d['state'] != 'Booted')[0]['udid']


def ios_diagnostics():
    """Preserve startup stderr and crash reports after a failed native gate."""
    logs = Path('logs').resolve()
    logs.mkdir(exist_ok=True)
    device = ios_device()
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
    parser.add_argument('command', choices=('run', 'ios-device', 'ios-ipad', 'ios-diagnostics'))
    parser.add_argument('target', choices=('android', 'ios'), nargs='?')
    parser.add_argument('--device')
    parser.add_argument('--local', action='store_true', help='Verify this exact local payload; not release evidence')
    parser.add_argument('--require-independent-windows', action='store_true')
    args = parser.parse_args()
    if args.command == 'ios-device':
        print(ios_device())
    elif args.command == 'ios-ipad':
        print(ios_device(ipad=True))
    elif args.command == 'ios-diagnostics':
        ios_diagnostics()
    else:
        if not args.target or not args.device:
            parser.error('run requires a target and --device')
        run(args.target, args.device, local=args.local, require_independent_windows=args.require_independent_windows)
