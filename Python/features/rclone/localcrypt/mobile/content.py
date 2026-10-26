"""LocalCrypt content factory and verified ciphertext publication behind providers."""
import base64
from contextlib import contextmanager, closing
from hashlib import sha256
from io import BytesIO
import os
from pathlib import Path
from uuid import uuid4

from commonUtils.filesystem.snapshots import verified_file_snapshot
from commonUtils.persistence.publication import mutation_lock, save_transaction
from commonUtils.runtime.operations import check_cancelled, MutationIncomplete, MutationResult
from commonUtils.runtime.streams import read_up_to


class DecodedContent:
    """Bounded compatibility transport; plaintext remains in this session's RAM."""
    def __init__(self, client, record, path):
        with path.open('rb') as stream:
            result = client.request('crypt_decode', remote=record['remote'], identity=record['identity'],
                                    path=record['encrypted_path'], fd=stream.fileno())
        self.data = base64.b64decode(result['data'], validate=True)
        if len(self.data) > 32 * 1024 * 1024:
            raise ValueError('Decrypted copy exceeds 32 MiB.')

    @contextmanager
    def open(self, path):
        with BytesIO(self.data) as stream:
            yield stream

    def close(self):
        self.data = b''


class CryptContentProvider:
    """The sole native content/write boundary for managed and legacy copies."""
    from services.documents.mobile_reading import DocumentReadCapabilities
    document_capabilities = DocumentReadCapabilities(
        private=True, writable=True, credential_bound=True, offline=True, required_feature='rclone')

    def check(self):
        self._access.check()

    def capture_access(self, path):
        return self._access.grant.check

    @property
    def privacy_gate(self):
        return getattr(self.client, 'session_privacy', None)

    def _ciphertext_temporary(self, path):
        return self._locate(path).with_name('.save-' + uuid4().hex)
    def document_readers(self):
        from services.documents.provider_documents import ProviderDocuments
        return ProviderDocuments(self)

    def _content_at(self, record, physical, *, password='', cancelled=lambda: False):
        self._access.check()
        if getattr(self.client, 'supports_streaming', False):
            from .archive_source import NativeSource
            return NativeSource(self.client, record, physical, password=password, cancelled=cancelled)
        return DecodedContent(self.client, record, physical)

    def content_source(self, path, *, password='', cancelled=lambda: False):
        # Ordinary provider.open remains the transfer byte stream. Native archive
        # acceleration and inner passwords are supplied only through this hook.
        return self._content_at(self.record(path), self._locate(path), password=password, cancelled=cancelled)

    def thumbnail(self, path, size, *, member='', password='', cancelled=lambda: False):
        if not getattr(self.client, 'supports_streaming', False):
            return b''
        with closing(self.content_source(path, password=password, cancelled=cancelled)) as source:
            result = source.request('crypt_thumbnail', member=member, width=size[0], height=size[1])
        check_cancelled(cancelled)
        return base64.b64decode(result['data'], validate=True)

    def _publish_ciphertext(self, path, stage, verify, *, expected_revision, password='', cancelled=lambda: False):
        with mutation_lock, self.operation(cancelled):
            path = self.relative(path)
            record = self.record(path)
            target = self._locate(path)
            temporary = self._ciphertext_temporary(path)
            owned = False
            staged_snapshot = None

            def create():
                nonlocal owned
                with temporary.open('xb') as output:
                    owned = True
                    stage(record, output)

            def verified():
                nonlocal staged_snapshot
                before = verified_file_snapshot(temporary)
                with closing(self._content_at(record, temporary, password=password, cancelled=cancelled)) as source:
                    verify(source)
                staged_snapshot = verified_file_snapshot(temporary)
                if staged_snapshot != before:
                    raise ValueError('Staged ciphertext changed during verification.')

            def validate():
                self._access.check()
                if self.entry(path)['revision'] != expected_revision:
                    raise ValueError('The document changed; original preserved. Reopen it before saving.')

            def cleanup():
                if owned:
                    temporary.unlink(missing_ok=True)

            save_transaction(stage=create, verify=verified, validate=validate,
                             publish=lambda: os.replace(temporary, target), cleanup=cleanup, cancelled=cancelled)
            try:
                self._access.check()
                if verified_file_snapshot(target)[1] != staged_snapshot[1]:
                    raise ValueError('Ciphertext changed after publication.')
            except Exception as error:
                raise MutationIncomplete('The file was saved, but verification after publication failed. Keep your draft.',
                                         MutationResult(destination_published=True)) from error

    def replace_bytes(self, path, data, *, expected_revision, cancelled=lambda: False):
        if len(data) > 32 * 1024 * 1024:
            raise ValueError('Document exceeds its buffer size limit.')
        def stage(record, output):
            action = 'crypt_encode' if Path(path).suffix.lower() in {'.txt', '.md', '.markdown', '.ini'} else 'crypt_write_buffer'
            self.client.request(action, remote=record['remote'], identity=record['identity'],
                path=record['encrypted_path'], fd=output.fileno(), data=base64.b64encode(data).decode('ascii'))
        def verify(source):
            with source.open(path) as stream:
                result = read_up_to(stream, len(data) + 1, cancelled=cancelled)
            if sha256(result).digest() != sha256(data).digest():
                raise ValueError('Encrypted save verification failed; original preserved.')
        self._publish_ciphertext(path, stage, verify, expected_revision=expected_revision, cancelled=cancelled)

    def replace_archive_members(self, path, replacements, *, expected_revision, password='', cancelled=lambda: False):
        from commonUtils.archives.rebuilding import content_manifest, patched_manifest
        if len(replacements) != 1:
            raise ValueError('This native archive writer replaces one metadata member per transaction.')
        member, data = next(iter(replacements.items()))
        if len(data) > 1024 * 1024:
            raise ValueError('Metadata exceeds 1 MiB.')
        from commonUtils.runtime.resources.content import ProviderContent
        with closing(ProviderContent(self, path, password=password, cancelled=cancelled)) as content:
            if content.expected != expected_revision:
                raise ValueError('The document changed; original preserved.')
            with content.open_archive(path) as archive:
                expected = patched_manifest(archive, replacements, cancelled=cancelled)
        def stage(record, output):
            with self._locate(path).open('rb') as original:
                self.client.request('crypt_metadata', remote=record['remote'], identity=record['identity'],
                    path=record['encrypted_path'], fd=original.fileno(), output_fd=output.fileno(),
                    member=member, password=password, data=base64.b64encode(data).decode('ascii'))
        def verify(source):
            archive = getattr(source, 'open_archive', None)
            if archive is not None:
                with archive(path, password=password) as opened:
                    actual = content_manifest(opened, cancelled=cancelled)
            else:
                from commonUtils.archives.zip_access import open_archive
                with source.open(path) as stream, open_archive(stream, password=password or None) as opened:
                    actual = content_manifest(opened, cancelled=cancelled)
            if actual != expected:
                raise ValueError('Archive verification failed; original preserved.')
        self._publish_ciphertext(path, stage, verify, expected_revision=expected_revision,
                                 password=password, cancelled=cancelled)
