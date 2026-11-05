"""Bounded native app launch and strict test-mode UI evidence verification."""
import argparse
import base64
import importlib.util
import io
import hashlib
import tarfile
import zipfile
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import stat
import shutil
import subprocess
import sys
import time
from threading import Event, Thread, Timer

PREFIX = 'LOGISTICS_NATIVE_UI_RESULT='
REPO = Path(__file__).resolve().parents[2]
# Direct CI script execution does not inherit the application's source path.
# The pinned external manager imports commonUtils from its consumer checkout.
sys.path.insert(0, str(REPO / 'Python'))
sys.path.insert(0, str(REPO))
from commonUtils.runtime.diagnostics import Severity, log
spec = importlib.util.spec_from_file_location('native_ui_contract',
    Path(__file__).resolve().parents[1] / 'native_tests/tests/logisticsmobile/__init__.py')
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


def verify_native_diagnostics(path):
    markers = ('Error in handler:', 'Error in handler cleanup:',
               'Exception ignored on calling ctypes callback function:',
               'Error in async handler:', 'Error in async handler cleanup:',
               'Task exception was never retrieved', 'Task was destroyed but it is pending',
               'Exception in callback ', 'message sent to deallocated instance')
    with Path(path).open(errors='replace') as stream:
        for number, line in enumerate(stream, 1):
            if any(marker in line for marker in markers):
                raise ValueError(f'Unhandled native app error in {path}:{number}: {line.strip()[:500]}')


def validate_report_identity(report, target, *, local_manifest=None, partial=False):
    """Validate provenance and inventory, including diagnostic-only failed prefixes."""
    if not isinstance(report, dict):
        raise ValueError('Invalid native app UI report.')
    source = report.get('source', {})
    if not isinstance(source, dict):
        raise ValueError('Invalid native app source manifest.')
    backend = 'toga_android.' if target == 'android' else 'toga_iOS.'
    expected_root = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    expected_shared = subprocess.check_output(['git', '-C', str(REPO / 'Python/commonUtils'), 'rev-parse', 'HEAD'], text=True).strip()
    expected_cases = list(contract.CASES)
    cases = report.get('cases')
    valid_cases = (isinstance(cases, list) and cases == expected_cases[:len(cases)]
                   if partial else cases == expected_cases)
    if (report.get('schema') != 1 or report.get('suite') != 'logistics-native-ui'
            or report.get('target') != target
            or not isinstance(report.get('backend'), str) or not report['backend'].startswith(backend)
            or not valid_cases or report.get('expected_cases') != expected_cases
            or (partial and (report.get('success') is not False or not isinstance(report.get('error'), str)))
            or (local_manifest is None and source.get('dirty') is not False)
            or source.get('logistics_commit') != expected_root or source.get('commonUtils_commit') != expected_shared):
        raise ValueError('Native app UI checks failed or came from a different source/backend.')
    if local_manifest is not None:
        expected = json.loads(Path(local_manifest).read_text())
        if source != expected or len(source.get('source_sha256', '')) != 64:
            raise ValueError('Local native report came from a different staged snapshot.')
    return report


def verify_report(report, target, output, *, local_manifest=None):
    validate_report_identity(report, target, local_manifest=local_manifest)
    if report.get('success') is not True or report.get('error'):
        raise ValueError('Native app UI checks failed or came from a different source/backend.')
    Path(output).write_text(json.dumps(report, indent=2) + '\n')
    return report


def collect_android_report(path, code, output, *, local_manifest=None):
    """Retain a source-verified failed report without treating it as acceptance."""
    path, output = Path(path), Path(output)
    try:
        incoming = read_report(path)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise RuntimeError(f'Native app UI run failed ({code}): native report unavailable or invalid '
                           f'({type(error).__name__}); see retained log {path}.') from None
    try:
        validate_report_identity(incoming, 'android', local_manifest=local_manifest,
                                 partial=isinstance(incoming, dict) and incoming.get('success') is False)
        if incoming.get('success') is not True and incoming.get('success') is not False:
            raise ValueError('Invalid native report success state.')
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise RuntimeError(f'Native app UI run failed ({code}): native report rejected: {error}; '
                           f'see retained log {path}.') from None
    completed, expected = len(incoming['cases']), len(incoming['expected_cases'])
    detail = next((line.strip()[:600] for line in reversed(str(incoming.get('error') or '').splitlines())
                   if line.strip()), '')
    failed = code != 0 or incoming.get('success') is not True or bool(incoming.get('error'))
    if failed and not detail:
        detail = 'process failed after reporting' if incoming.get('success') is True else 'native checks failed without an exception summary'
    verified = None if failed else verify_report(incoming, 'android', output, local_manifest=local_manifest)
    (path.parent / 'android-native-ui-stdout.json').write_text(json.dumps(incoming, indent=2) + '\n')
    (path.parent / 'android-report-transport.json').write_text(json.dumps(dict(
        transport='stdout', briefcase_exit_code=code, status='failed' if failed else 'passed',
        completed_cases=completed, expected_cases=expected, error=detail), indent=2) + '\n')
    if failed:
        raise RuntimeError(f'Native app UI run failed ({code}); completed {completed}/{expected} cases: '
                           f'{detail}. See retained report {path.parent / "android-native-ui-stdout.json"}.')
    return verified



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
        for name in ('cached.json', 'error.txt', 'fault.log', 'timings.json', 'webview-counts.json', 'rotation-failure.json', 'reader-edge-timers.json'):
            target = diagnostics / ('ios-native-ui-' + name)
            target.unlink(missing_ok=True)
            source = path.with_name('logistics-native-ui-' + name) if name != 'cached.json' else path
            if source.is_file() and source.stat().st_mtime_ns >= started_ns:
                shutil.copyfile(source, target)
        target = diagnostics / 'ios-preview-diagnostics.json'
        target.unlink(missing_ok=True)
        source = path.with_name('logistics-preview-diagnostics.json')
        if source.is_file() and source.stat().st_mtime_ns >= started_ns:
            shutil.copyfile(source, target)
    if not path.is_file() or path.stat().st_mtime_ns < started_ns:
        return None
    raw = path.read_text()
    return json.loads(raw)


def linux_host_memory(proc=Path('/proc')):
    """Read public memory counters and process names, never command lines/env."""
    values = {line.split(':', 1)[0]: int(line.split()[1])
              for line in (proc / 'meminfo').read_text().splitlines()
              if line.startswith(('MemTotal:', 'MemAvailable:', 'SwapFree:'))}
    counters = dict(line.split() for line in (proc / 'vmstat').read_text().splitlines())
    processes = []
    for entry in proc.iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            status = dict(line.split(':', 1) for line in (entry / 'status').read_text().splitlines() if ':' in line)
            rss = int(status.get('VmRSS', '0').split()[0])
            processes.append(dict(pid=int(entry.name), name=status.get('Name', '').strip(), rss_kib=rss))
        except (OSError, ValueError, IndexError):
            continue  # Processes may exit between directory and status reads.
    return dict(memory_mib={key: value // 1024 for key, value in values.items()},
                oom_kill=int(counters.get('oom_kill', 0)),
                processes=sorted(processes, key=lambda row: row['rss_kib'], reverse=True)[:8])


def record_host_memory(path):
    if not (sys.platform.startswith('linux') and os.environ.get('GITHUB_ACTIONS') == 'true'):
        return
    try:
        row = dict(time=time.time(), **linux_host_memory())
        log(Severity.INFO, 'Native host memory', json.dumps(row))
        sys.stdout.flush()
        with path.with_name('native-host-memory.jsonl').open('a') as stream:
            stream.write(json.dumps(row) + '\n')
    except (OSError, ValueError, IndexError):
        pass  # Diagnostics must never change native test acceptance.


def record_android_emulator(logs):
    """Retain the configured SDK revision alongside hosted renderer diagnostics."""
    sdk = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    if not sdk:
        return
    try:
        properties = Path(sdk) / 'emulator/source.properties'
        values = {key.strip(): value.strip() for key, value in
                  (line.split('=', 1) for line in properties.read_text().splitlines() if '=' in line)}
        revision = values.get('Pkg.Revision', '').strip()
        if not revision:
            raise ValueError('Emulator revision is missing')
        row = dict(revision=revision, renderer='software')
        (logs / 'android-emulator.json').write_text(json.dumps(row) + '\n')
        log(Severity.INFO, 'Android emulator', json.dumps(row))
        sys.stdout.flush()
    except (OSError, ValueError) as error:
        log(Severity.WARNING, 'Android emulator diagnostics', str(error))


def record_ios_stall(path, row):
    """Sample only the identified test app, while its render deadline runs."""
    pid = row.get('pid')
    if sys.platform != 'darwin' or type(pid) is not int or pid <= 1:
        return
    receipt = path.with_name('ios-webview-stall-' + str(pid) + '.json')
    record = dict(pid=pid, received_ns=time.time_ns(), sent_ns=row.get('sent_ns'))
    service_capture = None
    def save(status):
        record['status'] = status
        try:
            receipt.write_text(json.dumps(record, indent=2) + '\n')
        except OSError:
            pass
    try:
        if receipt.exists():
            return
        save('received')
        process = subprocess.run(['ps', '-ww', '-p', str(pid), '-o', 'comm='],
            capture_output=True, text=True, timeout=5, check=False)
        record.update(process_exit_code=process.returncode, executable=process.stdout.strip()[:4096])
        if process.returncode:
            save('process-unavailable')
            return
        if not process.stdout.strip().endswith('/Logistics Mobile.app/Logistics Mobile'):
            save('unexpected-executable')
            return
        if path.with_name('ios-native-ui-owned.json').is_file():
            from mobile_build.validation.screen_time_rpc import capture
            def capture_services():
                try:
                    capture(path, record['executable'], pid)
                except Exception as error:
                    log(Severity.WARNING, 'Simulator service diagnostics', type(error).__name__)
            service_capture = Thread(target=capture_services, daemon=True)
            service_capture.start()
        output = path.with_name('ios-webview-stall-' + str(pid) + '.sample.txt')
        if output.exists():
            return
        # Collect stacks before costly symbol analysis. The failed native check
        # retains its app/view long enough for analysis, without extending the
        # render acceptance deadline or accepting a late result.
        result = subprocess.run(['sample', str(pid), '3', '-file', str(output)],
            capture_output=True, text=True, timeout=60, check=False)
        record.update(sample_exit_code=result.returncode, sample_stderr=result.stderr[-2000:])
        captured = output.read_text(errors='replace') if output.is_file() else ''
        has_stacks = 'Thread_' in captured or 'DispatchQueue_' in captured
        record['thread_stacks_present'] = has_stacks
        save('sampled' if result.returncode == 0 and has_stacks else
             'empty-sample' if result.returncode == 0 else 'sample-failed')
    except (OSError, subprocess.TimeoutExpired) as error:
        record['error'] = type(error).__name__ + ': ' + str(error)[:500]
        save('capture-error')  # Diagnostics never alter native acceptance.
    finally:
        if service_capture is not None:
            # Start both sides together; symbolication or an unavailable
            # service must not delay collecting the app's waiting stacks.
            service_capture.join(timeout=5)


def record_android_stall(path, row):
    """Read failure evidence only from the hosted job's single emulator."""
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        return
    sdk = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    if not sdk:
        return
    adb = Path(sdk) / 'platform-tools/adb'
    receipt = path.with_name('android-focus-stall.json')
    if receipt.exists():
        return
    record = dict(reason=row, status='received')
    try:
        devices = subprocess.run([str(adb), 'devices'], capture_output=True, timeout=5, check=True)
        online = [line.split()[0] for line in devices.stdout.decode().splitlines()[1:]
                  if len(line.split()) == 2 and line.split()[1] == 'device']
        if len(online) != 1 or not online[0].startswith('emulator-') or not online[0][9:].isdigit():
            record['status'] = 'no-single-hosted-emulator'
            return
        record.update(serial=online[0], commands={})
        deadline = time.monotonic() + 14
        for name, args in (
                ('screen.png', ['exec-out', 'screencap', '-p']),
                ('windows.txt', ['shell', 'dumpsys', 'window', 'windows']),
                ('input-method.txt', ['shell', 'dumpsys', 'input_method']),
                ('last-anr.txt', ['shell', 'dumpsys', 'activity', 'lastanr'])):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            result = subprocess.run([str(adb), '-s', online[0], *args],
                capture_output=True, timeout=min(5, remaining), check=False)
            path.with_name('android-focus-stall-' + name).write_bytes(result.stdout)
            record['commands'][name] = result.returncode
        record['status'] = ('captured' if len(record['commands']) == 4
                            and not any(record['commands'].values()) else 'partial')
    except (OSError, subprocess.SubprocessError) as error:
        record.update(status='capture-error', error=str(error)[:500])
    finally:
        receipt.write_text(json.dumps(record, indent=2) + '\n')


def _progress(path, stopped):
    """Tail checkpoints and preserve an explicitly signalled iOS stall."""
    last_memory = 0
    with path.open(errors='replace') as stream:
        while True:
            if time.monotonic() - last_memory >= 30:
                last_memory = time.monotonic()
                record_host_memory(path)
            line = stream.readline()
            if not line:
                if stopped.wait(.1):
                    return
                continue
            if path.name.startswith('ios-') and 'LOGISTICS_NATIVE_PROCESS=' in line:
                try:
                    from mobile_build.validation.ios_failure_diagnostics import record_process
                    record_process(path.parent, json.loads(line.split('LOGISTICS_NATIVE_PROCESS=', 1)[1]))
                except Exception:
                    pass  # Diagnostic observers must not stop checkpoint/RPC progress.
            elif 'LOGISTICS_NATIVE_CASE=' in line:
                log(Severity.INFO, 'Native checkpoint', line.split('LOGISTICS_NATIVE_CASE=',1)[1].strip())
            elif 'LOGISTICS_NATIVE_DETAIL=' in line:
                log(Severity.INFO, 'Native detail', line.split('LOGISTICS_NATIVE_DETAIL=',1)[1].strip())
            elif path.name.startswith('ios-') and 'LOGISTICS_NATIVE_WEBVIEW_STALL=' in line:
                try:
                    row = json.loads(line.split('LOGISTICS_NATIVE_WEBVIEW_STALL=', 1)[1])
                    record_ios_stall(path, row)
                except (ValueError, AttributeError):
                    pass
            elif path.name.startswith('android-') and 'LOGISTICS_NATIVE_ANDROID_STALL=' in line:
                try:
                    row = json.loads(line.split('LOGISTICS_NATIVE_ANDROID_STALL=', 1)[1])
                    record_android_stall(path, row)
                except (ValueError, AttributeError, OSError):
                    pass
            elif 'LOGISTICS_NATIVE_TIMING=' in line:
                try:
                    row = json.loads(line.split('LOGISTICS_NATIVE_TIMING=',1)[1])
                except ValueError:
                    continue
                if row.get('name') in {'navigation','documents','readers','scenes','chat','connections','localcrypt','ui-review','rotation-panel'}:
                    log(Severity.INFO, 'Native section', row['name']+' '+json.dumps(row.get('details',{}))+' '+str(round(row['elapsed_s'],2))+'s')
            sys.stdout.flush()


def clear_run_reports(logs, target):
    """A new device must never inherit another device's success or crash report."""
    names = [target + '-native-ui' + suffix for suffix in (
        '.json', '-local.json', '-stdout.json', '-cached.json',
        '-error.txt', '-fault.log', '-timings.json')]
    if target == 'ios':
        names.extend(('ios-report-transport.json', 'ios-native-ui-process.json',
                      'ios-original-process-diagnostics.json', 'ios-original-process.sample.txt',
                      'ios-native-ui-rotation-failure.json', 'ios-native-ui-reader-edge-timers.json'))
    for name in names:
        (logs / name).unlink(missing_ok=True)



# Only these native-suite artifacts may cross the disposable-device boundary.
NATIVE_EVIDENCE = ('pdf-edge-left.png', 'pdf-edge-right.png') + tuple(
    f'notebook-image-evidence/{provider}-{phase}{suffix}.png'
    for provider in ('Local', 'LocalCrypt')
    for phase in ('captured', 'transformed', 'arranged', 'second-page', 'cut-pasted', 'reopened')
    for suffix in ('', '-canvas')) + tuple(
    f'notebook-image-evidence/{provider}-saved.rmdoc' for provider in ('Local', 'LocalCrypt'))
EVIDENCE_FILE_LIMIT = 4 * 1024 * 1024
EVIDENCE_TOTAL_LIMIT = 32 * 1024 * 1024


def retain_native_evidence(entries, output, started_ns):
    """Validate the entire bounded stream before writing any artifact."""
    saved = {}
    total = 0
    for name, modified_ns, regular, size, read in entries:
        if (name not in NATIVE_EVIDENCE or name in saved or not regular
                or not 0 <= size <= EVIDENCE_FILE_LIMIT):
            raise ValueError('Invalid native evidence member: ' + name)
        if modified_ns < started_ns - 1_000_000_000:
            continue  # tar timestamps have one-second resolution
        total += size
        if len(saved) >= len(NATIVE_EVIDENCE) or total > EVIDENCE_TOTAL_LIMIT:
            raise ValueError('Native evidence exceeds retention bounds.')
        content = read(size + 1)
        if len(content) != size:
            raise ValueError('Truncated or oversized native evidence: ' + name)
        saved[name] = (content, modified_ns)
    output = Path(output)
    if output.is_symlink() or output.parent.is_symlink():
        raise ValueError('Native evidence destination is a symlink.')
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'manifest.json').is_symlink():
        raise ValueError('Native evidence manifest is a symlink.')
    for old in output.iterdir():
        if old.is_symlink() or not old.is_file():
            raise ValueError('Unexpected native evidence destination member.')
        if old.name == 'manifest.json' or old.name in {name.replace('/', '--') for name in NATIVE_EVIDENCE}:
            old.unlink()
        else:
            raise ValueError('Unexpected native evidence destination file.')
    manifest = []
    for name, (content, modified_ns) in saved.items():
        # Flatten the fixed allowlist; never extract archive paths or links.
        path = output / name.replace('/', '--')
        if path.is_symlink():
            raise ValueError('Native evidence destination is a symlink.')
        path.write_bytes(content)
        manifest.append(dict(name=name, file=path.name, bytes=len(content),
                             modified_ns=modified_ns, sha256=hashlib.sha256(content).hexdigest()))
    (output / 'manifest.json').write_text(json.dumps(dict(artifacts=manifest), indent=2) + '\n')
    return manifest


def retain_native_cache(cache, output, started_ns):
    cache = Path(cache)
    if cache.is_symlink():
        raise ValueError('Native cache is a symlink.')
    def entries():
        for name in NATIVE_EVIDENCE:
            path = cache / name
            if path.parent.is_symlink() or path.is_symlink():
                raise ValueError('Native evidence source is a symlink.')
            if path.exists():
                info = path.stat()
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError('Native evidence source is not a regular file.')
                with path.open('rb') as stream:
                    yield name, info.st_mtime_ns, path.is_file(), info.st_size, stream.read
    return retain_native_evidence(entries(), output, started_ns)


def retain_native_tar(stream, output, started_ns):
    def entries():
        with tarfile.open(fileobj=stream, mode='r|') as archive:
            count = 0
            for item in archive:
                count += 1
                if count > len(NATIVE_EVIDENCE) + 1:
                    raise ValueError('Too many native evidence archive members.')
                if item.isdir() and item.name.rstrip('/') == 'notebook-image-evidence':
                    continue
                if not item.isfile() or item.name not in NATIVE_EVIDENCE:
                    raise ValueError('Invalid native evidence archive member.')
                content = archive.extractfile(item)
                yield item.name, int(item.mtime * 1e9), True, item.size, content.read
    return retain_native_evidence(entries(), output, started_ns)


def collect_owned_android_evidence(emulator, record, device, started_ns, logs):
    """Require the manager's live lease; never discover or select a device."""
    if record.get('serial') != device or json.loads(emulator.marker.read_text()) != record:
        raise ValueError('Native evidence device does not match its owned lease.')
    emulator.verify(record)
    command = [str(emulator.adb), '-s', device, 'exec-out', 'run-as',
               'io.github.ispaure.logisticsmobile', 'tar', '-C', 'cache', '-cf', '-',
               'pdf-edge-left.png', 'pdf-edge-right.png', 'notebook-image-evidence']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env=emulator.environment)
    timer = Timer(30, process.kill)
    timer.start()
    try:
        result = retain_native_tar(process.stdout, Path(logs) / 'android-native-ui-evidence', started_ns)
        code = process.wait(timeout=5)
        # tar may report absent optional diagnostics, but must have a valid archive.
        if code not in (0, 1):
            raise RuntimeError('Native evidence transfer failed.')
        return result
    finally:
        timer.cancel()
        process.stdout.close()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def collect_owned_ios_evidence(device, started_ns, logs):
    lease = Path(logs) / 'ios-native-ui-owned.json'
    if not lease.exists():
        return None  # local manager must supply its explicit lease-bound callback
    owner = json.loads(lease.read_text())
    if (owner.get('device') != device or owner.get('removed')
            or not str(owner.get('name', '')).startswith('Logistics Native Gate ')):
        raise ValueError('Native evidence simulator does not match its owned lease.')
    from build_manager.apple_simulators import AppleSimulators
    if AppleSimulators().matching(device, owner['name']) is None:
        raise ValueError('Owned native evidence simulator is unavailable.')
    return collect_leased_ios_evidence(AppleSimulators(), lease, owner, device, started_ns, logs)


def collect_leased_ios_evidence(client, lease, owner, device, started_ns, logs):
    """The caller supplies its exact created lease and owning simulator client."""
    if (owner.get('device') != device or owner.get('removed')
            or json.loads(Path(lease).read_text()) != owner
            or client.matching(device, owner['name']) is None):
        raise ValueError('Native evidence simulator does not match its live lease.')
    cache = subprocess.check_output(['xcrun', 'simctl', 'get_app_container', device,
        'io.github.ispaure.logisticsmobile', 'data'], text=True, timeout=30).strip()
    if not cache:
        raise ValueError('Owned native application container is unavailable.')
    return retain_native_cache(Path(cache) / 'Library/Caches',
                               Path(logs) / 'ios-native-ui-evidence', started_ns)


def finish_native_evidence(collector, device, started_ns, logs, primary=None):
    try:
        return collector(device, started_ns, logs)
    except Exception as error:
        if primary is None:
            raise
        primary.add_note('Native evidence collection also failed: ' + repr(error))
        try:
            (Path(logs) / 'native-evidence-error.json').write_text(
                json.dumps(dict(error=repr(error))) + '\n')
        except OSError:
            pass


def run(target, device, *, local=False, require_independent_windows=False, require_duo=False, no_update=False,
        evidence_collector=None):
    def operation():
        started_ns = time.time_ns()
        primary = None
        try:
            return _run_once(target, device, local=local,
                require_independent_windows=require_independent_windows, require_duo=require_duo, no_update=no_update)
        except BaseException as error:
            primary = error
            raise
        finally:
            collector = evidence_collector or (collect_owned_ios_evidence if target == 'ios' else None)
            if collector is not None:
                finish_native_evidence(collector, device, started_ns, Path('logs'), primary)
    if target == 'ios' and no_update and not local and os.environ.get('GITHUB_ACTIONS') == 'true':
        from mobile_build.validation.ios_startup_recovery import run as recover_startup
        return recover_startup(operation, device, tools=sys.modules[__name__])
    return operation()


def _run_once(target, device, *, local=False, require_independent_windows=False, require_duo=False, no_update=False):
    from logistics_build.test_structure import inventory
    inventory(REPO)
    if no_update:
        if target == 'ios':
            verify_prebuilt_ios(local=local)
        elif target == 'android':
            verify_prebuilt_android(local=local)
        else:
            raise ValueError('Unsupported cached native test target.')
    command = [sys.executable, '-u', '-m', 'briefcase', 'run', 'android' if target == 'android' else 'iOS',
               '--test', '--no-input', '--device', device]
    if no_update:
        command.append('--no-update')
    if target == 'android' and not local:
        command.extend(['--Xemulator=-no-window', '--Xemulator=-no-audio', '--Xemulator=-no-snapshot-load', '--Xemulator=-gpu',
                        '--Xemulator=software', '--shutdown-on-exit'])
    logs = Path('logs')
    logs.mkdir(exist_ok=True)
    clear_run_reports(logs, target)
    if target == 'android' and not local:
        record_android_emulator(logs)
    path = logs / (target + '-native-ui.log')
    started_ns = time.time_ns()
    if target == 'ios':
        manifest_path = Path('payload/source.json')
        source = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
        (logs / 'ios-native-ui-device.json').write_text(json.dumps(dict(
            device=device, started_ns=started_ns, source=source)) + '\n')
    # Include cold startup, installation, all native cases and the visual audit.
    # Software-rendered Android audits need the published 40-minute budget.
    # iOS also exercises the added rotation matrix; allow 30 minutes per device.
    timeout = 2400 if target == 'android' else 1800
    with path.open('w') as stream:
        stopped = Event()
        progress = Thread(target=_progress,args=(path,stopped),daemon=True)
        if progress:progress.start()
        process = None
        try:
            process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            code = process.wait(timeout=timeout)
        except BaseException as error:
            if process is None:
                raise
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=10 if isinstance(error, subprocess.TimeoutExpired) else 1)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            if isinstance(error, subprocess.TimeoutExpired):
                raise RuntimeError(f'Native app UI run exceeded {timeout // 60} minutes; see retained logs.') from None
            raise
        finally:
            stopped.set()
            if progress:progress.join(timeout=65 if target == 'ios' else 2)
            record_host_memory(path)
            if target == 'android' and not local:
                record_android_emulator(logs)
    output = logs / (target + ('-native-ui-local.json' if local else '-native-ui.json'))
    manifest = Path('payload/source.json') if local else None
    report = None
    if target == 'android':
        report = collect_android_report(path, code, output, local_manifest=manifest)
    if target == 'ios':
        # Retain failed reports too: the actual assertion belongs in the CLI
        # failure, not just a generic process exit. Accepted exits still require
        # complete case/source verification; Briefcase can lose its exit marker.
        try:
            incoming = read_report(path)
        except ValueError:
            incoming = None
        if incoming is not None:
            (logs / 'ios-native-ui-stdout.json').write_text(json.dumps(incoming, indent=2) + '\n')
            transport = 'stdout'
        elif code in (0, 200):
            # The cache is atomic and fresh for this device/run; it still has
            # to satisfy the same complete case, backend and source contract.
            incoming = simulator_report(device, started_ns, diagnostics=logs)
            transport = 'simulator-file'
        if incoming is not None:
            if code not in (0, 200):
                detail = incoming.get('error') or 'process failed after reporting'
                raise RuntimeError(f'Native app UI run failed ({code}): {detail}')
            if incoming.get('error'):
                log(Severity.ERROR, 'Native iOS report', str(incoming['error']))
                sys.stdout.flush()
            report = verify_report(incoming, target, output, local_manifest=manifest)
            (logs / 'ios-report-transport.json').write_text(json.dumps(dict(
                transport=transport, device=device, briefcase_exit_code=code)) + '\n')
    if report is None:
        if code:
            log(Severity.ERROR, 'Native app output', path.read_text(errors='replace')[-10000:])
            sys.stdout.flush()
            raise RuntimeError(f'Native app UI run failed ({code}); see retained logs.')
        report = verify(path, target, output, local_manifest=manifest)
    if require_independent_windows and report.get('independent_windows_tested') is not True:
        raise ValueError('This run did not verify independent system windows.')
    if require_duo:
        verify_duo_rotation(report)
    verify_native_diagnostics(path)
    return report


def verify_prebuilt_android(*, local=False):
    apk = Path('build/logisticsmobile/android/gradle/app/build/outputs/apk/debug/app-debug.apk')
    expected = json.loads(Path('payload/source.json').read_text())
    if not local:
        root = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
        shared = subprocess.check_output(['git', '-C', str(REPO / 'Python/commonUtils'), 'rev-parse', 'HEAD'], text=True).strip()
        if (expected.get('dirty') is not False or expected.get('logistics_commit') != root
                or expected.get('commonUtils_commit') != shared
                or not re.fullmatch('[0-9a-f]{64}', str(expected.get('source_sha256', '')))):
            raise ValueError('Shared Android test application came from a different source.')
    with zipfile.ZipFile(apk) as archive:
        with zipfile.ZipFile(io.BytesIO(archive.read('assets/chaquopy/app.imy'))) as application:
            actual = json.loads(application.read('mobile/source.json'))
            if actual != expected or not any(name.startswith('tests/logisticsmobile/') for name in application.namelist()):
                raise ValueError('Cached Android APK is not the matching native test application.')


def verify_prebuilt_ios(*, local=False):
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
    if (source != expected or (not local and source.get('dirty') is not False)
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


def boot_timeout_details(error, started, record, lease):
    """Capture the known owned lease and failing stage without another device action."""
    def decoded(value):
        return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
    command = [str(part) for part in error.cmd] if isinstance(error.cmd, (tuple,list)) else str(error.cmd)
    tokens = command if isinstance(command, list) else command.split()
    stage = 'unknown'
    for index, token in enumerate(tokens[:-1]):
        if Path(token).name == 'simctl':
            stage = {'boot': 'boot', 'bootstatus': 'bootstatus', 'list': 'inventory'}.get(tokens[index+1], 'unknown')
            break
    return dict(device=record['device'], command=command, stage=stage, timeout=error.timeout,
        elapsed_seconds=time.monotonic()-started, lease=str(lease), lease_record=dict(record),
        stdout=decoded(error.stdout), stderr=decoded(error.stderr))


def owned_ios_device(lease, *, ipad=False, duo=False, client=None, sdk=None):
    """Use the same fresh, owned simulator lifecycle as local native QA."""
    from build_manager.apple_simulators import AppleSimulators
    from uuid import uuid4
    client = client or AppleSimulators()
    lease = Path(lease)
    if lease.exists():
        raise ValueError('Clean the previous owned simulator lease before creating another.')
    sdk = sdk or subprocess.check_output(
        ['xcrun', '--sdk', 'iphonesimulator', '--show-sdk-version'], text=True).strip()
    parts = sdk.split('.')
    if len(parts) < 2 or not all(part.isdigit() for part in parts):
        raise ValueError('Invalid selected Simulator SDK version.')
    # The 27.1 runtime is Duo-only; ordinary phones/tablets use 27.0 with
    # that SDK. Preserve the selected family's compatible runtime major.
    from logistics_build.test_environments import load, runtime_id
    family = 'duo' if duo else 'ipad' if ipad else 'iphone'
    required = runtime_id(load(REPO), family)
    devices = {runtime: rows for runtime, rows in client.devices()['devices'].items() if runtime == required}
    selected = select_ios_device(dict(devices=devices), ipad=ipad, duo=duo)
    runtime, profile = next((runtime, row) for runtime, rows in devices.items()
                            for row in rows if row['udid'] == selected)
    name = 'Logistics Native Gate ' + uuid4().hex
    device = client.create(name, profile['deviceTypeIdentifier'], runtime)
    lease.parent.mkdir(parents=True, exist_ok=True)
    record = dict(device=device, name=name, runtime=runtime,
                  device_type=profile['deviceTypeIdentifier'], sdk=sdk)
    lease.write_text(json.dumps(record))
    boot_started = time.monotonic()
    try:
        client.boot(device, name=name)
    except subprocess.TimeoutExpired as error:
        # bootstatus reports its current boot phase on stdout. Keep that
        # evidence even when the simulator never becomes responsive.
        try:
            details = boot_timeout_details(error, boot_started, record, lease)
            lease.with_name('ios-native-ui-boot-timeout.json').write_text(json.dumps(details))
        except Exception:
            error.add_note('Owned boot timeout diagnostics could not be captured or saved.')
        raise
    return device


def cleanup_owned_ios_device(lease, *, client=None):
    lease = Path(lease)
    if not lease.exists():
        return
    from build_manager.apple_simulators import AppleSimulators
    record = json.loads(lease.read_text())
    if not record['name'].startswith('Logistics Native Gate '):
        raise ValueError('Refusing cleanup without the native gate ownership label.')
    client = client or AppleSimulators()
    client.remove(record['device'], record['name'])
    record['removed'] = client.matching(record['device'], record['name']) is None
    lease.write_text(json.dumps(record))
    if not record['removed']:
        raise RuntimeError('Owned native gate simulator remains after cleanup.')


def ios_diagnostics():
    """Capture original owned process/crash evidence without replaying the app."""
    logs = Path('logs').resolve()
    logs.mkdir(exist_ok=True)
    receipt = logs / 'ios-native-ui-device.json'
    try:
        recorded = json.loads(receipt.read_text()) if receipt.is_file() else {}
        if not isinstance(recorded, dict):
            recorded = {}
    except (OSError, ValueError):
        recorded = {}
    device = recorded.get('device')
    from mobile_build.validation.ios_failure_diagnostics import owned_run, sample_original
    try:
        owned_run(logs)
        owned = True
    except (OSError, ValueError, KeyError, TypeError):
        owned = False
    if owned and device:
        if recorded.get('started_ns'):
            try:
                simulator_report(device, recorded['started_ns'], diagnostics=logs)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                (logs / 'ios-cache-capture.json').write_text(json.dumps(dict(
                    status='unavailable', error=type(error).__name__)) + '\n')
        command = ['xcrun', 'simctl', 'spawn', device, 'log', 'show', '--last', '10m',
                   '--style', 'compact', '--predicate',
                   'process == "Logistics Mobile" OR eventMessage CONTAINS "io.github.ispaure.logisticsmobile"']
        with (logs / 'ios-system.log').open('w') as output:
            try:
                subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=60, check=False)
            except subprocess.TimeoutExpired:
                output.write('\nSimulator log collection timed out.\n')
    sample_original(logs)
    for name, command in (
            ('host-memory.txt', ['sysctl', 'hw.memsize', 'hw.ncpu']),
            ('host-vm.txt', ['vm_stat'])):
        with (logs / name).open('w') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=15, check=False)
    processes = subprocess.run(['ps', '-axo', 'pid,ppid,state,%cpu,rss,comm'],
                               capture_output=True, text=True, timeout=15, check=False)
    (logs / 'host-webkit-processes.txt').write_text('\n'.join(line for line in processes.stdout.splitlines()
        if any(name in line for name in ('WebKit', 'Simulator', 'Logistics Mobile'))))
    for source in (Path.home() / 'Library/Logs/DiagnosticReports').glob('*.ips'):
        if (source.stat().st_size <= 10 * 1024 * 1024
                and source.stat().st_mtime_ns >= recorded.get('started_ns', time.time_ns())):
            header = source.read_text(errors='replace')[:8192]
            identity_path = logs / 'ios-native-ui-process.json'
            identity = json.loads(identity_path.read_text()) if identity_path.exists() else {}
            try:
                crash = json.loads('\n'.join(source.read_text().splitlines()[1:]))
            except ValueError:
                continue
            if ('logistics' in header.lower() and identity.get('pid')
                    and crash.get('pid', crash.get('procPid')) == identity['pid']):
                shutil.copyfile(source, logs / source.name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'ios-device', 'ios-ipad', 'ios-duo', 'ios-diagnostics', 'ios-cleanup'))
    parser.add_argument('--owned', action='store_true', help='Create a fresh leased simulator in the selected SDK major series')
    parser.add_argument('target', choices=('android', 'ios'), nargs='?')
    parser.add_argument('--device')
    parser.add_argument('--local', action='store_true', help='Verify this exact local payload; not release evidence')
    parser.add_argument('--require-independent-windows', action='store_true')
    parser.add_argument('--require-duo', action='store_true')
    parser.add_argument('--no-update', action='store_true', help='Reuse an already built test application')
    args = parser.parse_args()
    if args.command in ('ios-device', 'ios-ipad', 'ios-duo'):
        options = dict(ipad=args.command == 'ios-ipad', duo=args.command == 'ios-duo')
        print(owned_ios_device('logs/ios-native-ui-owned.json', **options)
              if args.owned else ios_device(**options))
    elif args.command == 'ios-cleanup':
        cleanup_owned_ios_device('logs/ios-native-ui-owned.json')
    elif args.command == 'ios-diagnostics':
        ios_diagnostics()
    else:
        if not args.target or not args.device:
            parser.error('run requires a target and --device')
        run(args.target, args.device, local=args.local, require_independent_windows=args.require_independent_windows,
            require_duo=args.require_duo, no_update=args.no_update)
