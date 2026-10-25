"""Logistics Linux VM policy over the reusable existing-guest transport."""
import argparse
import base64
import json
from pathlib import Path
import signal
import subprocess
import sys
from threading import Event
import time
from uuid import uuid4

from build_manager import Phase, Plan
from build_manager.parallels import Parallels
from Scripts.build_snapshots import source_members


INSPECT = '''import json,os,pathlib,platform,pwd
users=[dict(uid=p.pw_uid,gid=p.pw_gid) for p in pwd.getpwall() if 1000<=p.pw_uid<60000]
print(json.dumps(dict(system=platform.system(),architecture=platform.machine(),
os_release=pathlib.Path('/etc/os-release').read_text(),users=users)))
'''

BOOTSTRAP = '''import pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]); bootstrap=root/'bootstrap'; environment=root/'environment'
subprocess.run([sys.executable,'-m','venv',str(bootstrap)],check=True,timeout=120)
python=bootstrap/'bin/python'
subprocess.run([str(python),'-m','pip','install','uv==0.12.18'],check=True,timeout=300)
subprocess.run([str(python),'-m','uv','venv','--python','3.12.2','--seed',str(environment)],check=True,timeout=600)
'''




def run(args):
    cancelled = Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: cancelled.set())
    client = Parallels()
    original = client.start(args.vm)
    vm = original['uuid']
    deadline = time.monotonic() + 120
    while True:
        try:
            info = json.loads(client.execute(vm, ['python3', '-c', INSPECT], timeout=15))
            break
        except (RuntimeError, subprocess.TimeoutExpired):
            if cancelled.is_set() or time.monotonic() >= deadline:
                raise RuntimeError('Guest tools/Python are not ready; no test result is implied.') from None
            cancelled.wait(2)
    expected_host = 'ubuntu' if args.container_image else args.distribution
    if info['system'] != 'Linux' or ('ID=' + expected_host) not in info['os_release'].replace('"', ''):
        raise ValueError('Selected VM does not provide the requested Linux distribution.')
    if len(info['users']) != 1:
        raise ValueError('Select a guest with one identifiable normal test account; no root Qt fallback is allowed.')
    account = info['users'][0]
    container = None
    token = uuid4().hex
    workspace = '/var/tmp/' + token
    result = dict(schema=1, vm=vm, original_state=original['status'], environment=info,
                  workspace=workspace, source=args.source_identity, status='running', phases=[])
    args.results.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    staged = False
    transfer_attempted = False
    collected = False
    try:
        transfer_started = time.monotonic()
        transfer_attempted = True
        result['transferred_sha256'] = client.stage(vm, args.snapshot, workspace, token, account['uid'], account['gid'],
                                                  members=source_members(args.snapshot))
        staged = True
        result['transfer_seconds'] = time.monotonic() - transfer_started
        env = dict(QT_QPA_PLATFORM='offscreen', PYTHONUNBUFFERED='1', PYTHONUTF8='1',
                   UV_PYTHON_INSTALL_DIR=workspace + '/python', UV_CACHE_DIR=workspace + '/cache',
                   PYTHONPATH=workspace + '/source:' + workspace + '/source/Python')
        def execute(argv, environment, timeout):
            return client.run_owned(vm, workspace, token, account['uid'],
                container.run(workspace, ['env', *(key+'='+value for key,value in environment.items()), *argv]) if container else argv,
                container.environment if container else environment, cancelled, timeout=timeout)
        if args.container_image:
            from build_manager.containers import RootlessContainer
            container = RootlessContainer('/var/tmp/build-manager-fedora-cache-'+str(account['uid']), account['uid'],
                                           'build-manager-'+token, args.container_image)
            result['container'] = dict(image=args.container_image, name=container.name, rootless=True,
                                       protections='default Podman; normal UID; browser sandbox retained')
            prepare_image = """import hashlib,json,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]); command=json.loads(sys.argv[2]); image=sys.argv[3]
definition=root/'source/Python/tests/platform/fedora43.Containerfile'
sha=hashlib.sha256(definition.read_bytes()).hexdigest()
probe=subprocess.run(command+['image','inspect',image],capture_output=True,text=True)
rows=json.loads(probe.stdout) if probe.returncode==0 else []
if not rows or rows[0].get('Config',{}).get('Labels',{}).get('build-manager.definition')!=sha:
 subprocess.run(command+['build','--label','build-manager.definition='+sha,'--tag',image,'--file',str(definition),str(definition.parent)],check=True,timeout=900)
 rows=json.loads(subprocess.check_output(command+['image','inspect',image],text=True))
reports=root/'reports';reports.mkdir(exist_ok=True)
(reports/'container-image.json').write_text(json.dumps(dict(image_id=rows[0]['Id'],definition_sha256=sha,architecture=rows[0]['Architecture'])))
"""
            image_code = client.run_owned(vm, workspace, token, account['uid'],
                ['python3','-c',prepare_image,workspace,json.dumps(container.command),args.container_image],
                container.environment,cancelled,timeout=1020)
            if image_code:
                raise RuntimeError('Rootless Fedora image preparation failed: '+str(image_code))
            image = json.loads(client.execute(vm,['python3','-c',
                'import pathlib,sys;print(pathlib.Path(sys.argv[1]).read_text())',workspace+'/reports/container-image.json']))
            container.image = image['image_id']
            result['container'].update(image)

        setup_started = time.monotonic()
        bootstrap = BOOTSTRAP if not container else '''import json,pathlib,platform,subprocess,sys
r=pathlib.Path('/etc/os-release').read_text()
if 'ID=fedora' not in r or 'VERSION_ID=43' not in r: raise ValueError('Expected Fedora43 container')
p=pathlib.Path(sys.argv[1])/'reports';p.mkdir(exist_ok=True)
(p/'container-environment.json').write_text(json.dumps(dict(os_release=r,architecture=platform.machine())))
subprocess.run(['uv','venv','--python','3.12.2','--seed',sys.argv[1]+'/environment'],check=True,timeout=600)
'''
        code = execute(['python3', '-c', bootstrap, workspace], env, 1020)
        result['setup_seconds'] = time.monotonic() - setup_started
        if code:
            result['status'] = 'cancelled' if cancelled.is_set() else 'failed'
            result['failure'] = 'Guest isolated interpreter setup failed: ' + str(code)
            return 1
        guest_python = workspace + '/environment/bin/python'
        if args.manager_checkout:
            from Scripts.guest_manager import stage_linux
            stage_linux(client, vm, workspace, token, account['uid'], account['gid'], args.manager_checkout, args.snapshot)
            setup = [guest_python, '-m', 'Scripts.guest_manager', '--checkout', workspace+'/manager', '--project', workspace+'/source']
        else:
            setup = [guest_python, 'Scripts/install_build_manager.py', '--from-pin', workspace+'/manager']
        env['LOGISTICS_MANAGER_CHECKOUT'] = workspace+'/manager'
        code = execute(setup, env, 600)
        if code:raise RuntimeError('Guest external-manager setup failed; verify the exact pinned source is available.')
        reports = workspace + '/reports'
        if args.pattern:
            suite, pattern = ('shared', args.pattern[7:]) if args.pattern.startswith('shared:') else ('desktop', args.pattern)
            phases = (Phase('environment', (guest_python, 'Python/tests/run_platform_checks.py', '--install', '--prepare-only', '--results-dir', reports),
                            workspace + '/source', timeout=600, environment=env, kind='setup'),
                      Phase('focused', (guest_python, 'dev.py', 'test', suite, pattern, '--python', guest_python),
                            workspace + '/source', timeout=900, environment=dict(env, LOGISTICS_REQUIRE_LOCALCRYPT_TESTS='1'), dependencies=('environment',)))
        else:
            phases = (Phase('platform', (guest_python, 'Python/tests/run_platform_checks.py', '--install', '--results-dir', reports),
                        workspace + '/source', timeout=3000, environment=env),
                  Phase('release-tooling', (guest_python, '-m', 'unittest', 'discover', '-s', '.github/scripts', '-v'),
                        workspace + '/source', timeout=300, environment=env))
        plan = Plan('Logistics', 'Focused Linux contracts' if args.pattern else 'Full local Linux platform checks', args.source_identity, phases,
                    workspace + '/operation', backend='Parallels ' + args.distribution)
        client.write_owned(vm, workspace, token, 'plan.json', json.dumps(plan.data()).encode(),
                           account['uid'], account['gid'])
        code = execute([guest_python, '-m', 'build_manager', workspace + '/plan.json', '--output', reports + '/manager'], env, 3400)
        result['status'] = 'cancelled' if cancelled.is_set() else 'passed' if code == 0 else 'failed'
        return int(code != 0)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result.update(status='failed', error=str(error))
        return 1
    finally:
        if container:
            try:
                cleanup = 'import os;os.setgid('+str(account['gid'])+');os.setuid('+str(account['uid'])+');exec('+repr(container.cleanup_script())+')'
                client.cleanup(vm, ['env', *(key+'='+value for key,value in container.environment.items()), 'python3', '-c', cleanup,
                                    json.dumps(container.command), container.name], timeout=45)
                result['container_removed'] = True
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                result.update(status='failed', container_cleanup_error=str(error))
        if transfer_attempted and not staged:
            try:
                staged = client.owned_exists(vm, workspace, token)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                result['cleanup_check_error'] = str(error)
        if staged:
            try:
                client.collect(vm, workspace, token, args.results / 'guest')
                collected = True
                evidence = args.results / 'guest/reports/manager/result.json'
                if evidence.is_file():
                    report = json.loads(evidence.read_text())
                    if report['source'] != args.source_identity or report['backend'] != 'Parallels ' + args.distribution:
                        raise ValueError('Retrieved guest report belongs to different source/backend.')
                    result['phases'] = report['phases']
                    result['guest_result'] = str(evidence)
                    if result['status'] == 'passed' and report['status'] != 'passed':
                        raise ValueError('Guest exit status disagrees with its required test result.')
                elif result['status'] == 'passed':
                    raise ValueError('A passing guest process did not produce its required result.')
            except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
                result.update(status='failed', retrieval_error=str(error))
            if collected:
                try:
                    client.remove(vm, workspace, token)
                    result['guest_workspace_removed'] = True
                except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                    result.update(status='failed', cleanup_error=str(error))
            else:
                result['guest_workspace_preserved_for_recovery'] = True
        result['seconds'] = time.monotonic() - started
        (args.results / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result), flush=True)
        if args.shutdown and original['status'] == 'stopped':
            client.shutdown(vm)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vm', required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--source-identity', type=json.loads, required=True)
    parser.add_argument('--distribution', choices=('ubuntu', 'fedora'), required=True)
    parser.add_argument('--container-image', default='')
    parser.add_argument('--shutdown', action='store_true')
    parser.add_argument('--pattern', default='')
    parser.add_argument('--manager-checkout', type=Path)
    args = parser.parse_args()
    code = run(args)
    report = json.loads((args.results / 'result.json').read_text())
    return code or int(report['status'] != 'passed')


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('VM backend failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
