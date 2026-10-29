"""Logistics portable Windows prerequisite policy; guest transport stays generic."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import signal
import subprocess
from threading import Event
import time
from uuid import uuid4
import zipfile

from build_manager import Phase, Plan
from build_manager.parallels import Parallels
from build_manager.windows_guest import WindowsGuest
from build_manager.guest_tools import WINDOWS_PREPARE, windows_parameters
from logistics_build.build_snapshots import source_members
from logistics_build.guest_results import GuestResultLifecycle, waiting_progress


PREPARE = WINDOWS_PREPARE


def prepare(vm, output):
    client = Parallels()
    guest = client.start(vm)
    catalog = json.loads(Path(__file__).with_name('build_manager_tools.json').read_text())['windows_arm64']
    from logistics_build.test_environments import load
    catalog['runtime']['python'] = 'cpython-' + load()['python_version'] + '-windows-x86_64'
    token = uuid4().hex
    parameters = windows_parameters(token, catalog, **catalog['runtime'])
    record = dict(token=token, vm=guest['uuid'], status='preparing', tests_run=False)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + '\n')
    try:
        prepared = json.loads(client.powershell(guest['uuid'], PREPARE, parameters, timeout=360))
        record.update(prepared, status='prepared', original_state=guest['status'])
        return record
    except (OSError, ValueError, RuntimeError) as error:
        record.update(status='failed', error=str(error))
        raise
    finally:
        output.write_text(json.dumps(record, indent=2) + '\n')


def source_zip(snapshot):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in source_members(snapshot):
            path = snapshot / name
            if path.is_symlink():
                raise ValueError('Windows source transfer cannot flatten a symbolic link: '+name)
            files = sorted(path.rglob('*')) if path.is_dir() else [path]
            for file in files:
                if file.is_symlink():
                    raise ValueError('Windows source transfer cannot flatten a symbolic link: '+str(file.relative_to(snapshot)))
                if file.is_file():
                    archive.write(file, file.relative_to(snapshot).as_posix())
    return stream.getvalue()


def run(args):
    from copy import copy
    from logistics_build.guest_attempts import result_attempt
    with result_attempt(args.results, args.source_identity, 'Parallels Windows') as directory:
        attempt = copy(args)
        attempt.results = directory
        return _run_attempt(attempt)


def _run_attempt(args):
    client = Parallels()
    cancelled = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: cancelled.set())
    args.results.mkdir(parents=True, exist_ok=False)
    selected = client.start(args.vm)
    if args.prepared and args.prepared.is_file():
        prepared = json.loads(args.prepared.read_text())
        if prepared.get('vm') != selected['uuid'] or prepared.get('status') != 'prepared':
            raise ValueError('Prepared tools belong to another guest or are incomplete.')
    else:
        prepared = prepare(args.vm, args.results / 'prepared.json')
    operation = uuid4().hex
    guest = WindowsGuest(client, prepared['vm'], prepared['workspace'], prepared['token'], operation)
    source = 'source-' + operation
    reports = 'reports-' + operation
    root = PureWindowsPath(prepared['workspace'])
    target = str(root / source)
    report_dir = str(root / reports)
    python = prepared['python']
    environment = dict(PYTHONPATH=target + ';' + str(root / source / 'Python'), PYTHONUNBUFFERED='1',
                       PYTHONUTF8='1', QT_QPA_PLATFORM='offscreen',
                       UV_PYTHON_INSTALL_DIR=str(root / 'python'), UV_CACHE_DIR=str(root / 'cache'),
                       UV_PYTHON_ARCH='x86_64', BROWSER_TEST_ARTIFACTS=str(root / reports / 'browser-diagnostics'))
    if getattr(args, 'manager_working_tree', None):
        environment['LOGISTICS_MANAGER_LOCAL_TEST_SOURCE'] = args.manager_working_tree
    if os.environ.get('LOGISTICS_REUSE_TEST_RESULTS') == 'off':
        environment['LOGISTICS_REUSE_TEST_RESULTS'] = 'off'
    result = dict(schema=1, status='running', source=args.source_identity, backend='Parallels Windows', original_state=selected['status'],
                  started_at=datetime.now(timezone.utc).isoformat(), guest_architecture=prepared['guestArchitecture'],
                  runtime=prepared['runtime'], workspace=prepared['workspace'], workspace_token=prepared['token'], operation=operation)
    lifecycle = GuestResultLifecycle(result, args.results, 'Parallels Windows', 'test_workspace')
    manager = 'manager-' + operation
    try:
        payload = source_zip(args.snapshot)
        result['transfer_sha256'] = hashlib.sha256(payload).hexdigest()
        transfer = time.monotonic()
        guest.stage(source, payload)
        result['transfer_seconds'] = time.monotonic() - transfer
        # Git's filemode setting is platform-specific in an owned copied clone.
        configure = r'''
foreach ($directory in @($p.source,(Join-Path $p.source 'Python\commonUtils'))) {
 & $p.git -C $directory config --local core.filemode false
 if ($LASTEXITCODE -ne 0) { throw 'Cannot configure owned Git workspace' }
 & $p.git -C $directory config --local core.autocrlf false
 & $p.git -C $directory config --local core.longpaths true
}
$version=& $p.python -c 'import json,platform,sysconfig,struct,sys;print(json.dumps(dict(guest=platform.machine(),python_platform=sysconfig.get_platform(),pointer_bits=8*struct.calcsize(chr(80)),version=sys.version)))'
@{runtime=($version|ConvertFrom-Json);git=[string](& $p.git --version);path=$env:PATH}|ConvertTo-Json -Compress
'''
        info = json.loads(guest.call_idempotent(configure,
            values=dict(source=target, git=prepared['git'], python=python), timeout=60))
        result.update(runtime=info['runtime'], git=info['git'])
        environment['PATH'] = str(PureWindowsPath(prepared['git']).parent) + ';' + str(root / 'environment/Scripts') + ';' + info['path']
        manager = 'manager-' + operation
        manager_path = str(root / manager)
        if args.manager_checkout:
            from logistics_build.guest_manager import archive
            guest.stage(manager, archive(args.manager_checkout, args.snapshot, 'zip', working_tree=getattr(args, 'manager_working_tree', None)))
            guest.call_idempotent("foreach($folder in @($p.root,($p.root+'\\Python\\commonUtils'))){& $p.git -C $folder config core.fileMode false;if($LASTEXITCODE -ne 0){throw 'Manager Git setup failed'}}", values=dict(root=manager_path,git=prepared['git']))
            setup_command = ['-m','logistics_build.guest_manager','--checkout',manager_path,'--project',target]
        else:
            setup_command = ['logistics_build/install_build_manager.py','--from-pin',manager_path]
        environment['LOGISTICS_MANAGER_CHECKOUT'] = manager_path
        setup = guest.run(python, setup_command, source, reports, environment, cancelled, timeout=600,
                          progress=waiting_progress('Windows', 'manager setup'))
        if setup:
            raise RuntimeError('Guest external-manager setup failed; verify the exact pinned source is available.')
        install = (python, 'Python/tests/run_platform_checks.py', '--install', '--results-dir', report_dir)
        if args.pattern:
            from logistics_build.guest_manager import focused_command
            command = focused_command(python, args.pattern, manager_path)
            phases = (Phase('environment', (*install, '--prepare-only'), target, timeout=600, environment=environment, kind='setup'),
                      Phase('focused', command, target,
                            timeout=1200, environment=dict(environment, LOGISTICS_REQUIRE_LOCALCRYPT_TESTS='1'), dependencies=('environment',)))
        else:
            phases = (Phase('platform', install, target, timeout=5400, environment=environment),
                      Phase('release-tooling', (python, '-m', 'unittest', 'discover', '-s', '.github/scripts', '-v'),
                            target, timeout=300, environment=environment))
        if getattr(args, 'native_notebooks', False):
            probe_count = len(args.notebook_probe or ('drawing-save-stress', 'page-two-memory', 'menus-zoom', 'brush-pixels'))
            graphics_count = 4 if args.notebook_rendering == 'all' else 1
            phases += (Phase('notebook-native', (python, 'Python/tests/notebooks/notebook_platform_probe.py',
                '--output', str(root / reports / 'notebook-native'),
                *(['--rendering', args.notebook_rendering] if args.notebook_rendering else []),
                *(value for probe in args.notebook_probe or [] for value in ('--probe', probe))), target,
                timeout=600 * probe_count * graphics_count + 30,
                environment=environment, dependencies=('environment',)),)
        plan = Plan('Logistics', 'Focused Windows contracts' if args.pattern else 'Full local Windows platform checks',
                    args.source_identity, phases, str(root / ('operation-' + operation)), backend='Parallels Windows')
        plan_name = 'plan-' + operation + '.json'
        guest.write(plan_name, json.dumps(plan.data(), indent=2).encode())
        argv = ['-m', 'build_manager', str(root / plan_name), '--output', str(root / reports / 'manager'),
                '--cancel-file', str(root / ('cancel-' + operation))]
        code = guest.run(python, argv, source, reports, environment, cancelled, timeout=6000,
                         progress=waiting_progress('Windows', 'selected checks'))
        result['status'] = 'cancelled' if cancelled.is_set() else 'passed' if code == 0 else 'failed'
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result.update(status='failed', error=str(error))
    finally:
        lifecycle.collect(
            lambda: guest.collect([reports, source + '/test-results'], args.results / 'guest'),
            args.results / 'guest' / reports / 'manager/result.json',
            lambda: guest.remove_paths([source, source + '.zip', manager, manager + '.zip', reports,
                'plan-' + operation + '.json', 'operation-' + operation, 'cancel-' + operation,
                'evidence-' + operation + '.zip']))
        result['public_tool_cache_retained'] = True
        lifecycle.finish()
    if args.shutdown and selected['status'] == 'stopped':
        client.shutdown(selected['uuid'])
    return int(result['status'] != 'passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vm', required=True)
    parser.add_argument('--prepare-output', type=Path)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--results', type=Path)
    parser.add_argument('--source-identity', type=json.loads)
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--pattern', default='')
    parser.add_argument('--native-notebooks', action='store_true', help='Run native notebook UI probes after focused setup')
    parser.add_argument('--notebook-probe', action='append', choices=('drawing-save-stress', 'page-two-memory', 'menus-zoom', 'brush-pixels'),
                        help='Select focused native checks; defaults to all checks')
    parser.add_argument('--notebook-rendering', choices=('native', 'software', 'chromium-software', 'warp', 'all'),
                        help='Select a graphics path for native notebook acceptance')
    parser.add_argument('--manager-checkout', type=Path)
    parser.add_argument('--manager-working-tree', help='Exact captured manager content identity for explicit local testing only')
    parser.add_argument('--shutdown', action='store_true')
    args = parser.parse_args()
    if args.native_notebooks and not args.pattern:
        parser.error('--native-notebooks requires an explicit focused test pattern')
    if args.snapshot:
        if not args.results or not args.source_identity:
            parser.error('A source snapshot requires explicit identity and result paths.')
        return run(args)
    if not args.prepare_output:
        parser.error('Select source validation or an explicit preparation output.')
    record = prepare(args.vm, args.prepare_output)
    print(json.dumps(dict(status='tools prepared; tests not run', guest_architecture=record['guestArchitecture'],
                          runtime=record['runtime'], interactive_session=record['session'])))


if __name__ == '__main__':
    raise SystemExit(main())
