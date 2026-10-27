"""Explicit exact-pin manager transfer for isolated Logistics guest environments."""
import argparse
import base64
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile


def focused_command(python, pattern, manager):
    """Route explicit diagnostic patterns; complete platform gates stay unchanged."""
    if pattern.startswith('manager:'):
        selected = pattern.removeprefix('manager:')
        if not selected or any(value in selected for value in ('/', '\\', '..')):
            raise ValueError('Manager focus requires a test filename pattern.')
        # Use the exact project-pinned checkout already installed in this guest.
        return (python, '-m', 'unittest', 'discover', '-s',
                str(manager).rstrip('/\\') + '/Python/tests', '-p', selected, '-v')
    suite, selected = ('shared', pattern[7:]) if pattern.startswith('shared:') else ('desktop', pattern)
    return (python, 'dev.py', 'test', suite, selected, '--python', python)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, timeout=60).strip()


def verify(checkout, project, *, pinned_source=False):
    checkout, project = Path(checkout).resolve(), Path(project)
    pin = json.loads((project/'build-manager-dependency.json').read_text())['revision']
    if not pinned_source and git(checkout, 'rev-parse', 'HEAD') != pin:
        raise ValueError('Explicit manager checkout does not match the project dependency pin.')
    try:
        if git(checkout, 'cat-file', '-t', pin) != 'commit':
            raise ValueError('Declared manager pin is not a commit.')
        shared = git(checkout, 'ls-tree', pin, 'Python/commonUtils').split()[2]
        git(checkout/'Python/commonUtils', 'cat-file', '-e', shared+'^{commit}')
    except (subprocess.CalledProcessError, IndexError) as error:
        raise ValueError('Explicit manager sources lack the declared project/dependency commits.') from error
    if not pinned_source and git(checkout/'Python/commonUtils', 'rev-parse', 'HEAD') != shared:
        raise ValueError('Manager commonUtils does not match its real pinned submodule.')
    for folder in (checkout, checkout/'Python/commonUtils'):
        if git(folder, 'status', '--porcelain', '--untracked-files=no'):
            raise ValueError('Commit manager/dependency edits before guest transfer.')
    return pin, shared


def archive(checkout, project, kind):
    from Scripts.build_retention import scratch
    checkout = Path(checkout).resolve()
    pin, shared = verify(checkout, project, pinned_source=True)
    stream = io.BytesIO()
    with scratch(Path(project)) as workspace:
        source = workspace/'manager'
        for target, origin, revision in ((source, checkout, pin),
                (source/'Python/commonUtils', checkout/'Python/commonUtils', shared)):
            target.mkdir(parents=True, exist_ok=True)
            subprocess.run(['git', 'init', '--quiet', str(target)], check=True, timeout=30)
            subprocess.run(['git', '-C', str(target), 'fetch', '--quiet', '--depth', '1', '--no-tags', origin.as_uri(), revision], check=True, timeout=120)
            subprocess.run(['git', '-C', str(target), 'checkout', '--quiet', '--detach', 'FETCH_HEAD'], check=True, timeout=60)
        if kind == 'zip':
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as output:
                for path in sorted(source.rglob('*')):
                    output.write(path, path.relative_to(source).as_posix())
        elif kind == 'tar':
            with tarfile.open(fileobj=stream, mode='w:gz') as output:
                for path in sorted(source.iterdir()): output.add(path, arcname=path.name)
        else:
            raise ValueError('Choose zip or tar manager transfer.')
    return stream.getvalue()


def stage_linux(client, vm, workspace, token, uid, gid, checkout, project):
    from build_manager.parallels import OWNED
    payload = archive(checkout, project, 'tar')
    script = OWNED + """
import base64,io,os,tarfile
manager=path/'manager'
with tarfile.open(fileobj=io.BytesIO(base64.b64decode(sys.stdin.buffer.read(),validate=True)),mode='r:gz') as archive:
 archive.extractall(manager,filter='data')
for folder,dirs,files in os.walk(manager):
 os.chown(folder,int(sys.argv[3]),int(sys.argv[4]))
 for name in files: os.chown(os.path.join(folder,name),int(sys.argv[3]),int(sys.argv[4]),follow_symlinks=False)
"""
    client.execute_idempotent(vm, ['python3','-c',script,workspace,token,str(uid),str(gid)], data=base64.b64encode(payload), timeout=180)
    return workspace+'/manager'


def install(checkout, project):
    verify(checkout, project)
    subprocess.run([sys.executable, str(Path(project)/'Scripts/install_build_manager.py'), str(checkout)], check=True, timeout=180)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    args = parser.parse_args()
    install(args.checkout, args.project)
