"""Run shared/app regressions and pristine-before/current ZIP parity on any OS."""

import argparse
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time


REPO = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results-dir', type=Path, default=REPO / 'test-results')
    parser.add_argument('--install', action='store_true', help='Install the project\'s pinned dependencies into this interpreter first')
    parser.add_argument('--prepare-only', action='store_true', help='With --install, prepare dependencies only; this is not a passing test result')
    args = parser.parse_args()
    if args.prepare_only and not args.install:
        parser.error('--prepare-only requires --install and never counts as platform validation')
    if args.install:
        # Export the committed lock rather than resolving transitive versions in CI.
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'uv==0.12.18'], check=True)
        with tempfile.TemporaryDirectory() as directory:
            requirements = Path(directory) / 'requirements.txt'
            subprocess.run([sys.executable, '-m', 'uv', 'export', '--project', str(REPO / 'Python'),
                            '--locked', '--no-dev', '--no-emit-project', '--format', 'requirements-txt',
                            '--output-file', str(requirements)], check=True)
            subprocess.run([sys.executable, '-m', 'uv', 'pip', 'sync', '--python', sys.executable,
                            str(requirements)], check=True)
    if args.install and os.environ.get('LOGISTICS_MANAGER_CHECKOUT'):
        subprocess.run([sys.executable, '-m', 'Scripts.guest_manager', '--checkout', os.environ['LOGISTICS_MANAGER_CHECKOUT'],
                        '--project', str(REPO)], cwd=REPO, check=True, timeout=180)
    results = args.results_dir.resolve()
    results.mkdir(parents=True, exist_ok=True)
    report = {'platform': platform.platform(), 'python': sys.version,
              'dependencies': {name: version(name) for name in ('Pillow', 'PySide6', 'pyzipper', 'yt-dlp')}, 'checks': []}
    env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(REPO / 'Python'), str(REPO))),
               QT_QPA_PLATFORM='offscreen', PYTHONUNBUFFERED='1', PYTHONUTF8='1')
    # Qt expands Windows 8.3 aliases; give fixtures matching native long paths.
    native_temp = str(Path(tempfile.gettempdir()).resolve())
    env.update(TEMP=native_temp, TMP=native_temp, TMPDIR=native_temp)
    if args.install:
        # Framework Python on macOS may lack a default CA path. Use the locked
        # dependency bundle while retaining certificate verification.
        env.setdefault('SSL_CERT_FILE', subprocess.check_output(
            [sys.executable, '-c', 'import certifi; print(certifi.where())'],
            text=True).strip())
        # Clean runners must exercise real crypt operations, not skip their fixtures.
        subprocess.run([sys.executable, '-m', 'Scripts.local_desktop'],
                       cwd=REPO, env=env, check=True, timeout=180)
        env['LOGISTICS_REQUIRE_LOCALCRYPT_TESTS'] = '1'
    if args.prepare_only:
        print('Environment prepared; no platform tests were run.', flush=True)
        return 0
    # A shared project-owned plan feeds CI and the local manager. Functional
    # test discovery remains with the existing isolated regression runner.
    sys.path.insert(0, str(REPO))
    from Scripts.validation_plans import desktop_checks
    checks = desktop_checks(platform.system(), results)
    for name, command, timeout in checks:
        print(f'Running {name} on {platform.system()}…', flush=True)
        from Scripts.platform_checks import run_check
        check_env = dict(env, QT_QPA_PLATFORM='windows') if name == 'windows-native-ui' else env
        row = run_check(name, [sys.executable, *command], root=REPO, results=results,
                        environment=check_env, timeout=timeout)
        code = row['exit_code']
        output = (results/(name+'.log')).read_text(encoding='utf-8', errors='replace')
        report['checks'].append(row)
        (results / 'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f'{name}: {"PASS" if code == 0 else "FAIL"} ({code})', flush=True)
        if code:
            print(output[-12000:], flush=True)
            if name == 'windows-native-ui':
                print(f'Native Windows startup exit: 0x{code & 0xffffffff:08X}', flush=True)
                break  # A fatal bootstrap needs fixing before headless regressions.
    print(f'Reports: {results}', flush=True)
    return int(any(check['exit_code'] for check in report['checks']))


if __name__ == '__main__':
    raise SystemExit(main())
