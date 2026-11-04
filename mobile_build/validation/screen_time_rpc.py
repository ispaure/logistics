"""Read-only server-side diagnostics for a manager-owned simulator WebView stall."""
import json
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import platform
import re
import subprocess
import time
from uuid import UUID

SERVICES = {
    'com.apple.ScreenTimeSettingsAgent': ('/ScreenTimeSettingsFoundation.framework/ScreenTimeSettingsAgent',),
    'com.apple.ScreenTimeAgent': ('/ScreenTimeCore.framework/ScreenTimeAgent', '/usr/libexec/ScreenTimeAgent'),
    'com.apple.SpringBoard': ('/CoreServices/SpringBoard.app/SpringBoard',),
    'com.apple.ManagedSettingsAgent': ('/ManagedSettings.framework/ManagedSettingsAgent', '/ManagedSettings.framework/Support/ManagedSettingsAgent'),
    'com.apple.FamilyControlsAgent': ('/FamilyControls.framework/FamilyControlsAgent', '/FamilyControls.framework/Support/FamilyControlsAgent'),
}


def capture(log_path, executable, app_pid, *, runner=subprocess.run):
    if type(app_pid) is not int or app_pid <= 1:
        raise ValueError('Invalid app PID.')
    logs = Path(log_path).parent
    receipt = logs / f'ios-screen-time-rpc-{app_pid}.json'
    record = dict(status='received', captured_ns=time.time_ns(), app_pid=app_pid)
    deadline = time.monotonic() + 40
    def command(args, timeout=5):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Service capture budget expired.')
        result = runner(args, capture_output=True, text=True, timeout=min(timeout, remaining), check=False)
        if result.returncode:
            raise RuntimeError('Diagnostic command failed: ' + str(result.returncode))
        return result.stdout
    try:
        match = re.search(r'/Devices/([A-Fa-f0-9-]{36})/data/Containers/Bundle/Application/', executable)
        if match is None:
            raise ValueError('App executable has no simulator identity.')
        device = str(UUID(match[1]))
        owner = json.loads((logs / 'ios-native-ui-owned.json').read_text())
        if (str(UUID(owner['device'])) != device or owner.get('removed')
                or not re.fullmatch(r'Logistics Native Gate [a-f0-9]{32}', owner['name'])):
            raise ValueError('No matching active native-gate owner.')
        inventory = json.loads(command(['xcrun', 'simctl', 'list', 'devices', '--json']))
        found = [(runtime, row) for runtime, rows in inventory['devices'].items() for row in rows
                 if str(UUID(row['udid'])) == device]
        if len(found) != 1 or found[0][1]['name'] != owner['name'] or found[0][1]['state'] != 'Booted':
            raise ValueError('Owned simulator is not booted.')
        record.update(device=device, runtime=dict(identifier=found[0][0]),
                      host=dict(macos=platform.mac_ver()[0], cpus=os.cpu_count()),
                      developer_dir=os.environ.get('DEVELOPER_DIR'))
        # Retain the pre-stall launch/connection timeline before its rolling
        # file can be replaced by minutes of later rotation-test messages.
        timeline = logs / 'ios-webkit-live.log'
        if timeline.exists():
            with timeline.open('rb') as stream:
                stream.seek(max(0, timeline.stat().st_size - 1024 * 1024))
                (logs / f'ios-screen-time-rpc-{app_pid}.timeline.log').write_bytes(stream.read(1024 * 1024))
            record['timeline_captured_ns'] = time.time_ns()
        try:
            runtimes = json.loads(command(['xcrun', 'simctl', 'list', 'runtimes', '--json']))
            row = next(row for row in runtimes['runtimes'] if row['identifier'] == found[0][0])
            record['runtime'].update({key: row[key] for key in ('name', 'version', 'buildversion') if key in row})
        except (ValueError, KeyError, StopIteration, RuntimeError, subprocess.SubprocessError) as error:
            record['runtime_error'] = type(error).__name__
        try:
            record['xcode_version'] = command(['xcodebuild', '-version'])[:500]
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            record['xcode_error'] = type(error).__name__

        related = set()
        record['related_launchd_names'] = {}
        for namespace in ('user/foreground', 'system'):
            try:
                listing = command(['xcrun', 'simctl', 'spawn', device, 'launchctl', 'print', namespace])
                names = sorted({name for name in re.findall(r'\bcom\.apple\.[A-Za-z0-9_.-]+', listing)
                    if any(word in name.lower() for word in ('screentime', 'managedsettings', 'familycontrols'))})[:100]
                record['related_launchd_names'][namespace] = names
                related.update(names)
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                record['related_launchd_names'][namespace] = dict(error=type(error).__name__)
        candidates = [*SERVICES, *sorted(related - SERVICES.keys())[:3]]

        def describe(label):
            row = dict(label=label, started_ns=time.time_ns())
            try:
                for namespace in ('user/foreground', 'system'):
                    service = namespace + '/' + label
                    try:
                        listing = command(['xcrun', 'simctl', 'spawn', device, 'launchctl', 'print', service])
                        break
                    except RuntimeError:
                        continue
                else:
                    raise ValueError('Service is absent in both simulator namespaces.')
                def field(name):
                    match = re.search(r'^\s*' + re.escape(name) + r' = (.+)$', listing, re.MULTILINE)
                    if match is None:
                        raise ValueError('Missing service field: ' + name)
                    return match[1].strip()
                row.update(service=service, state=field('state'), program=field('program'), pid=int(field('pid')))
                # Launchd descriptors can include environment values. Persist
                # selected fields and Apple service names, never the raw dump.
                row['advertised_apple_names'] = sorted(set(re.findall(r'\bcom\.apple\.[A-Za-z0-9_.-]+', listing)))[:100]
                for key in ('runs', 'last exit code', 'active count'):
                    try:
                        row[key] = int(field(key))
                    except ValueError:
                        pass
                allowed = SERVICES.get(label, tuple(suffix for suffixes in SERVICES.values() for suffix in suffixes))
                if row['pid'] <= 1 or not row['program'].endswith(allowed):
                    raise ValueError('Unexpected simulator service identity.')
                observed = command(['ps', '-ww', '-p', str(row['pid']), '-o', 'comm=']).strip()
                if not observed.endswith(allowed):
                    raise ValueError('Service process changed before sampling.')
                row['process'] = command(['ps', '-p', str(row['pid']), '-o', 'pid=,ppid=,state=,%cpu=,rss=,comm=']).strip()
                row['status'] = 'identified'
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                row.update(status='capture-error', error=type(error).__name__ + ': ' + str(error)[:300])
            row['identified_ns'] = time.time_ns()
            return row

        # The original SettingsAgent assumption was not established by a
        # causal reproduction. Capture the other Screen Time candidates and
        # SpringBoard too, within this same explicitly owned simulator.
        # Hosted Macs can have only three CPUs. Bound sampler concurrency so
        # collecting more evidence does not crowd out the app's own sample.
        with ThreadPoolExecutor(max_workers=2) as pool:
            services = list(pool.map(describe, candidates))
            unique = {}
            for row in services:
                if row['status'] == 'identified':
                    unique.setdefault(row['pid'], row)
            def sample(row):
                try:
                    suffix = '' if row['label'] == 'com.apple.ScreenTimeSettingsAgent' else '.' + row['label']
                    output = logs / f'ios-screen-time-rpc-{app_pid}{suffix}.sample.txt'
                    row['sample_started_ns'] = time.time_ns()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('Service capture budget expired.')
                    sampled = runner(['sample', str(row['pid']), '2', '-file', str(output)],
                        capture_output=True, text=True, timeout=min(15, remaining), check=False)
                    graph = output.read_text(errors='replace') if output.is_file() else ''
                    row.update(sample_exit_code=sampled.returncode,
                               thread_stacks_present='Thread_' in graph or 'DispatchQueue_' in graph)
                    row['status'] = 'sampled' if sampled.returncode == 0 and row['thread_stacks_present'] else 'sample-failed'
                except (OSError, subprocess.SubprocessError) as error:
                    row.update(status='capture-error', error=type(error).__name__ + ': ' + str(error)[:300])
                row['sample_finished_ns'] = time.time_ns()
                return row
            sampled = list(pool.map(sample, unique.values()))
        record['services'] = services
        preferred = next((row for row in sampled if row['status'] == 'sampled'), None)
        if preferred is not None:
            record.update({key: preferred[key] for key in ('pid', 'program', 'service', 'state', 'thread_stacks_present', 'sample_exit_code')})
            record['status'] = 'sampled'
        else:
            record.update(status='capture-error', error='; '.join(row.get('error', row['status']) for row in services)[:1000])
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        record.update(status='capture-error', error=type(error).__name__ + ': ' + str(error)[:400])
    record['finished_ns'] = time.time_ns()
    receipt.write_text(json.dumps(record, indent=2) + '\n')
    return record
