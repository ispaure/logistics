"""Logistics portable Windows prerequisite policy; guest transport stays generic."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
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
from Scripts.build_snapshots import source_members


PREPARE = r'''
if ((Get-Process -Id $PID).SessionId -eq 0) { throw 'Use the existing interactive guest test account.' }
if ($env:PROCESSOR_ARCHITECTURE -ne 'ARM64') { throw 'This tool catalog requires the selected Windows ARM64 guest.' }
if ($p.token -notmatch '^[a-f0-9]{32}$') { throw 'Invalid workspace ownership token.' }
$root=Join-Path ([Environment]::GetFolderPath('CommonDocuments')) ('bm\'+$p.token)
if (Test-Path -LiteralPath $root) { throw 'Owned workspace already exists; inspect it before retry.' }
$null=New-Item -ItemType Directory -Path $root
@{token=$p.token}|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $root '.manager-owned.json') -Encoding UTF8
$downloads=Join-Path $root 'downloads'; $null=New-Item -ItemType Directory -Path $downloads
$tools=Join-Path $root 'tools'; $null=New-Item -ItemType Directory -Path $tools
$resolved=@{}
foreach ($entry in @(@{name='uv';value=$p.tools.uv},@{name='git';value=$p.tools.git})) {
 $tool=$entry.value
 if ($tool.url -notmatch '^https://github.com/' -or $tool.sha256 -notmatch '^[a-f0-9]{64}$') { throw 'Invalid pinned tool metadata.' }
 $zip=Join-Path $downloads ($entry.name+'.zip')
 Invoke-WebRequest -UseBasicParsing -Uri $tool.url -OutFile $zip -TimeoutSec 120
 if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $tool.sha256) { throw 'Tool archive hash mismatch.' }
 $folder=Join-Path $tools $entry.name
 Expand-Archive -LiteralPath $zip -DestinationPath $folder
 $resolved[$entry.name]=(Get-ChildItem -LiteralPath $folder -Filter ($entry.name+'.exe') -Recurse|Select-Object -First 1).FullName
 if (-not $resolved[$entry.name]) { throw ('Tool executable missing: '+$entry.name) }
}
$env:UV_PYTHON_INSTALL_DIR=Join-Path $root 'python';$env:UV_CACHE_DIR=Join-Path $root 'cache';$env:UV_PYTHON_ARCH='x86_64'
$environment=Join-Path $root 'environment'
& $resolved.uv venv --python cpython-3.12.2-windows-x86_64 --seed $environment
if ($LASTEXITCODE -ne 0) { throw 'Pinned Windows interpreter preparation failed.' }
$python=Join-Path $environment 'Scripts\python.exe'
$version=& $python -c 'import json,platform,sys;print(json.dumps(dict(version=sys.version,architecture=platform.machine())))'
if ($LASTEXITCODE -ne 0) { throw 'Pinned interpreter could not execute.' }
$record=@{token=$p.token;workspace=$root;python=$python;uv=$resolved.uv;git=$resolved.git;runtime=($version|ConvertFrom-Json);guestArchitecture=$env:PROCESSOR_ARCHITECTURE;session=(Get-Process -Id $PID).SessionId}
$record|ConvertTo-Json -Depth 5|Set-Content -LiteralPath (Join-Path $root 'prepared.json') -Encoding UTF8
$record|ConvertTo-Json -Depth 5 -Compress
'''


def prepare(vm, output):
    client = Parallels()
    guest = client.start(vm)
    tools = json.loads(Path(__file__).with_name('build_manager_tools.json').read_text())['windows_arm64']
    token = uuid4().hex
    record = dict(token=token, vm=guest['uuid'], status='preparing', tests_run=False)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + '\n')
    try:
        prepared = json.loads(client.powershell(guest['uuid'], PREPARE, dict(token=token, tools=tools), timeout=360))
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
    result = dict(schema=1, status='running', source=args.source_identity, backend='Parallels Windows', original_state=selected['status'],
                  started_at=datetime.now(timezone.utc).isoformat(), guest_architecture=prepared['guestArchitecture'],
                  runtime=prepared['runtime'], workspace=prepared['workspace'], operation=operation)
    started = time.monotonic()
    collected = False
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
        info = json.loads(client.powershell(prepared['vm'], configure,
            dict(source=target, git=prepared['git'], python=python), timeout=60))
        result.update(runtime=info['runtime'], git=info['git'])
        environment['PATH'] = str(PureWindowsPath(prepared['git']).parent) + ';' + str(root / 'environment/Scripts') + ';' + info['path']
        setup = guest.run(python, ['Scripts/install_build_manager.py','--from-pin',str(root/'manager')], source, reports, environment, cancelled, timeout=600)
        if setup:raise RuntimeError('Guest external-manager setup failed; verify the exact pinned source is available.')
        install = (python, 'Python/tests/run_platform_checks.py', '--install', '--results-dir', report_dir)
        if args.pattern:
            suite, pattern = ('shared', args.pattern[7:]) if args.pattern.startswith('shared:') else ('desktop', args.pattern)
            phases = (Phase('environment', (*install, '--prepare-only'), target, timeout=600, environment=environment, kind='setup'),
                      Phase('focused', (python, 'dev.py', 'test', suite, pattern, '--python', python), target,
                            timeout=1200, environment=dict(environment, LOGISTICS_REQUIRE_LOCALCRYPT_TESTS='1'), dependencies=('environment',)))
        else:
            phases = (Phase('platform', install, target, timeout=3000, environment=environment),
                      Phase('release-tooling', (python, '-m', 'unittest', 'discover', '-s', '.github/scripts', '-v'),
                            target, timeout=300, environment=environment))
        plan = Plan('Logistics', 'Focused Windows contracts' if args.pattern else 'Full local Windows platform checks',
                    args.source_identity, phases, str(root / ('operation-' + operation)), backend='Parallels Windows')
        plan_name = 'plan-' + operation + '.json'
        guest.write(plan_name, json.dumps(plan.data(), indent=2).encode())
        argv = ['-m', 'build_manager', str(root / plan_name), '--output', str(root / reports / 'manager'),
                '--cancel-file', str(root / ('cancel-' + operation))]
        code = guest.run(python, argv, source, reports, environment, cancelled, timeout=3400)
        result['status'] = 'cancelled' if cancelled.is_set() else 'passed' if code == 0 else 'failed'
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result.update(status='failed', error=str(error))
    finally:
        try:
            guest.collect([reports, source + '/test-results'], args.results / 'guest')
            collected = True
            evidence = args.results / 'guest' / reports / 'manager/result.json'
            if evidence.is_file():
                report = json.loads(evidence.read_text())
                if report['source'] != args.source_identity or report['backend'] != 'Parallels Windows':
                    raise ValueError('Retrieved Windows evidence belongs to another source/backend.')
                result['phases'] = report['phases']
                result['guest_result'] = str(evidence)
                if result['status'] == 'passed' and report['status'] != 'passed':
                    raise ValueError('Windows exit status disagrees with required validation result.')
            elif result['status'] == 'passed':
                raise ValueError('Windows did not produce its required validation result.')
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
            result.update(status='failed', retrieval_error=str(error))
        if collected:
            try:
                guest.remove_paths([source, source + '.zip', reports, 'plan-' + operation + '.json',
                                    'operation-' + operation, 'cancel-' + operation])
                result['test_workspace_removed'] = True
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                result.update(status='failed', cleanup_error=str(error))
        else:
            result['test_workspace_preserved_for_recovery'] = True
        result['seconds'] = time.monotonic() - started
        result['public_tool_cache_retained'] = True
        (args.results / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result), flush=True)
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
    parser.add_argument('--shutdown', action='store_true')
    args = parser.parse_args()
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
