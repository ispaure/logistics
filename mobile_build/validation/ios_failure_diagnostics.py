"""Read-only evidence from the original hosted Native Gate iOS test process.

This collector requires its Native Gate lease and Python startup marker. A crash
before that marker has no verified original PID here: retain explicit unavailable
metadata and host evidence, without claiming PID-bound IPS coverage. The local
manager backend owns a different lease/collector and is outside this module.
"""
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import time

BUNDLE = 'io.github.ispaure.logisticsmobile'
SOURCE_KEYS = ('logistics_commit', 'commonUtils_commit', 'source_sha256')


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def process_identity(pid):
    result = subprocess.run(['ps', '-ww', '-p', str(pid), '-o', 'lstart=', '-o', 'comm='],
                            capture_output=True, text=True, timeout=5, check=False)
    if result.returncode:
        return None
    match = re.fullmatch(r'(.{24})\s+(.+)', result.stdout.strip())
    if match is None:
        return None
    started = time.mktime(datetime.strptime(match[1], '%a %b %d %H:%M:%S %Y').timetuple())
    return dict(started_ns=int(started * 1e9), executable=match[2])


def owned_run(logs):
    record = json.loads((logs / 'ios-native-ui-device.json').read_text())
    owner = json.loads((logs / 'ios-native-ui-owned.json').read_text())
    if not isinstance(record, dict) or not isinstance(owner, dict):
        raise ValueError('Invalid original native run ownership record.')
    if (not isinstance(owner.get('name'), str)
            or not owner['name'].startswith('Logistics Native Gate ')
            or owner.get('removed') or owner.get('device') != record.get('device')
            or type(record.get('started_ns')) is not int):
        raise ValueError('Original owned native test run is unavailable.')
    return record


def record_process(logs, marker):
    """Bind the original startup marker before any failure-time collection."""
    logs = Path(logs)
    path = logs / 'ios-native-ui-process.json'
    if path.exists():
        return  # A later startup/relaunch must never replace the original identity.
    evidence = dict(status='identity-unverified', marker=marker)
    try:
        record = owned_run(logs)
        if not isinstance(marker, dict):
            raise ValueError('Invalid original process marker.')
        expected = record.get('source') or {}
        if not isinstance(expected, dict) or not isinstance(marker.get('source'), dict):
            raise ValueError('Invalid original process source identity.')
        pid, started = marker.get('pid'), marker.get('started_ns')
        if (type(pid) is not int or pid <= 1 or type(started) is not int
                or started < record['started_ns'] or any(not expected.get(k)
                    or marker.get('source', {}).get(k) != expected[k] for k in SOURCE_KEYS)):
            raise ValueError('Original startup marker does not match this run/source.')
        evidence.update(device=record['device'], run_started_ns=record['started_ns'], pid=pid)
        result = subprocess.run(['xcrun', 'simctl', 'get_app_container', record['device'], BUNDLE, 'app'],
                                capture_output=True, text=True, timeout=10, check=False)
        if result.returncode or not result.stdout.strip():
            raise ValueError('Original installed application is unavailable.')
        executable = str(Path(result.stdout.strip()) / 'Logistics Mobile')
        current = process_identity(pid)
        if current is None:
            evidence['status'] = 'original-process-unavailable'
        elif (current['executable'] != executable or current['started_ns'] < record['started_ns'] - 2_000_000_000
              or current['started_ns'] > started + 2_000_000_000):
            raise ValueError('Original process executable/start identity does not match.')
        else:
            evidence.update(status='original-process-verified', identity=current)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        evidence['error'] = type(error).__name__
    save(path, evidence)


def sample_original(logs):
    """Never launch an app; unavailable/reused/unverified PIDs cannot be sampled."""
    logs = Path(logs)
    result = dict(status='identity-unverified', sampled=False)
    try:
        record = owned_run(logs)
        original = json.loads((logs / 'ios-native-ui-process.json').read_text())
        if (not isinstance(original, dict) or not isinstance(original.get('marker'), dict)
                or not isinstance(original['marker'].get('source'), dict)
                or not isinstance(record.get('source'), dict)):
            raise ValueError('Invalid original process record.')
        if (original.get('status') != 'original-process-verified'
                or original.get('device') != record['device']
                or original.get('run_started_ns') != record['started_ns']
                or any(not record.get('source', {}).get(k) or original.get('marker', {}).get('source', {}).get(k) != record.get('source', {}).get(k)
                       for k in SOURCE_KEYS)):
            raise ValueError('Original process identity was not verified for this run.')
        pid = original['pid']
        if type(pid) is not int or pid <= 1:
            raise ValueError('Invalid original process PID.')
        current = process_identity(pid)
        result['pid'] = pid
        if current is None:
            result['status'] = 'original-process-dead'
        elif current != original['identity']:
            result['status'] = 'original-process-identity-changed'
        else:
            target = logs / 'ios-original-process.sample.txt'
            if target.exists():
                result['status'] = 'already-sampled'
            else:
                capture = subprocess.run(['sample', str(pid), '3', '-file', str(target)],
                    capture_output=True, text=True, timeout=60, check=False)
                result.update(status='sampled' if capture.returncode == 0 else 'sample-failed',
                              sampled=capture.returncode == 0, exit_code=capture.returncode)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result['error'] = type(error).__name__
    save(logs / 'ios-original-process-diagnostics.json', result)
    return result
