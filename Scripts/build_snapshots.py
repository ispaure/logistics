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
    current = excluded.read_text() if excluded.is_file() else ''
    missing = [rule for rule in rules if rule not in current.splitlines()]
    if missing:
        with excluded.open('a') as stream:
            stream.write('\n' + '\n'.join(missing) + '\n')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, timeout=60).strip()


def identity(root, revision='working-tree'):
    root = Path(root)
    committed = 'HEAD' if revision == 'working-tree' else revision
    commit = git(root, 'rev-parse', committed + '^{commit}')
    dependency = git(root, 'ls-tree', commit, 'Python/commonUtils').split()[2]
    dirty = bool(git(root, 'status', '--porcelain')) if revision == 'working-tree' else False
    digest = hashlib.sha256(commit.encode())
    if revision == 'working-tree':
        paths = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-c', '-o', '--exclude-standard', '-z']).split(b'\0')
        for encoded in sorted(set(paths)):
            if not encoded:
                continue
            name = os.fsdecode(encoded)
            path = root / name
            digest.update(encoded)
            if path.is_symlink():
                link = os.readlink(path)
                if Path(link).is_absolute() or not (path.parent / link).resolve().is_relative_to(root.resolve()):
                    raise ValueError('Source symlink escapes the checkout: ' + name)
                digest.update(b'link:' + os.fsencode(link))
            elif path.is_file():
                digest.update(b'executable:' if path.stat().st_mode & stat.S_IXUSR else b'file:')
                digest.update(bytes.fromhex(file_sha256(path)))
            elif not path.exists():
                digest.update(b'deleted')
            else:
                digest.update(b'directory')
        dependency = git(root / 'Python/commonUtils', 'rev-parse', 'HEAD')
        shared_dirty = bool(git(root / 'Python/commonUtils', 'status', '--porcelain'))
        if shared_dirty:
            # Shared working-tree development is supported only after its own
            # commit, so a snapshot can never silently lose a library edit.
            raise ValueError('Commit pending commonUtils changes before preparing an isolated plan.')
        digest.update(dependency.encode())
    return dict(logistics_commit=commit, commonUtils_commit=dependency, dirty=dirty,
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
            paths = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-c', '-o', '--exclude-standard', '-z']).split(b'\0')
            names = sorted({os.fsdecode(value) for value in paths if value})
            # Retire deleted/type-changed tracked paths before overlaying new
            # children. Never traverse a stale checkout symlink while copying.
            for name in names:
                source, target = root / name, snapshot / name
                if name == 'Python/commonUtils':
                    continue
                if not source.exists() and not source.is_symlink():
                    remove(target)
                elif target.is_symlink() or (target.exists() and source.is_dir() != target.is_dir()):
                    remove(target)
            for name in names:
                source, target = root / name, snapshot / name
                if source.is_symlink() or source.is_file():
                    for parent in reversed(target.parents):
                        if parent == snapshot or snapshot in parent.parents:
                            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                                remove(parent)
                            parent.mkdir(exist_ok=True)
                    if source.is_symlink():
                        remove(target)
                        target.symlink_to(os.readlink(source))
                    else:
                        shutil.copy2(source, target)
        if identity(root, revision) != before:
            raise RuntimeError('Source changed during snapshot preparation; inspect a fresh plan.')
        exclude_private_runtime_references(snapshot)
        with (snapshot / '.git/info/exclude').open('a') as stream:
            stream.write('\n.manager-source.json\n')
        (snapshot / '.manager-source.json').write_text(json.dumps(dict(source=before,
            snapshot_fingerprint=identity(snapshot)['fingerprint']), indent=2) + '\n')
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
