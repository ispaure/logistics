"""Existing ciphertext-copy catalog; document I/O delegates to resource providers."""
import json
from pathlib import Path
from uuid import uuid4
from commonUtils.filesystem.snapshots import verified_file_snapshot
from commonUtils.persistence.publication import mutation_lock
from features.rclone.mobile.cloud import download_name
from services.documents.mobile_reading import DocumentReadCapabilities


class LocalCryptCopies:
    # Reads use app-private ciphertext, not the network transfer connection.
    offline = True
    document_capabilities = DocumentReadCapabilities(
        private=True, writable=True, credential_bound=True, offline=True, required_feature='rclone')

    @property
    def privacy_gate(self):
        return getattr(self.client, 'session_privacy', None)

    def privacy_gate_for(self, key):
        from features.rclone.mobile.session_privacy import remote_privacy_gate
        if getattr(self.client, 'credential_state', None) is None:
            return remote_privacy_gate(self.client, None)  # Single-account compatibility clients.
        record = self.record(key)
        return remote_privacy_gate(self.client, record['remote'], record['identity'], cipher=True)

    def __init__(self, root, client):
        self.root, self.client = Path(root), client
        self._write_lock = mutation_lock
        if not self.root.is_absolute() or self.root.is_symlink():
            raise ValueError('Encrypted copies require an app-private directory.')
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate(record):
        if (not isinstance(record, dict) or set(record) != {'remote', 'encrypted_path', 'identity'}
                or any(not isinstance(v, str) or not v for v in record.values())
                or len(record['identity']) != 64
                or any(c not in '0123456789abcdef' for c in record['identity'])):
            raise ValueError('Invalid encrypted-copy mapping.')
        download_name(record['encrypted_path'])

    def _folder(self, key):
        if not isinstance(key, str) or len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Invalid encrypted copy.')
        folder = self.root / key
        if folder.is_symlink():
            raise ValueError('Linked encrypted copies are not supported.')
        return folder

    def _data(self, key):
        return self._folder(key) / 'data'

    def _temporary(self, key):
        return self._data(key).with_name('.save-' + uuid4().hex)

    def record(self, key):
        folder = self._folder(key)
        for name, limit in (('record.json', 8192), ('data', None)):
            path = folder / name
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1 or (limit is not None and path.stat().st_size > limit):
                raise ValueError('Invalid encrypted copy.')
        record = json.loads((folder / 'record.json').read_text(encoding='utf-8'))
        self._validate(record)
        return record

    def items(self):
        result = []
        for folder in sorted(self.root.iterdir()):
            try:
                record = self.record(folder.name)
            except (OSError, ValueError, TypeError):
                continue
            try:
                name = self.client.request('crypt_describe', remote=record['remote'],
                                           path=record['encrypted_path'], identity=record['identity'])
            except ValueError:
                name = 'Locked copy ' + folder.name[:8]
            result.append((folder.name, name))
        return result

    def _snapshot(self, key):
        record = self.record(key)
        path = self._data(key)
        return self._snapshot_path(record, path)

    def _snapshot_path(self, record, path):
        try:
            revision, digest = verified_file_snapshot(path)
        except ValueError as error:
            raise ValueError('Encrypted copy changed while checking its revision.') from error
        return record, revision, digest

    def _documents(self, key):
        from .resources import DownloadedCryptFile
        from services.documents.provider_documents import ProviderDocuments
        provider = DownloadedCryptFile(self, key)
        return ProviderDocuments(provider), provider.name

    def capture_access(self, key):
        from features.rclone.service import CredentialGrant
        client, generation = self.client, getattr(self.client, 'generation', None)
        return CredentialGrant(key, lambda: self.client is not client or getattr(client, 'generation', None) != generation).check

    def open(self, key, *, password='', cancelled=lambda: False):
        documents, name = self._documents(key)
        reader = documents.open(name, password=password, cancelled=cancelled)
        reader.key = key
        return reader

    def save(self, reader, text, *, cancelled=lambda: False):
        from services.documents.provider_documents import ProviderDocuments
        updated = ProviderDocuments(reader.source.provider).save(reader, text, cancelled=cancelled)
        updated.key = reader.key
        return updated

    def save_metadata(self, reader, changes, *, cancelled=lambda: False):
        from services.documents.provider_documents import ProviderDocuments
        updated = ProviderDocuments(reader.source.provider).save_metadata(reader, changes, cancelled=cancelled)
        updated.key = reader.key
        return updated
