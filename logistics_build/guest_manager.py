"""Explicit exact-pin manager transfer for isolated Logistics guest environments."""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys


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


def dependency_pin(project):
    return json.loads((Path(project) / 'build-manager-dependency.json').read_text())['revision']


def verify(checkout, project, *, pinned_source=False):
    from build_manager.dependency_sources import verify as verify_source
    return verify_source(checkout, dependency_pin(project), pinned_source=pinned_source)


def archive(checkout, project, kind):
    from build_manager.dependency_sources import archive as source_archive
    from logistics_build.build_retention import scratch
    with scratch(Path(project)) as workspace:
        return source_archive(checkout, dependency_pin(project), kind, workspace)


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
    subprocess.run([sys.executable, str(Path(project)/'logistics_build/install_build_manager.py'), str(checkout)], check=True, timeout=180)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkout', type=Path, required=True)
    parser.add_argument('--project', type=Path, required=True)
    args = parser.parse_args()
    install(args.checkout, args.project)
