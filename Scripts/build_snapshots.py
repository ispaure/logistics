"""Materialize owned Logistics source snapshots without copying private inputs."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory


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
            name = encoded.decode()
            path = root / name
            digest.update(encoded)
            if path.is_file():
                digest.update(hashlib.sha256(path.read_bytes()).digest())
            elif not path.exists():
                digest.update(b'deleted')
        dependency = git(root / 'Python/commonUtils', 'rev-parse', 'HEAD')
        shared_dirty = bool(git(root / 'Python/commonUtils', 'status', '--porcelain'))
        if shared_dirty:
            # Shared working-tree development is supported only after its own
            # commit, so a snapshot can never silently lose a library edit.
            raise ValueError('Commit pending commonUtils changes before preparing an isolated plan.')
        digest.update(dependency.encode())
    return dict(logistics_commit=commit, commonUtils_commit=dependency, dirty=dirty,
                fingerprint=digest.hexdigest(), selection=revision)


def materialize(root, destination, revision='working-tree'):
    root, destination = Path(root), Path(destination)
    before = identity(root, revision)
    if destination.exists():
        metadata = destination / '.manager-source.json'
        if metadata.is_file():
            saved = json.loads(metadata.read_text())
            if saved.get('source') == before and saved.get('snapshot_fingerprint') == identity(destination)['fingerprint']:
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
            for encoded in set(paths):
                if not encoded:
                    continue
                name = encoded.decode()
                source, target = root / name, snapshot / name
                if source.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                elif not source.exists() and target.is_file():
                    target.unlink()
        if identity(root, revision) != before:
            raise RuntimeError('Source changed during snapshot preparation; inspect a fresh plan.')
        with (snapshot / '.git/info/exclude').open('a') as stream:
            stream.write('\n.manager-source.json\n')
        (snapshot / '.manager-source.json').write_text(json.dumps(dict(source=before,
            snapshot_fingerprint=identity(snapshot)['fingerprint']), indent=2) + '\n')
        snapshot.rename(destination)
    return before
