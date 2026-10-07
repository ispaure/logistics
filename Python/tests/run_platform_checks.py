"""Run shared/app regressions and pristine-before/current ZIP parity on any OS."""

import argparse
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import tomllib

REPO = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', type=Path, default=REPO / 'test-results')
    parser.add_argument('--install', action='store_true', help='Install the project\'s pinned dependencies into this interpreter first')
    args = parser.parse_args()
    if args.install:
        project = tomllib.loads((REPO / 'Python/pyproject.toml').read_text())
        subprocess.run([sys.executable, '-m', 'pip', 'install', *project['project']['dependencies'],
                        *project['tool']['uv']['constraint-dependencies']], check=True)
    results = args.results_dir.resolve()
    results.mkdir(parents=True, exist_ok=True)
    report = {'platform': platform.platform(), 'python': sys.version,
              'dependencies': {name: version(name) for name in ('Pillow', 'PySide6', 'pyzipper')}, 'checks': []}
    env = dict(os.environ, PYTHONPATH=str(REPO / 'Python'), QT_QPA_PLATFORM='offscreen', PYTHONUNBUFFERED='1', PYTHONUTF8='1')
    checks = [
        ('commonutils', ['-X', 'faulthandler', '-m', 'unittest', 'discover', '-s', 'Python/commonUtils/tests', '-v'], 300),
        ('logistics', ['-X', 'faulthandler', '-m', 'unittest', 'discover', '-s', 'Python/tests', '-v'], 300),
        ('compression-parity', ['Python/tests/compare_comic_zip_versions.py', '--output-dir', str(results / 'parity')], 600),
    ]
    for name, command, timeout in checks:
        print(f'Running {name} on {platform.system()}…', flush=True)
        started = time.monotonic()
        try:
            completed = subprocess.run([sys.executable, *command], cwd=REPO, env=env, capture_output=True, timeout=timeout)
            output = (completed.stdout + completed.stderr).decode('utf-8', errors='replace')
            code = completed.returncode
        except subprocess.TimeoutExpired as error:
            output = ((error.stdout or b'') + (error.stderr or b'')).decode('utf-8', errors='replace') + '\nTimed out.'
            code = 124
        (results / (name + '.log')).write_text(output, encoding='utf-8')
        report['checks'].append({'name': name, 'exit_code': code, 'seconds': round(time.monotonic() - started, 2)})
        (results / 'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f'{name}: {"PASS" if code == 0 else "FAIL"} ({code})', flush=True)
        if code:
            print(output[-12000:], flush=True)
    print(f'Reports: {results}', flush=True)
    return int(any(check['exit_code'] for check in report['checks']))


if __name__ == '__main__':
    raise SystemExit(main())
