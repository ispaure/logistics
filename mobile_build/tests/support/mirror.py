"""Reusable Logistics mirror fixtures; no test cases or discovery side effects."""
from hashlib import sha256
import json
import os
from pathlib import Path


class MirrorClient:
    generation = 1
    identity = 'a' * 64

    def __init__(self):
        self.data = {'folder/note.txt': b'first', 'encoded/opaque-name': b'ciphertext'}
        self.backups = []
        self.directories = set()

    def connection_identity(self, remote):
        return self.identity

    def request(self, action, **values):
        path = values.get('path', '')
        if action == 'mirror_progress':
            return dict(phase='Transferring', done=5, total=10, files=1, total_files=2,
                        listed=3, checks=1, active=1)
        if action in ('mirror_review_progress', 'mirror_review_clear'):
            return dict(changes=[])
        if action == 'mirror_review':
            target = Path(values['local_path'])
            local = {p.relative_to(target).as_posix(): p.read_bytes().hex()
                     for p in target.rglob('*') if p.is_file()} if target.exists() else {}
            prefix = path + '/' if path else ''
            online = {key[len(prefix):]: value.hex() for key, value in self.data.items() if key.startswith(prefix)}
            source, destination = (local, online) if values['push'] else (online, local)
            changes = [[('add' if name not in destination else 'match' if source[name] == destination[name]
                        else 'replace'), name] for name in source]
            changes += [['delete', name] for name in destination if name not in source]
            fingerprint = sha256(json.dumps([source, destination], sort_keys=True).encode()).hexdigest()
            return dict(changes=changes, fingerprint=fingerprint)
        if action == 'crypt_paths':
            return [self.request('crypt_path', **dict(values, **entry, decode=True))['path']
                    for entry in values['entries']]
        if action == 'crypt_path':
            return dict(path=path, identity='b' * 64)
        if action == 'mirror_info':
            crypt = values['remote'] == 'Secret' and not values.get('decrypted')
            return dict(identity=self.identity, crypt=crypt, cipher_identity='b' * 64 if crypt else '',
                        prefix='encoded' if crypt else path)
        if action == 'mirror_sync':
            import shutil
            target = Path(values['local_path'])
            prefix = path + '/' if path else ''
            if values['push']:
                local = {child.relative_to(target).as_posix(): child.read_bytes() for child in target.rglob('*') if child.is_file()}
                transferred = sum(self.data.get(prefix + key) != data for key, data in local.items())
                self.data = {key: data for key, data in self.data.items() if not key.startswith(prefix)}
                self.data.update({prefix + key: data for key, data in local.items()})
                self.directories = {key for key in self.directories if not key.startswith(prefix)}
                self.directories.update(prefix + child.relative_to(target).as_posix() for child in target.rglob('*') if child.is_dir())
                return transferred
            for child in list(target.iterdir()):
                shutil.rmtree(child) if child.is_dir() else child.unlink()
            for key, data in self.data.items():
                if key.startswith(prefix):
                    destination = target / key[len(prefix):]
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with destination.open('wb') as stream:
                        self.copy_remote_file(key, stream)
            for key in self.directories:
                if key.startswith(prefix):
                    (target / key[len(prefix):]).mkdir(parents=True, exist_ok=True)
            return 1
        if action == 'mirror_validate':
            hash = sha256()
            while block := os.read(values['fd'], 65536):
                hash.update(block)
            return hash.hexdigest()
        raise ValueError(action)

    def copy_remote_file(self, path, stream):
        stream.write(self.data[path])
