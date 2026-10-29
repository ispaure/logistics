"""Materialize owned Logistics source snapshots without copying private inputs."""
import hashlib
import json
import os
import stat
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from commonUtils.runtime.streams import file_sha256

from build_manager.locking import workspace_lock


# These are private runtime references bound by mobile_plan, never source inputs.
PRIVATE_RUNTIME_NAMES = ('.venv', '.tools', '.device.json', '.testflight-auth.json', '.android-beta')


def exclude_private_runtime_references(snapshot):
    snapshot = Path(snapshot)
    excluded = snapshot / '.git/info/exclude'
    if snapshot.is_symlink() or any(path.is_symlink() for path in (snapshot/'.git',snapshot/'.git/info',excluded)):
        raise ValueError('Snapshot Git metadata must not be linked.')
    if not (snapshot/'.git').is_dir():
        raise ValueError('Snapshot requires owned Git metadata.')
    rules = ['/' + (Path('mobile_build') / name).as_posix() for name in PRIVATE_RUNTIME_NAMES]
    # Retention pins are workspace metadata, not application source. Pinning an
    # accepted build must not make the next platform's snapshot reuse fail.
    rules.append('.keep')
    current = excluded.read_text() if excluded.is_file() else ''
    missing = [rule for rule in rules if rule not in current.splitlines()]
    if missing:
        with excluded.open('a') as stream:
            stream.write('\n' + '\n'.join(missing) + '\n')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, timeout=60).strip()


def working_paths(root):
    paths = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-c', '-o', '--exclude-standard', '-z'])
    return sorted({os.fsdecode(value) for value in paths.split(b'\0') if value})


def check_source_path(root, path):
    # A tracked child can now sit below a replaced parent symlink. Check the
    # whole path before hashing or copying, not just the final directory entry.
    if ((path.is_symlink() and Path(os.readlink(path)).is_absolute())
            or not path.resolve().is_relative_to(root.resolve())):
        raise ValueError('Source symlink escapes the checkout: ' + path.relative_to(root).as_posix())


def working_fingerprint(root, commit):
    digest = hashlib.sha256(commit.encode())
    for name in working_paths(root):
        path = root / name
        check_source_path(root, path)
        digest.update(os.fsencode(name) + b'\0')
        if path.is_symlink():
            digest.update(b'link:' + os.fsencode(os.readlink(path)))
        elif path.is_file():
            digest.update(b'executable:' if path.stat().st_mode & stat.S_IXUSR else b'file:')
            digest.update(bytes.fromhex(file_sha256(path)))
        elif not path.exists():
            digest.update(b'deleted')
        else:
            digest.update(b'directory')
    return digest.hexdigest()


def overlay_working_tree(root, destination, *, skip=()):
    names = [name for name in working_paths(root) if name not in skip]
    for name in names:
        source, target = root / name, destination / name
        check_source_path(root, source)
        if not source.exists() and not source.is_symlink():
            remove(target)
        elif target.is_symlink() or (target.exists() and source.is_dir() != target.is_dir()):
            remove(target)
    for name in names:
        source, target = root / name, destination / name
        check_source_path(root, source)
        if source.is_symlink() or source.is_file():
            for parent in reversed(target.parents):
                if parent == destination or destination in parent.parents:
                    if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                        remove(parent)
                    parent.mkdir(exist_ok=True)
            if source.is_symlink():
                remove(target)
                target.symlink_to(os.readlink(source))
            else:
                shutil.copy2(source, target)


def require_committed_source(source, operation):
    if source.get('dirty') or source.get('commonUtils_dirty'):
        raise ValueError(operation + ' requires committed source in Logistics and commonUtils. '
                         'Use a local development build to test edits, or choose Latest commit to exclude them.')


def identity(root, revision='working-tree'):
    root = Path(root)
    committed = 'HEAD' if revision == 'working-tree' else revision
    commit = git(root, 'rev-parse', committed + '^{commit}')
    dependency = git(root, 'ls-tree', commit, 'Python/commonUtils').split()[2]
    dirty = bool(git(root, 'status', '--porcelain')) if revision == 'working-tree' else False
    digest = hashlib.sha256(commit.encode())
    if revision == 'working-tree':
        digest.update(bytes.fromhex(working_fingerprint(root, commit)))
        pinned = dependency
        dependency = git(root / 'Python/commonUtils', 'rev-parse', 'HEAD')
        shared_dirty = bool(git(root / 'Python/commonUtils', 'status', '--porcelain'))
        shared_fingerprint = working_fingerprint(root / 'Python/commonUtils', dependency)
        digest.update(bytes.fromhex(shared_fingerprint))
        dirty = dirty or shared_dirty or dependency != pinned
    else:
        shared_dirty, shared_fingerprint = False, None
    return dict(logistics_commit=commit, commonUtils_commit=dependency, dirty=dirty,
                commonUtils_dirty=shared_dirty, commonUtils_fingerprint=shared_fingerprint,
                fingerprint=digest.hexdigest(), selection=revision)


def materialize(root, destination, revision='working-tree', *, expected=None):
    destination = Path(destination)
    with workspace_lock(destination.with_suffix('.lock')):
        return _materialize(root, destination, revision, expected=expected)


def _materialize(root, destination, revision, *, expected=None):
    root, destination = Path(root), Path(destination)
    before = identity(root, revision)
    if expected is not None and any(before[key] != expected.get(key) for key in ('logistics_commit', 'commonUtils_commit', 'dirty', 'fingerprint')):
        raise ValueError('Source changed after the shared planning capture; prepare a fresh plan.')
    if destination.exists():
        exclude_private_runtime_references(destination)
        metadata = destination / '.manager-source.json'
        if metadata.is_file():
            saved = json.loads(metadata.read_text())
            # A branch, HEAD and its full SHA can name identical committed bytes.
            # Keep the original provenance label while comparing immutable identity.
            comparable = dict(saved.get('source', {}))
            comparable['selection'] = before['selection']
            if comparable == before and saved.get('snapshot_fingerprint') == identity(destination)['fingerprint']:
                os.utime(destination, None)
                return before
        raise ValueError('Snapshot destination already belongs to different source.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='source-', dir=destination.parent) as temporary:
        snapshot = Path(temporary) / 'source'
        subprocess.run(['git', 'clone', '--quiet', '--no-local', '--no-checkout', str(root), str(snapshot)], check=True, timeout=120)
        subprocess.run(['git', '-C', str(snapshot), 'checkout', '--quiet', '--detach', before['logistics_commit']], check=True, timeout=60)
        shared = snapshot / 'Python/commonUtils'
        if shared.exists():
            shared.rmdir()
        subprocess.run(['git', 'clone', '--quiet', '--no-local', '--no-checkout', str(root / 'Python/commonUtils'), str(shared)], check=True, timeout=120)
        subprocess.run(['git', '-C', str(shared), 'checkout', '--quiet', '--detach', before['commonUtils_commit']], check=True, timeout=60)
        if revision == 'working-tree':
            overlay_working_tree(root, snapshot, skip=('Python/commonUtils',))
            overlay_working_tree(root / 'Python/commonUtils', shared)
        if identity(root, revision) != before:
            raise RuntimeError('Source changed during snapshot preparation; inspect a fresh plan.')
        exclude_private_runtime_references(snapshot)
        with (snapshot / '.git/info/exclude').open('a') as stream:
            stream.write('\n.manager-source.json\n')
        captured = identity(snapshot)
        if revision == 'working-tree' and captured['fingerprint'] != before['fingerprint']:
            raise RuntimeError('Snapshot bytes differ from the captured source; prepare a fresh plan.')
        (snapshot / '.manager-source.json').write_text(json.dumps(dict(source=before,
            snapshot_fingerprint=captured['fingerprint']), indent=2) + '\n')
        snapshot.rename(destination)
    return before


def source_members(snapshot):
    members = ['.git', '.manager-source.json']
    for relative in ('', 'Python/commonUtils'):
        folder = snapshot / relative
        names = subprocess.check_output(['git', '-C', str(folder), 'ls-files', '-c', '-o', '--exclude-standard', '-z']).split(b'\0')
        members.extend(str(Path(relative) / os.fsdecode(name)) for name in names if name and ((folder / os.fsdecode(name)).is_file() or (folder / os.fsdecode(name)).is_symlink()))
        if relative:
            members.append(relative + '/.git')
    return sorted(set(members))


def remove(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
