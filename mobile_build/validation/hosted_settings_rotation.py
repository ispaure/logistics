"""Run the branch-only Settings contrast on the workflow's verified owned iPad."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from ui_tools import verify_prebuilt_ios


BUNDLE = 'io.github.ispaure.logisticsmobile'
TRACE = 'logistics-native-ui-rotation-trace.jsonl'


def run(device, mode):
    logs = Path('logs')
    lease = json.loads((logs / 'ios-native-ui-owned.json').read_text())
    if (lease['device'] != device or lease.get('removed')
            or not lease['name'].startswith('Logistics Native Gate ')):
        raise ValueError('Expected the fresh diagnostic simulator lease.')
    app = Path('build/logisticsmobile/ios/xcode/build/Debug-iphonesimulator/Logistics Mobile.app')
    verify_prebuilt_ios(app=app)
    simctl = ['xcrun', 'simctl']
    subprocess.run([*simctl, 'install', device, str(app)], check=True, timeout=90)
    cache = subprocess.check_output(
        [*simctl, 'get_app_container', device, BUNDLE, 'data'], text=True, timeout=25).strip()
    source = Path(cache) / 'Library' / 'Caches' / TRACE
    if not cache or source.exists():
        raise ValueError('Expected a new app data container.')
    environment = os.environ | {'SIMCTL_CHILD_LOGISTICS_SETTINGS_ROTATION_PROBE': mode,
                                 'SIMCTL_CHILD_PYTHONUNBUFFERED': '1'}
    started = time.time_ns()
    exit_code = None
    expected = 50 if mode == 'warm' else 36
    try:
        with (logs / 'settings-rotation-console.log').open('w') as output:
            finished = subprocess.run([*simctl, 'launch', '--console-pty', device, BUNDLE],
                                      env=environment, stdout=output, stderr=subprocess.STDOUT,
                                      timeout=1100 if mode == 'warm' else 180, check=False)
            exit_code = finished.returncode
    finally:
        if source.is_file():
            shutil.copyfile(source, logs / TRACE)
        report_dir = Path.home() / 'Library/Logs/DiagnosticReports'
        rows = [json.loads(line) for line in (logs / TRACE).read_text().splitlines()] if source.is_file() else []
        if not rows or rows[-1]['event'] != 'complete':
            time.sleep(5)  # Give the simulator crash reporter time to write its report.
        for report in report_dir.glob('Logistics Mobile*.ips'):
            if report.stat().st_mtime_ns < started or report.stat().st_size > 10 * 1024 * 1024:
                continue
            shutil.copyfile(report, logs / report.name)
        summary = dict(mode=mode, exit_code=exit_code, total_events=len(rows),
                       before=sum(row['event'] == 'request-before' for row in rows),
                       settled=sum(row['event'] == 'request-settled' for row in rows),
                       snapshots=sum('native' in row for row in rows if row['event'] == 'request-before'),
                       last=rows[-1] if rows else None)
        (logs / 'settings-rotation-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary), flush=True)
    if (exit_code != 0 or summary['settled'] != expected or summary['snapshots'] != expected
            or summary['last']['event'] != 'complete' or summary['last']['mode'] != mode):
        raise RuntimeError('The Settings rotation comparison did not complete with full snapshots.')


if __name__ == '__main__':
    run(*sys.argv[1:])
