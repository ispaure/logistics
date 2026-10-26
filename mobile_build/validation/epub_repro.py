"""Collect a standalone native loading experiment, never release acceptance."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from ui_tools import verify_prebuilt_ios


def main():
    device = sys.argv[1]
    verify_prebuilt_ios()
    logs = Path('logs');logs.mkdir(exist_ok=True)
    host = dict(xcode=subprocess.check_output(['xcodebuild','-version'],text=True).strip(),
        runtimes=json.loads(subprocess.check_output(['xcrun','simctl','list','runtimes','--json'],text=True)))
    (logs/'epub-loading-host.json').write_text(json.dumps(host,indent=2)+'\n')
    report_path=logs/'epub-loading-repro.json'
    report_path.unlink(missing_ok=True)
    started = time.time_ns()
    (logs/'epub-loading-device.json').write_text(json.dumps(dict(device=device,started_ns=started)))
    process=None
    try:
        with (logs/'epub-loading-repro.log').open('w') as output:
            process=subprocess.Popen([sys.executable,'-m','briefcase','run','iOS','--test','--no-input','--device',device,'--no-update'],stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
            process.wait(timeout=1200)
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait()
        container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',device,'io.github.ispaure.logisticsmobile','data'],text=True).strip())
        source=container/'Library/Caches/logistics-epub-repro.json'
        if source.is_file() and source.stat().st_mtime_ns>=started:
            shutil.copy2(source,report_path)
    if not report_path.is_file():
        raise RuntimeError('Diagnostic did not produce a fresh report; inspect logs.')
    report=json.loads(report_path.read_text())
    expected=json.loads(Path('payload/source.json').read_text())
    if (report.get('suite')!='epub-loading-reproduction' or report.get('diagnostic_only') is not True
            or report.get('canonical_native_acceptance') is not False or report.get('source')!=expected):
        raise ValueError('Diagnostic report identity/scope differs from the built artifact.')
    print(json.dumps({k:report.get(k) for k in ['suite','complete','planned_observations','elapsed_seconds','experiment_error']}))
    for row in report['observations']:
        print(json.dumps({k:row.get(k) for k in ['label','mode','deadline_met','late_rendered','seconds']}))
    if report.get('complete') is not True:
        raise RuntimeError('Diagnostic was incomplete; do not treat missing observations as successes.')


if __name__=='__main__':main()
