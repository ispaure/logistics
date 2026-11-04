"""One complete-suite retry for evidenced Swift pool starvation on an owned CI simulator.

Screen Time's synchronous XPC can occupy every cooperative Swift worker. WebKit's
ExtensionKit launch then cannot run, although the application's UI loop continues.
Qualification requires that exact sampled stack, a zero-process private WebView,
the current failed native report, and an unchanged prebuilt test application.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import UUID


def read(path, limit=4 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink():
        raise ValueError('Recovery evidence cannot be linked.')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Recovery evidence exceeds its bound.')
    return data


def blocked_workers(sample):
    """Count distinct Swift task workers synchronously blocked in Screen Time RPC."""
    workers = set()
    for block in re.split(r'(?=^\s+\d+ Thread_)', sample, flags=re.MULTILINE):
        thread = re.match(r'\s+\d+ Thread_(\d+)', block)
        if (thread and 'ScreenTimeWebBrowserSettings.XPCClient' in block
                and 'completeTaskWithClosure' in block
                and 'ScreenTimeSettingsServices' in block
                and 'xpc_connection_send_message_with_reply_sync' in block
                and 'mach_msg2_trap' in block):
            workers.add(int(thread[1]))
    return sorted(workers)


def stalled_view(error):
    """A failed DOM assertion or a live/unattached process is never infrastructure proof."""
    for line in error.splitlines():
        if not (line.startswith('RuntimeError: WebView did not render ')
                and "url='app-document://" in line and ', native=' in line):
            continue
        try:
            state = ast.literal_eval(line.split(', native=', 1)[1])
        except (ValueError, SyntaxError, RecursionError):
            return False
        return (isinstance(state, dict) and state.get('platform_backend') == 'toga_iOS.widgets.webview'
                and state.get('parent') is True and state.get('window') is True
                and state.get('loading') is True and state.get('progress') == .1
                and type(state.get('web_process_pid')) is int and state['web_process_pid'] == 0
                and type(state.get('provisional_process_pid')) is int and state['provisional_process_pid'] == 0)
    return False


def qualification(logs, device, started_ns, source, collect, *, cpus, expected_cases):
    """Read fresh evidence only; no repair or app launch happens during diagnosis."""
    if type(cpus) is not int or not 1 <= cpus <= 512:
        return None
    metadata = json.loads(read(logs / 'ios-native-ui-device.json'))
    if metadata.get('device') != device or metadata.get('started_ns', 0) < started_ns:
        return None
    incoming = collect(device, metadata['started_ns'], diagnostics=logs)
    if (not isinstance(incoming, dict) or incoming.get('schema') != 1
            or incoming.get('suite') != 'logistics-native-ui' or incoming.get('target') != 'ios'
            or incoming.get('backend', '').startswith('toga_iOS.') is not True
            or incoming.get('success') is not False or incoming.get('source') != source
            or incoming.get('expected_cases') != list(expected_cases)
            or incoming.get('cases') != list(expected_cases)[:len(incoming.get('cases', []))]):
        return None
    error = read(logs / 'ios-native-ui-error.txt', 64 * 1024).decode()
    if not stalled_view(error) or read(logs / 'ios-native-ui-fault.log', 1024):
        return None
    for receipt in logs.glob('ios-webview-stall-*.json'):
        row = json.loads(read(receipt, 16 * 1024))
        pid = row.get('pid')
        executable = row.get('executable', '')
        if (row.get('status') != 'sampled' or row.get('sample_exit_code') != 0
                or row.get('thread_stacks_present') is not True or type(pid) is not int
                or f'/Devices/{device}/'.lower() not in executable.lower()
                or not executable.endswith('/Logistics Mobile.app/Logistics Mobile')
                or not metadata['started_ns'] <= row.get('sent_ns', 0)
                    <= row.get('received_ns', 0) <= time.time_ns()):
            continue
        sample_path = receipt.with_suffix('.sample.txt')
        sample = read(sample_path).decode()
        workers = blocked_workers(sample)
        if f'(pid {pid})' in sample and len(workers) >= cpus:
            return dict(reason='swift-screen-time-worker-starvation', cpus=cpus,
                blocked_workers=workers, pid=pid, sample=sample_path.name,
                sample_sha256=hashlib.sha256(sample.encode()).hexdigest())
    return None


def preserve(logs, target):
    """Keep each attempt independently, including its original failed native report."""
    target.mkdir()
    hashes = {}
    total = 0
    for path in logs.iterdir():
        if not (path.name.startswith(('ios-native-ui', 'ios-webview-stall-', 'ios-webkit-live', 'ios-screen-time-rpc-'))
                or path.name == 'ios-report-transport.json') or not path.is_file():
            continue
        data = read(path, 32 * 1024 * 1024)
        total += len(data)
        if total > 128 * 1024 * 1024:
            raise ValueError('Native recovery evidence exceeds its total bound.')
        (target / path.name).write_bytes(data)
        hashes[path.name] = hashlib.sha256(data).hexdigest()
    return hashes


def process_absent(pid):
    """An uncertain or still-running first app must never be replayed."""
    result = subprocess.run(['ps', '-ww', '-p', str(pid), '-o', 'comm='],
        capture_output=True, text=True, timeout=5, check=False)
    return result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip()


def run(operation, device, *, tools, logs=Path('logs'), source_path=Path('payload/source.json')):
    """Retry once after the failed process exits; all native assertions run again."""
    logs, source_path = Path(logs), Path(source_path)
    try:
        source_before = read(source_path)
    except (OSError, ValueError):
        source_before = None  # Missing recovery evidence must not change an ordinary run.
    directory = None
    if source_before is not None:
        try:
            directory = logs / 'ios-startup-recovery' / str(UUID(device)) / hashlib.sha256(source_before).hexdigest()
        except ValueError:
            pass
    if directory is not None and directory.exists():
        raise RuntimeError('iOS startup recovery was already admitted; preserve its evidence before a new run.')
    started_ns = time.time_ns()
    try:
        return operation()
    except RuntimeError as first:
        if directory is None or not str(first).startswith('Native app UI run failed ('):
            raise
        try:
            source = json.loads(source_before)
            if read(source_path) != source_before:
                raise ValueError('Prepared native source changed.')
            tools.verify_prebuilt_ios(local=False)
            tools.verify_native_diagnostics(logs / 'ios-native-ui.log')
            proof = qualification(logs, device, started_ns, source, tools.simulator_report,
                cpus=os.cpu_count(), expected_cases=tools.contract.CASES)
            owner = json.loads(read(logs / 'ios-native-ui-owned.json', 16 * 1024))
            if (not proof or owner.get('device') != device or owner.get('removed')
                    or not re.fullmatch(r'Logistics Native Gate [a-f0-9]{32}', owner.get('name', ''))):
                raise ValueError('No current owned simulator starvation proof.')
            from build_manager.apple_simulators import AppleSimulators
            observed = AppleSimulators().matching(device, owner['name'])
            if observed is None or observed.get('state') != 'Booted':
                raise ValueError('Recorded owned simulator is missing or no longer booted.')
            if not process_absent(proof['pid']):
                raise ValueError('The first native process has not been proven stopped.')
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError, RecursionError):
            raise first
        try:
            directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            raise RuntimeError('iOS startup recovery was already admitted; preserve its evidence before a new run.') from first
        journal = dict(status='admitted', device=device, source=source,
            qualification=proof, first_error=str(first), started_ns=started_ns)
        def save():
            temporary = directory / 'recovery.tmp'
            temporary.write_text(json.dumps(journal, indent=2) + '\n')
            temporary.replace(directory / 'recovery.json')
        save()
        journal['first_attempt'] = preserve(logs, directory / 'attempt-1')
        save()
        # Old sampler receipts must not suppress sampling if a PID is reused.
        for path in logs.glob('ios-webview-stall-*'):
            if path.name in journal['first_attempt']:
                path.unlink()
        print('Confirmed owned Simulator Swift worker starvation; preserved first attempt at '
              + str(directory) + '. Repeating the complete native suite once on the warmed simulator.', flush=True)
        try:
            if read(source_path) != source_before:
                raise ValueError('Prepared source changed before native recovery.')
            result = operation()
        except BaseException as error:
            journal['status'] = 'failed'
            journal['second_error'] = str(error)
            save()
            raise
        journal['second_attempt'] = preserve(logs, directory / 'attempt-2')
        journal['status'] = 'passed'
        save()
        return result
