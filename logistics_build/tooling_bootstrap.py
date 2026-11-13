"""Standard-library-only, explicit setup for this checkout's pinned tooling."""
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
import argparse
import errno
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
_MUTATION = ContextVar('tooling_mutation', default=None)


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
    'native_tooling': 'Native prerequisite preparation failed. Check access to go.dev and files.pythonhosted.org and run dev.py setup mobile. Preserve conflicting mobile_build/.tools/go or release-wheels folders before moving them aside and retrying Update project tooling.',
    'blocked': 'Tooling readiness could not be checked. Inspect the project environments and retry Project tooling readiness.',
    'unfinished_mutation': 'An earlier environment change is unfinished. Explicitly Update project tooling to repair verified stopped work; an unverified interruption requires a host restart first. Do not remove its recovery record.',
    'boot_identity': 'The host boot identity could not be verified. Restore access to the operating system boot identifier before changing project environments.',
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


def intent_path(root):
    return private(root) / 'tooling-mutation.json'


def boot_identity():
    try:
        if sys.platform == 'darwin':
            value = subprocess.run(['/usr/sbin/sysctl', '-n', 'kern.bootsessionuuid'], check=True,
                                   capture_output=True, text=True, timeout=3).stdout.strip()
        else:
            value = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        return str(uuid.UUID(value))
    except (OSError, ValueError, subprocess.SubprocessError):
        raise BootstrapError('boot_identity') from None


def read_intent(root):
    path = intent_path(root)
    if not owned_path(root, path):
        raise BootstrapError('unfinished_mutation')
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text())
        if (not isinstance(value, dict) or value.get('schema') != 1
                or value.get('root') != str(Path(root).resolve())
                or value.get('mode') not in ('sync', 'repair')
                or not isinstance(value.get('groups'), list)):
            raise ValueError
        for field in ('nonce', 'boot_id'):
            if not isinstance(value.get(field), str) or str(uuid.UUID(value[field])) != value[field]:
                raise ValueError
        if any(not isinstance(group, dict)
               or any(type(group.get(field)) is not int or group[field] <= 0 for field in ('pgid', 'sid'))
               for group in value['groups']):
            raise ValueError
        if 'cleanup' in value and value['cleanup'] != cleanup_proof(value):
            raise ValueError
        return value
    except (OSError, ValueError, KeyError, TypeError):
        raise BootstrapError('unfinished_mutation') from None


def cleanup_proof(value):
    return dict(nonce=value['nonce'], boot_id=value['boot_id'], groups=value['groups'])


def save_intent(state):
    current = read_intent(state['root'])
    if current is None or current['nonce'] != state['value']['nonce']:
        raise BootstrapError('unfinished_mutation')
    atomic_json(intent_path(state['root']), state['value'])


def clear_intent(root, nonce):
    state = _MUTATION.get()
    if (state is None or not state.get('verified') or not state['retired']
            or state['value']['nonce'] != nonce or Path(state['root']) != Path(root)):
        raise BootstrapError('unfinished_mutation')
    current = read_intent(root)
    if current is None or current['nonce'] != nonce or current.get('cleanup') != cleanup_proof(current):
        raise BootstrapError('unfinished_mutation')
    intent_path(root).unlink()
    sync_directory(intent_path(root).parent)


@contextmanager
def mutation_intent(root, mode, *, recover=False):
    if os.name != 'posix':
        yield
        return
    previous = read_intent(root)
    boot = boot_identity()
    if previous is not None and (not recover or (previous['boot_id'] == boot and 'cleanup' not in previous)):
        raise BootstrapError('unfinished_mutation')
    value = dict(schema=1, root=str(Path(root).resolve()), nonce=str(uuid.uuid4()),
                 boot_id=boot, mode=mode, groups=[])
    if previous is not None:
        value['recovery_nonce'] = previous['nonce']
    atomic_json(intent_path(root), value)
    state = dict(root=root, value=value, retired=True, uncertain=False)
    token = _MUTATION.set(state)
    try:
        yield
        if not state['retired'] or state['uncertain']:
            raise BootstrapError('unfinished_mutation')
        state['verified'] = True
    finally:
        try:
            if state['retired'] and not state['uncertain']:
                value['cleanup'] = cleanup_proof(value)
                save_intent(state)
                if state.get('verified'):
                    clear_intent(root, value['nonce'])
        finally:
            _MUTATION.reset(token)


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
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def sync_directory(path):
    if os.name == 'posix':
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


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


@contextmanager
def cancellation_scope(*, cleaning=False):
    """Unwind leases on bridge TERM; repeated cancellation cannot interrupt cleanup."""
    state = dict(launching=False, cancelled=False)
    if threading.current_thread() is not threading.main_thread():
        yield state
        return
    previous = {}
    def cancel(signum, frame):
        signal.signal(signum, signal.SIG_IGN)
        if state['launching']:
            state['cancelled'] = True
            return
        raise KeyboardInterrupt
    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, signal.SIG_IGN if cleaning else cancel)
        yield state
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _retire(process):
    """Retire only our child tree, within ten seconds, before releasing its lease."""
    with cancellation_scope(cleaning=True):
        if os.name == 'nt':
            # In a bridge this tree also remains inside the SDK's owning job.
            killer = subprocess.Popen(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                killer.wait(timeout=4)
            except subprocess.TimeoutExpired:
                killer.kill()
                killer.wait(timeout=1)
        else:
            def send(sig):
                try:
                    os.killpg(process.pid, sig)
                    return True
                except ProcessLookupError:
                    return False
                except PermissionError:
                    if sig == 0:
                        # Darwin may deny the existence probe while an exiting
                        # group is being reaped. Never treat that as retired.
                        return True
                    raise
            if send(signal.SIGTERM):
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    process.poll()  # Reap the direct child even if descendants remain.
                    if not send(0):
                        break
                    time.sleep(.02)
                send(signal.SIGKILL)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            # An inherited pipe must never turn cancellation into an unbounded wait.
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            raise
        if os.name == 'posix':
            deadline = time.monotonic() + 2
            while send(0):
                if time.monotonic() >= deadline:
                    return False
                time.sleep(.02)
        return True


def run_command(args, *, timeout=None, check=False, capture_output=False, **kwargs):
    """Own a child PGID, never a new SID that could escape the SDK bridge owner."""
    options = (dict(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == 'nt'
               else dict(process_group=0))
    if capture_output:
        options.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with cancellation_scope() as cancellation:
        # Deliver cancellation only once the child's cleanup finally is installed.
        # Do not block signals: the child must inherit an unblocked signal mask.
        cancellation['launching'] = True
        state = _MUTATION.get()
        if state is not None:
            # Constructor failure may occur after a child has started. Never
            # infer no-exec from an exception or issue a cleanup receipt for it.
            state['uncertain'] = True
            state['value'].pop('cleanup', None)
            save_intent(state)
        process = subprocess.Popen([str(arg) for arg in args], text=True, **options, **kwargs)
        try:
            if state is not None:
                state['uncertain'] = False
                state['value']['groups'].append(dict(pgid=process.pid, sid=os.getsid(0)))
                save_intent(state)
            cancellation['launching'] = False
            if cancellation['cancelled']:
                raise KeyboardInterrupt
            stdout, stderr = process.communicate(timeout=timeout)
            result = subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
            if check:
                result.check_returncode()
            return result
        finally:
            state = _MUTATION.get()
            previously_retired = state['retired'] if state is not None else True
            if state is not None:
                state['retired'] = False
            retired = _retire(process)
            if state is not None:
                state['retired'] = previously_retired and retired
                if not state['retired']:
                    raise BootstrapError('unfinished_mutation')


def run(args, **kwargs):
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
    for key in ('PYTHONPATH', 'PYTHONHOME'):
        environment.pop(key, None)
    return run_command(args, env=environment, capture_output=True,
                       check=True, timeout=180, **kwargs).stdout.rstrip()


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
               installed_revision='', source_checkout='')
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
    for base in (private(root) / 'workspaces', private(root) / 'snapshots',
                 Path(root) / 'test-results', Path(root) / 'tmp/runs/scratch'):
        if owned_path(root, base) and base.is_dir():
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
    if os.name == 'posix':
        state = _MUTATION.get()
        try:
            pending = read_intent(root)
            if pending is not None and (state is None or state['value']['nonce'] != pending['nonce']):
                raise BootstrapError('unfinished_mutation')
        except BootstrapError:
            return dict(ready=False, status='blocked', reason='unfinished_mutation',
                        message=MESSAGES['unfinished_mutation'], declared_revision=None, environments=[])
    declared = pin(root)
    rows = [inspect_environment(root, *item, declared) for item in environments(root)]
    ready = all(row['ready'] for row in rows)
    blocked = any(not interpreter.is_file() or not owned_path(root, folder)
                  for _, folder, interpreter in environments(root))
    from logistics_build.native_tooling import status as native_status
    native = native_status(root)
    message = ('Project manager SDK is ready. ' if ready else MESSAGES['environments'] if blocked else 'Update project tooling to the declared revision. ')
    if native['applicable']:
        message += native['message'] + ' Explicit Update project tooling also prepares pinned Go and the pure langdetect wheel.'
    return dict(native=native, action_description='Repair the pinned manager SDK; with a supported mobile environment, also prepare pinned Go and the pure Python app wheel.',
        ready=ready, status='ready' if ready else 'blocked' if blocked else 'needs_update',
        message=message,
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
        with mutation_intent(root, 'repair', recover=True):
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
    repair_native(root)
    marker = enrollment(root)
    marker.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(marker, dict(schema=1, root=str(root)))
    return status(root)

def repair_native(root):
    from logistics_build.native_tooling import host_key, declared
    if host_key() not in declared()['go']:
        return
    mobile = next(interpreter for name, _, interpreter in environments(root) if name == 'mobile')
    if mobile.is_file():
        try:
            state = _MUTATION.get()
            if os.name == 'posix' and state is None:
                raise BootstrapError('unfinished_mutation')
            nonce = state['value']['nonce'] if state is not None else str(uuid.uuid4())
            capability = private(root) / 'native-setup-owner.json'
            if not owned_path(root, capability):
                raise BootstrapError('linked_path')
            if os.name != 'posix':
                atomic_json(capability, dict(schema=1, root=str(Path(root).resolve()), nonce=nonce))
            run([mobile, Path(root) / 'logistics_build/native_tooling.py', '--root', root, '--owner-nonce', nonce], cwd=root)
            # Successful return includes owning run_command's bounded cleanup.
            # A failed/uncertain launch may leave an inert record; it grants no
            # authority without the held environment lock and matching nonce.
            if os.name != 'posix' and capability.is_file() and capability.stat().st_size <= 4096:
                value = json.loads(capability.read_text())
                if value == dict(schema=1, root=str(Path(root).resolve()), nonce=nonce):
                    capability.unlink()
        except subprocess.SubprocessError:
            raise BootstrapError('native_tooling') from None


def after_sync(root=ROOT):
    """Only a previous explicit tooling repair enrolls automatic restoration."""
    return update(root, confirmed=True) if enrolled(root) else None


@contextmanager
def environment_sync(root=ROOT):
    """Hold the shared environment lock across sync and enrolled restoration."""
    root = Path(root).resolve()
    if any(not owned_path(root, path) for path in (lock_path(root), *(folder for _, folder, _ in environments(root)))):
        raise BootstrapError('linked_path')
    with mutation_guard(root):
        with mutation_intent(root, 'sync'):
            restore = enrolled(root)
            yield
            if not restore:
                return
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
            return run_command(command, check=True).returncode
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
