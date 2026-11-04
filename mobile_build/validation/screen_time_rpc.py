"""Read-only server-side diagnostics for a manager-owned simulator WebView stall."""
import json
from pathlib import Path
import re
import subprocess
import time
from uuid import UUID


def capture(log_path, executable, app_pid, *, runner=subprocess.run):
    if type(app_pid) is not int or app_pid <= 1:
        raise ValueError('Invalid app PID.')
    logs = Path(log_path).parent
    receipt = logs / f'ios-screen-time-rpc-{app_pid}.json'
    record = dict(status='received', captured_ns=time.time_ns())
    def command(args, timeout=5):
        result = runner(args, capture_output=True, text=True, timeout=timeout, check=False)
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
        found = [row for rows in inventory['devices'].values() for row in rows
                 if str(UUID(row['udid'])) == device]
        if len(found) != 1 or found[0]['name'] != owner['name'] or found[0]['state'] != 'Booted':
            raise ValueError('Owned simulator is not booted.')
        record['device'] = device
        service = 'user/foreground/com.apple.ScreenTimeSettingsAgent'
        listing = command(['xcrun', 'simctl', 'spawn', device, 'launchctl', 'print', service])
        def field(name):
            match = re.search(r'^\s*' + name + r' = (.+)$', listing, re.MULTILINE)
            if match is None:
                raise ValueError('Missing service field: ' + name)
            return match[1].strip()
        pid = int(field('pid'))
        program = field('program')
        if pid <= 1 or not program.endswith('/ScreenTimeSettingsFoundation.framework/ScreenTimeSettingsAgent'):
            raise ValueError('Unexpected Screen Time service identity.')
        observed = command(['ps', '-ww', '-p', str(pid), '-o', 'comm=']).strip()
        if not observed.endswith('/ScreenTimeSettingsFoundation.framework/ScreenTimeSettingsAgent'):
            raise ValueError('Service process changed before sampling.')
        record.update(service=service, pid=pid, state=field('state'), program=program)
        record['process'] = command(['ps', '-p', str(pid), '-o', 'pid=,ppid=,state=,%cpu=,rss=,comm=']).strip()
        output = logs / f'ios-screen-time-rpc-{app_pid}.sample.txt'
        sampled = runner(['sample', str(pid), '2', '-file', str(output)],
            capture_output=True, text=True, timeout=15, check=False)
        record['sample_exit_code'] = sampled.returncode
        graph = output.read_text(errors='replace') if output.is_file() else ''
        record['thread_stacks_present'] = 'Thread_' in graph or 'DispatchQueue_' in graph
        record['status'] = ('sampled' if sampled.returncode == 0 and record['thread_stacks_present']
                            else 'sample-failed')
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        record.update(status='capture-error', error=type(error).__name__ + ': ' + str(error)[:400])
    receipt.write_text(json.dumps(record, indent=2) + '\n')
    return record
