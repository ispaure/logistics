"""Prepare an isolated native pose audit from an existing simulator build.

Choose real interior poses in Device Hub, then use --pose-sweep. The default
sweeps outer scene rotations. --observe-folds subsequently monitors a retained
comic while the operator opens/closes/rotates/folds the device. Results never
claim unobserved poses. This tool does not install over the main application.
"""
import argparse
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import time
from tempfile import TemporaryDirectory

if __package__:
    from .tools import stage
else:
    from tools import stage

BUNDLE = 'io.github.ispaure.logisticsduofoldqa'
REPO = Path(__file__).resolve().parents[1]


def sim(*arguments, check=True):
    return subprocess.run(['xcrun', 'simctl', *arguments], check=check,
                          capture_output=True, text=True).stdout.strip()


def prepare(source, output):
    source, output = source.resolve(), output.resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('QA output must be separate from the source simulator build.')
    if output.exists():
        raise ValueError('Choose a fresh output directory for this audit.')
    output.mkdir(parents=True)
    payload, app = output / 'payload', output / 'Fold QA.app'
    stage(REPO, payload, allow_dirty=True)
    shutil.copytree(source, app, symlinks=True)
    for name in ('logisticsmobile', 'features', 'services', 'commonUtils'):
        target = app / 'app' / name
        shutil.rmtree(target)
        shutil.copytree(payload / name, target)
    shutil.copytree(REPO / 'Mobile/native_tests/tests', app / 'app/tests', dirs_exist_ok=True)
    shutil.copyfile(payload / 'source.json', app / 'app/fold-source.json')
    (app / 'app/logisticsmobile/__main__.py').write_text(
        'from tests.logisticsmobile.duo_pose_probe import main\nmain().main_loop()\n')
    info_path = app / 'Info.plist'
    info = plistlib.loads(info_path.read_bytes())
    info.update(CFBundleIdentifier=BUNDLE, CFBundleDisplayName='Fold QA')
    info_path.write_bytes(plistlib.dumps(info))
    subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app)], check=True)
    return app


def run(source, output, device, *, pose_sweep=False, observe_folds=False, timeout=900):
    if output.exists():
        raise ValueError('Choose a fresh evidence output directory.')
    output.mkdir(parents=True)
    build = TemporaryDirectory(prefix='logistics-fold-qa-')
    try:
        app = prepare(source, Path(build.name) / 'build')
        shutil.copyfile(app / 'app/fold-source.json', output / 'source.json')
    except BaseException:
        build.cleanup()
        raise
    installed = False
    cache = None
    started = time.time_ns()
    try:
        sim('terminate', device, BUNDLE, check=False)
        sim('install', device, str(app))
        installed = True
        cache = Path(sim('get_app_container', device, BUNDLE, 'data')) / 'Library/Caches/toolbar-qa'
        (cache / 'result.json').unlink(missing_ok=True)
        arguments = [flag for flag, enabled in (('--pose-sweep', pose_sweep), ('--observe-folds', observe_folds)) if enabled]
        sim('launch', device, BUNDLE, *arguments)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = cache / 'result.json'
            if result.exists() and result.stat().st_mtime_ns >= started:
                report = json.loads(result.read_text())
                if not report.get('success'):
                    raise RuntimeError(report.get('error', 'Native audit failed.'))
                if not observe_folds or report.get('comic_fold_round_trip_tested'):
                    print(json.dumps(dict(success=True, observed_poses=report.get('observed_poses'),
                                          all_fold_poses_tested=report.get('all_fold_poses_tested'),
                                          comic_fold_round_trip_tested=report.get('comic_fold_round_trip_tested'))))
                    return report
            time.sleep(.5)
        raise TimeoutError('Audit timed out; retained evidence lists only the observed poses.')
    finally:
        # Evidence first, cleanup second, including failures and interrupted runs.
        try:
            if cache is not None and cache.exists():
                shutil.copytree(cache, output / 'evidence', dirs_exist_ok=True)
        finally:
            build.cleanup()
            if installed:
                sim('terminate', device, BUNDLE, check=False)
                sim('uninstall', device, BUNDLE)
                applications = sim('listapps', device)  # simctl emits an OpenStep plist.
                if BUNDLE in applications:
                    raise RuntimeError('QA cleanup failed: ' + BUNDLE)



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True, help='An existing Logistics Simulator .app')
    parser.add_argument('--output', type=Path, required=True, help='A new audit output directory')
    parser.add_argument('--device', required=True)
    parser.add_argument('--pose-sweep', action='store_true')
    parser.add_argument('--observe-folds', action='store_true')
    parser.add_argument('--timeout', type=int, default=900)
    arguments = parser.parse_args()
    run(arguments.app, arguments.output, arguments.device, pose_sweep=arguments.pose_sweep,
        observe_folds=arguments.observe_folds, timeout=arguments.timeout)
