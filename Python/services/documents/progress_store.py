"""Bounded checkpoint envelopes and the two durable reader-state stores."""

from hashlib import sha256
import json

from commonUtils.persistence import atomic_write_bytes

from .credential_state import LIMIT, _revision_value, sources


class IncompatibleCheckpoint(ValueError):
    """The saved locator belongs to a different document revision."""


def encode(value):
    raw = json.dumps(value, allow_nan=False, separators=(',', ':')).encode()
    if len(raw) > LIMIT:
        raise ValueError('Reader state exceeds its size limit.')
    return raw


def revision_binding(revision):
    raw = json.dumps(revision, sort_keys=True, default=_revision_value, allow_nan=False)
    # Keep content hashes and offline revision details out of the local envelope.
    return sha256(raw.encode()).hexdigest(), raw


def checkpoint(record, identity, kind, generation):
    if (not isinstance(record, dict) or record.get('identity') != identity
            or not isinstance(record.get('state'), dict)):
        raise ValueError('Invalid reader state binding.')
    if type(record.get('version')) is not int:
        raise ValueError('Invalid reader state version.')
    if record['version'] != 2:
        raise ValueError('Unsupported reader state version.')
    if (record.get('kind') != kind or record.get('generation') != generation
            or type(record.get('sequence')) is not int or not 1 <= record['sequence'] < 2**63
            or type(record.get('locator_version')) is not int or not 1 <= record['locator_version'] < 2**31
            or not isinstance(record.get('revision'), str) or not checkpoint_name(record['revision'])):
        raise ValueError('Invalid reader checkpoint.')
    # Re-encode before use to reject nonfinite values and invalid nested data.
    encode(record['state'])
    return record


class LocalCheckpoints:
    def __init__(self, root, document, kind, *, bookmarks):
        self.root = self.directory(root, document, bookmarks=bookmarks)
        self.identity = sha256(encode([document, kind])).hexdigest()
        self.legacy = self.legacy_revision = None

    @staticmethod
    def directory(root, document, *, bookmarks):
        section = root / ('ReaderBookmarks' if bookmarks else 'ReaderPositions')
        return section / 'Local' / sha256(encode(document)).hexdigest()

    def location(self):
        path = self.root / (self.identity + '.json')
        if any(part.is_symlink() for part in (path, self.root, self.root.parent, self.root.parent.parent)):
            raise ValueError('Linked reader state is not supported.')
        return path

    def read(self):
        return read_local_checkpoint(self.location())

    def write(self, record, validate, *, overwrite=True):
        path = self.location()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_bytes(path, encode(record), validate=validate, file_mode=0o600, overwrite=overwrite)


def read_local_checkpoint(path):
    if path.is_symlink():
        raise ValueError('Linked reader state is not supported.')
    with path.open('rb') as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('Reader state exceeds its size limit.')
    return json.loads(raw)


def checkpoint_name(name):
    return len(name) == 64 and all(character in '0123456789abcdef' for character in name)


def local_checkpoint_files(directory):
    if any(path.is_symlink() for path in (directory, directory.parent, directory.parent.parent)):
        raise ValueError('Linked reader state was preserved.')
    for path in directory.glob('*.json'):
        if path.is_symlink() or not checkpoint_name(path.stem) or not path.is_file():
            raise ValueError('Unexpected reader state file was preserved.')
        yield path


def clear_local_checkpoints(directory):
    if directory.is_symlink():
        raise ValueError('Linked reader state was preserved.')
    if not directory.exists():
        return
    for child in directory.iterdir():
        if not checkpoint_name(child.name) or child.is_symlink() or not child.is_dir():
            raise ValueError('Unexpected reader state directory was preserved.')
        for path in local_checkpoint_files(child):
            path.unlink()
        if not any(child.iterdir()):
            child.rmdir()


class EncryptedCheckpoints:
    def __init__(self, store, legacy_path, remote_name, *, namespace=None):
        self.store, self.remote_name = store, remote_name
        self.namespace = namespace
        self.legacy_path = str(legacy_path) if legacy_path is not None else store.document
        self.legacy_remote = next((source.remote for source in sources(store.provider)
                                   if getattr(source, 'remote', None)), '')

    def identity(self, *, create=False):
        return self.store.binding(create=create, remote_name=self.remote_name, namespace=self.namespace)

    def read(self, identity):
        try:
            return self.store.read_checkpoint(identity)
        except FileNotFoundError:
            return self._read_legacy()

    def _read_legacy(self):
        # Use the same authority and lookup keys, with the exact admitted legacy
        # key supplied by the format owner. The original stays until Clear.
        from copy import copy

        legacy = copy(self.store)
        from itertools import product
        current = (self.store.document, self.remote_name, self.namespace)
        candidates = product(dict.fromkeys((self.store.document, self.legacy_path)),
                             dict.fromkeys((self.remote_name, self.legacy_remote)),
                             dict.fromkeys((self.namespace, None)))
        for path, remote_name, namespace in candidates:
            if (path, remote_name, namespace) == current:
                continue
            legacy.document = path
            binding = legacy.binding(remote_name=remote_name, namespace=namespace)
            try:
                return legacy.read_checkpoint(binding)
            except FileNotFoundError:
                pass
        raise FileNotFoundError

    def write(self, record, validate):
        record['authority'] = self.store.authority()
        self.store.write_checkpoint(record['identity'], encode(record), validate=validate)
