"""Process-owned bindings between mount paths and the credentials that launched them."""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import RLock
from features.rclone import session


def _path(path):
    return os.path.normcase(str(Path(path).resolve()))


def _identity(config):
    values = session.credentials(config)
    if values is not None:
        return sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
    path = Path(config)
    before = path.stat()
    digest = sha256()
    with path.open('rb') as source:
        while chunk := source.read(65536):
            digest.update(chunk)
    after = path.stat()
    def version(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
    if version(before) != version(after):
        raise ValueError('Credentials changed while preparing the mount.')
    return version(after), digest.hexdigest()


@dataclass(frozen=True)
class MountBinding:
    config: str
    remote: str
    identity: object
    revoked: object

    @classmethod
    def capture(cls, config, remote):
        in_memory = session.credentials(config) is not None
        revoked = session.revocation_check(config) if in_memory else lambda: False
        return cls(_path(config), remote, _identity(config), revoked)

    def matches(self, config, remote):
        try:
            return self.config == _path(config) and self.remote == remote and not self.revoked() and self.identity == _identity(config)
        except (OSError, ValueError):
            return False


class MountBindings:
    def __init__(self):
        self._bindings = {}
        self._lock = RLock()

    def remember(self, mount_path, binding):
        with self._lock:
            self._bindings[_path(mount_path)] = binding

    def matches(self, mount_path, config, remote):
        with self._lock:
            binding = self._bindings.get(_path(mount_path))
        return binding is not None and binding.matches(config, remote)

    def forget(self, mount_path):
        with self._lock:
            self._bindings.pop(_path(mount_path), None)
