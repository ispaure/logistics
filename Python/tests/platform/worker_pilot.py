"""Measure the same portable test files with one and four isolated workers."""
import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import platform
from statistics import median
import subprocess
import sys
from time import monotonic


TESTS = Path(__file__).resolve().parents[1]
ROOT = TESTS.parents[1]
sys.path.insert(0, str(TESTS))
from parallel_regressions import PORTABLE_DIRECTORY, PORTABLE_FILES, PORTABLE_PILOT_ENV  # noqa: E402


def inventory(report):
    if not report['complete'] or not report['coverage_complete'] or report['not_run']:
        raise RuntimeError('Pilot sample did not account for every selected test.')
    cases = Counter((row['file'], row['stage'], row['id'], row['outcome']) for row in report['tests'])
    modules = Counter((row['path'], row['stage'], row['outcome']) for row in report['modules'])
    if {path for path, _, _ in modules} != set(PORTABLE_FILES) or not cases:
        raise RuntimeError('Pilot sample had a different inventory from the approved files.')
    return cases, modules


def peak_overlap(report):
    events = []
    for row in report['modules']:
        events.extend([(datetime.fromisoformat(row['started_at']), 1),
                       (datetime.fromisoformat(row['finished_at']), -1)])
    current = peak = 0
    for _, change in sorted(events):
        current += change
        peak = max(peak, current)
    return peak


def sample(output, index, workers):
    stem = output / f'sample-{index}-{workers}-workers'
    report = stem.with_suffix('.json')
    command = [sys.executable, str(TESTS / 'run_regressions.py'), PORTABLE_DIRECTORY,
               '--isolate-modules', '--workers', str(workers), '--report', str(report),
               '--junit', str(stem.with_suffix('.xml'))]
    for name in PORTABLE_FILES:
        command.extend(('--exact-file', name))
    # The pilot itself owns the four-worker budget on its dedicated runner or
    # guest. Its inner tests report to their own files.
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen',
                       BUILD_MANAGER_TEST_PROGRESS='0', **{PORTABLE_PILOT_ENV: '1'})
    environment.pop('TOGA_BACKEND', None)
    started = monotonic()
    with stem.with_suffix('.log').open('wb') as log:
        completed = subprocess.run(command, cwd=ROOT, env=environment, stdout=log,
                                   stderr=subprocess.STDOUT, timeout=180)
    if completed.returncode:
        raise RuntimeError(f'Pilot sample {index} with {workers} workers failed. See {log.name}.')
    data = json.loads(report.read_text(encoding='utf-8'))
    return dict(workers=workers, wall_seconds=round(monotonic() - started, 3),
                peak_overlap=peak_overlap(data), report=report.name), inventory(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform not in ('win32', 'linux'):
        parser.error('Use Windows or Linux for this pilot.')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    samples = []
    baseline = None
    for index, workers in enumerate((1, 4, 4, 1, 1, 4), start=1):
        row, outcomes = sample(output, index, workers)
        if baseline is None:
            baseline = outcomes
        if outcomes != baseline or row['peak_overlap'] != workers:
            raise RuntimeError(f'Pilot sample {index} differed in coverage, outcome or worker overlap.')
        samples.append(row)
    times = {workers: median(row['wall_seconds'] for row in samples if row['workers'] == workers)
             for workers in (1, 4)}
    result = dict(platform=platform.platform(), architecture=platform.machine(),
                  python=sys.version.split()[0], files=len(PORTABLE_FILES),
                  cases=sum(baseline[0].values()), file_stages=sum(baseline[1].values()),
                  serial_median_seconds=times[1], four_worker_median_seconds=times[4],
                  wall_reduction_percent=round(100 * (1 - times[4] / times[1]), 1),
                  samples=samples)
    (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
