"""Standard-library-only, explicit setup for this checkout's pinned tooling."""
from contextlib import contextmanager, ExitStack
import argparse
import errno
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


MESSAGES = {
    'confirmation': 'Confirm Update project tooling before making changes.',
    'environments': 'Set up both Logistics-owned desktop and mobile environments, then update project tooling.',
    'borrowed_environment': 'Use Logistics-owned virtual environments; borrowed, global and Ally interpreters cannot receive project tooling.',
    'active_workflow': 'A Logistics workflow is active. Wait for it to finish or stop it through its owning manager, then update tooling.',
    'changed_checkout': 'The owned tooling checkout or a pinned submodule has changes. Preserve and move that checkout aside, then update again; it will not be reset.',
    'ownership': 'The existing tooling folder lacks matching ownership proof. Preserve and move it aside before updating.',
    'linked_path': 'Linked tooling paths are not eligible. Use project-owned environment and tooling directories.',
    'pin': 'The declared manager pin is invalid or missing. Update the project to a valid published dependency pin before retrying.',
    'verification': 'Installed tooling did not verify in both environments. Inspect Project tooling readiness, then update again.',
    'install': 'Pinned tooling installation failed. Check Git access and Python build prerequisites, then update again.',
    'blocked': 'Tooling readiness could not be checked. Inspect the project environments and retry Project tooling readiness.',
}


class BootstrapError(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(MESSAGES[reason])


class ActiveWorkflowError(RuntimeError):
    reason = 'active_workflow'

    def __init__(self):
        super().__init__(MESSAGES[self.reason])


def private(root):
    return Path(root) / 'mobile_build/.tools/build-manager'


def lock_path(root):
    return private(root) / 'tooling-environment.lock'


def enrollment(root):
    return private(root) / 'tooling/enrolled.json'


def enrolled(root):
    marker = enrollment(root)
    return (marker.is_file() and not linked(marker)
            and json.loads(marker.read_text()) == dict(schema=1, root=str(Path(root).resolve())))


def atomic_json(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix='.tooling-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def pin(root):
    try:
        value = json.loads((Path(root) / 'build-manager-dependency.json').read_text())
    except (OSError, ValueError):
        raise BootstrapError('pin') from None
    if (not isinstance(value, dict) or value.get('schema') != 1 or value.get('adapter_api') != 1
            or not isinstance(value.get('revision'), str) or not isinstance(value.get('repository'), str)
            or not re.fullmatch('[0-9a-f]{40}', value.get('revision', ''))
            or not re.fullmatch(r'https://github\.com/[\w.-]+/[\w.-]+(?:\.git)?', value.get('repository', ''))):
        raise BootstrapError('pin')
    return value


def environments(root):
    root = Path(root)
    suffix = 'Scripts/python.exe' if os.name == 'nt' else 'bin/python'
    return [(name, root / folder, root / folder / suffix) for name, folder in
            [('desktop', '.venv'), ('mobile', 'mobile_build/.venv')]]


def linked(path):
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def owned_path(root, path):
    original = Path(root).absolute()
    relative = Path(path).absolute().relative_to(original)
    root = original.resolve()
    path = root / relative
    return not any(linked(part) for part in (path, *path.parents) if part != root and root in part.parents)


def run(args, **kwargs):
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
    for key in ('PYTHONPATH', 'PYTHONHOME'):
        environment.pop(key, None)
    return subprocess.run([str(arg) for arg in args], env=environment, capture_output=True,
                          text=True, check=True, timeout=180, **kwargs).stdout.rstrip()


def git(checkout, *args):
    return run(['git', '-C', checkout, *args])


def verify_checkout(checkout, declared):
    if (git(checkout, 'rev-parse', 'HEAD') != declared['revision']
            or git(checkout, 'config', '--get', 'remote.origin.url') != declared['repository']
            or git(checkout, 'status', '--porcelain', '--untracked-files=all')):
        raise BootstrapError('changed_checkout')
    modules = git(checkout, 'submodule', 'status', '--recursive').splitlines()
    if not modules or any(not row.startswith(' ') for row in modules):
        raise BootstrapError('changed_checkout')
    for row in modules:
        module = Path(checkout) / row.split()[1]
        if git(module, 'status', '--porcelain', '--untracked-files=all'):
            raise BootstrapError('changed_checkout')


_INSPECT = r'''
import importlib.util,json
from pathlib import Path
spec=importlib.util.find_spec('build_manager')
path=Path(spec.origin).resolve() if spec and spec.origin else None
checkout=None
if path:
 for parent in path.parents:
  if (parent/'.git').exists():
   checkout=str(parent);break
import sys
print(json.dumps(dict(source_checkout=checkout,prefix=sys.prefix)))
'''


def validate_interpreters(targets):
    for _, folder, interpreter in targets:
        value = json.loads(run([interpreter, '-I', '-c',
            'import json,sys; print(json.dumps(dict(prefix=sys.prefix)))']))
        if Path(value['prefix']).resolve() != folder.resolve():
            raise BootstrapError('borrowed_environment')


def inspect_environment(root, name, folder, interpreter, declared):
    row = dict(name=name, interpreter=str(interpreter), ready=False,
               installed_revision=None, source_checkout=None)
    if not owned_path(root, folder) or not interpreter.is_file():
        return row
    try:
        inspected = json.loads(run([interpreter, '-I', '-c', _INSPECT]))
        if Path(inspected['prefix']).resolve() != folder.resolve():
            return row
        checkout = inspected['source_checkout']
        if checkout:
            row['source_checkout'] = checkout
            row['installed_revision'] = git(checkout, 'rev-parse', 'HEAD')
            verify_checkout(checkout, declared)
            row['ready'] = True
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return row


@contextmanager
def file_lock(path, *, create=False):
    """Use the same OS advisory locks as the SDK without importing it."""
    path = Path(path)
    if linked(path):
        raise BootstrapError('linked_path')
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b' if create else 'r+b') as stream:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise ActiveWorkflowError() from error
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                raise ActiveWorkflowError() from error
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def operation_locks(root):
    # Existing lock files alone are harmless. Probe actual advisory ownership.
    for base in (private(root) / 'workspaces', private(root) / 'snapshots', Path(root) / 'test-results'):
        if base.is_dir():
            for path in base.rglob('*.lock'):
                if path.name in ('operation.lock', 'supervisor.lock') or path.name.endswith(('.operation.lock', '.retention.lock')):
                    if owned_path(root, path):
                        yield path


@contextmanager
def mutation_guard(root):
    with ExitStack() as stack:
        stack.enter_context(file_lock(lock_path(root), create=True))
        for path in sorted(set(operation_locks(root))):
            if path.is_file():
                stack.enter_context(file_lock(path))
        yield


def status(root=ROOT):
    declared = pin(root)
    rows = [inspect_environment(root, *item, declared) for item in environments(root)]
    ready = all(row['ready'] for row in rows)
    blocked = any(not interpreter.is_file() or not owned_path(root, folder)
                  for _, folder, interpreter in environments(root))
    return dict(ready=ready, status='ready' if ready else 'blocked' if blocked else 'needs_update',
        message='Project tooling is ready.' if ready else MESSAGES['environments'] if blocked else 'Update project tooling to the declared revision.',
        declared_revision=declared['revision'], environments=rows)


def update(root=ROOT, *, confirmed=False):
    if confirmed is not True:
        raise BootstrapError('confirmation')
    root = Path(root).resolve()
    declared = pin(root)
    targets = environments(root)
    if any(not owned_path(root, folder) or not interpreter.is_file() for _, folder, interpreter in targets):
        raise BootstrapError('environments')
    checkout = private(root) / 'tooling' / declared['revision']
    if any(not owned_path(root, path) for path in (checkout, lock_path(root), enrollment(root),
                                                        checkout.with_suffix('.ownership.json'))):
        raise BootstrapError('linked_path')
    with mutation_guard(root):
        return _repair_locked(root, declared, targets)


def _repair_locked(root, declared, targets):
    validate_interpreters(targets)
    checkout = private(root) / 'tooling' / declared['revision']
    if any(not owned_path(root, path) for path in (checkout, enrollment(root), checkout.with_suffix('.ownership.json'))):
        raise BootstrapError('linked_path')
    installer = root / 'logistics_build/install_build_manager.py'
    checkout.parent.mkdir(parents=True, exist_ok=True)
    proof = checkout.with_suffix('.ownership.json')
    identity = dict(root=str(root), **declared)
    if checkout.exists() and (not proof.is_file() or linked(proof) or json.loads(proof.read_text()) != identity):
        raise BootstrapError('ownership')
    if not checkout.exists():
        atomic_json(proof, identity)
    for _, _, interpreter in targets:
        if not checkout.exists():
            run([interpreter, installer, '--from-pin', checkout])
        else:
            verify_checkout(checkout, declared)
            run([interpreter, installer, checkout])
        verify_checkout(checkout, declared)
    result = status(root)
    if not result['ready']:
        raise BootstrapError('verification')
    marker = enrollment(root)
    marker.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(marker, dict(schema=1, root=str(root)))
    return result

def after_sync(root=ROOT):
    """Only a previous explicit tooling repair enrolls automatic restoration."""
    return update(root, confirmed=True) if enrolled(root) else None


@contextmanager
def environment_sync(root=ROOT):
    """Hold the shared environment lock across sync and enrolled restoration."""
    if not enrolled(root):
        yield
        return
    root = Path(root).resolve()
    if any(not owned_path(root, path) for path in (lock_path(root), *(folder for _, folder, _ in environments(root)))):
        raise BootstrapError('linked_path')
    with mutation_guard(root):
        yield
        targets = environments(root)
        if any(not owned_path(root, folder) or not interpreter.is_file() for _, folder, interpreter in targets):
            raise BootstrapError('environments')
        _repair_locked(root, pin(root), targets)


def handle(root, action, values):
    """Bounded protocol errors stay usable even when no SDK can be imported."""
    try:
        if not isinstance(values, dict):
            raise ValueError('Invalid tooling values.')
        return status(root) if action == 'tooling_status' else update(root, confirmed=values.get('confirmed') is True)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        reason = getattr(error, 'reason', 'install' if isinstance(error, subprocess.SubprocessError) else 'blocked')
        try:
            declared = pin(root)['revision']
        except (OSError, ValueError):
            declared = None
        return dict(ready=False, status='blocked', reason=reason, message=MESSAGES[reason],
                    declared_revision=declared, environments=[])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'update', 'after-sync', 'sync'])
    parser.add_argument('--root', '--project-root', dest='root', type=Path, default=ROOT)
    parser.add_argument('--venv', type=Path)
    parser.add_argument('--confirmed', action='store_true')
    args, command = parser.parse_known_args()
    if args.action == 'sync':
        if command[:1] == ['--']:
            command = command[1:]
        if not command or args.venv is None:
            parser.error('sync requires --venv and -- ORIGINAL_UV_ARGV')
        if args.venv.absolute() not in [folder.absolute() for _, folder, _ in environments(args.root)]:
            parser.error('sync must select a project-owned desktop or mobile environment')
        with environment_sync(args.root):
            return subprocess.run(command, check=True).returncode
    if command:
        parser.error('Unexpected tooling arguments')
    result = (status(args.root) if args.action == 'status' else
              update(args.root, confirmed=args.confirmed) if args.action == 'update' else after_sync(args.root))
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        reason = getattr(error, 'reason', 'install' if isinstance(error, subprocess.SubprocessError) else 'blocked')
        print(MESSAGES[reason], file=sys.stderr)
        raise SystemExit(1)
