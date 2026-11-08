"""Host document I/O over resource providers; format code never opens virtual paths.

Providers retain encoding, credentials and publication mechanics. This session
adds a document baseline, bounded input, independent lifetime and host privacy
policy, without introducing a second storage backend or writing recovery data.
"""
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.resources.mutations import save_resource_and_reopen
from commonUtils.runtime.streams import read_up_to


class _ReadRevisionChanged(ValueError):
    """The provider's revision changed across one bounded document read."""


class DocumentSizeExceeded(ValueError):
    """Document bytes exceed the caller's format limit."""


@dataclass(frozen=True)
class DocumentPolicy:
    persistent: bool
    writable: bool

    @classmethod
    def for_provider(cls, provider):
        sources = tuple(document_sources(provider))
        persistent = not any(getattr(source, 'private', False) or getattr(source, 'remote_storage', False)
                             for source in sources)
        declared = [source.capabilities for source in sources if getattr(source, 'capabilities', None) is not None]
        return cls(persistent, bool(declared) and document_writable(provider))

    def confirm_plaintext(self, destination):
        return not self.persistent and destination.persistent


def document_sources(*sources):
    """Walk host wrappers without letting a local cache hide remote policy."""
    seen = set()
    for source in sources:
        while source is not None and id(source) not in seen:
            seen.add(id(source))
            yield source
            source = getattr(source, 'provider', None)


def document_display_name(provider, path):
    for source in document_sources(provider):
        if getattr(source, 'decoded_path', None):
            path = source.decoded_path
            break
    return Path(path).name


def display_path(provider, path):
    """Format a provider's logical path without opening or decoding the file."""
    root = None
    for source in document_sources(provider):
        if getattr(source, 'remote', None):
            name = getattr(source, 'decoded_path', path)
            records = getattr(getattr(source, 'client', None), 'package_records', ())
            remote = next((original for record in records
                           for original, alias in record.get('aliases', {}).items()
                           if alias == source.remote), source.remote)
            return f'{remote}:{name}'
        if root is None:
            root = getattr(source, 'root', None)
    return str(Path(root or '') / path)


def document_writable(*sources):
    for source in document_sources(*sources):
        if getattr(source, 'remote_storage', False) or getattr(source, 'read_only', False):
            return False
        declared = getattr(source, 'capabilities', None)
        if declared is not None and not declared.replace:
            return False
    return True


def check_document_access(provider):
    for source in document_sources(provider):
        validate = getattr(source, '_check_active', None) or getattr(source, 'check', None)
        if validate is not None:
            validate()



def document_operation(source, cancelled=lambda: False):
    operation = getattr(source, 'operation', None)
    return operation(cancelled) if operation else nullcontext()


def local_document_provider(directory):
    """Select ordinary filesystem storage at the host document boundary."""
    from commonUtils.runtime.resources.local import LocalFiles
    return LocalFiles(directory)


def document_remote(provider):
    return any(getattr(source, 'remote_storage', False) for source in document_sources(provider))


def create_document_folder(provider, path, *, cancelled=lambda: False):
    from commonUtils.runtime.resources.mutations import create_resource_folder
    if not document_writable(provider):
        raise PermissionError('This Notes Library is read-only.')
    with document_operation(provider, cancelled):
        check_document_access(provider)
        return create_resource_folder(provider, path, cancelled=cancelled)


def create_marked_document_folder(provider, folder, marker, *, cancelled=lambda: False):
    """Publish an empty marker and roll back only the folder this call created."""
    from io import BytesIO
    from posixpath import join
    from commonUtils.persistence.publication import mutation_lock
    from commonUtils.runtime.resources.provider import require_capability

    if not document_writable(provider):
        raise PermissionError('This location is read-only.')
    require_capability(provider, 'create')
    require_capability(provider, 'delete')
    with mutation_lock, document_operation(provider, lambda: False):
        check_document_access(provider)
        check_cancelled(cancelled)
        provider.mkdir(folder)
        revision = provider.entry(folder)['revision']
        try:
            check_cancelled(cancelled)
            provider.create_file(join(folder, marker), BytesIO(), cancelled=cancelled)
        except Exception:
            try:
                provider.remove_empty(folder, revision)
            except (OSError, ValueError) as cleanup:
                raise ValueError('Could not finish creating the folder. Inspect it before retrying.') from cleanup
            raise
    return folder


def move_document_resource(provider, source, destination, *, cancelled=lambda: False):
    from commonUtils.runtime.resources.mutations import rename_resource
    if not document_writable(provider):
        raise PermissionError('This Notes Library is read-only.')
    with document_operation(provider, cancelled):
        check_document_access(provider)
        return rename_resource(provider, source, destination, cancelled=cancelled)

def publish_document_stream(source, path, writer, *, expected_revision, verify=None,
                            cancelled=lambda: False):
    """Keep archive rewrites streaming through their provider's transaction owner."""
    if not document_writable(source):
        raise PermissionError('This document is read-only. Create a local copy before editing.')
    with document_operation(source, cancelled):
        check_cancelled(cancelled)
        return source.replace_stream(path, writer, expected_revision=expected_revision, verify=verify)


def document_transaction(**options):
    """Ordinary archive policy retains its verified staging/backup callbacks."""
    from commonUtils.persistence.publication import save_transaction
    return save_transaction(**options)


def read_local_document(path, **options):
    from commonUtils.persistence.text import read_text_file
    return read_text_file(path, **options)


class DocumentResource:
    """One document's retained provider and last successfully read/saved revision.

    Construction takes independent access where supported; close() is idempotent.
    A new destination uses publish() with revision=None (no replacement).
    Successful saves advance the baseline only after reopening exact bytes.
    """
    def __init__(self, provider, path, *, max_bytes, independent=True):
        self.provider = provider.reopen() if independent and hasattr(provider, 'reopen') else provider
        self.path = self.provider.relative(path)
        self.max_bytes = max_bytes
        self.revision = None
        self._content_baseline = None
        self.closed = False
        self._release = self.provider.acquire() if independent and hasattr(self.provider, 'acquire') else lambda: None

    @property
    def policy(self):
        return DocumentPolicy.for_provider(self.provider)

    @property
    def name(self):
        return Path(self.path).name

    @property
    def identity(self):
        if self.policy.persistent and hasattr(self.provider, 'transfer_location'):
            return ('local', str(self.provider.transfer_location(self.path)))
        return (self.provider.storage_id, getattr(self.provider, 'storage_namespace', ''), self.path)

    def check(self):
        if self.closed:
            raise ValueError('This document is closed. Reopen it.')
        # entry also validates the retained provider's credential generation.
        return self.provider.entry(self.path)

    def read(self, *, cancelled=lambda: False, track_local_content=False):
        before = self.check()['revision']
        operation = getattr(self.provider, 'operation', None)
        with operation(cancelled) if operation else nullcontext():
            with self.provider.open(self.path) as stream:
                data = read_up_to(stream, self.max_bytes + 1, cancelled=cancelled)
        check_cancelled(cancelled)
        if len(data) > self.max_bytes:
            raise DocumentSizeExceeded('Document is too large; exceeds its format size limit.')
        if self.check()['revision'] != before:
            raise _ReadRevisionChanged('The document changed while opening; reopen it.')
        self.revision = before
        if track_local_content or self._content_baseline is not None:
            from commonUtils.runtime.resources.local import LocalFiles
            if isinstance(self.provider, LocalFiles) and self.policy.persistent:
                self._content_baseline = before, sha256(data).hexdigest()
        return data

    def save(self, data, *, validate=lambda data: None, cancelled=lambda: False):
        if self.revision is None:
            raise ValueError('Read the document before replacing it.')
        expected = self.revision
        baseline = self._content_baseline
        if baseline is not None and baseline[0] == expected:
            current = self.check()['revision']
            # The same local file can acquire new metadata while the editor is
            # open. Rebind only after a stable read proves its bytes match.
            if current != expected and current[:3] == expected[:3]:
                from commonUtils.runtime.streams import stream_signature
                with self.provider.open(self.path) as stream:
                    _, digest = stream_signature(stream, cancelled=cancelled, max_bytes=self.max_bytes)
                if digest == baseline[1] and self.check()['revision'] == current:
                    expected = current
        revision = self.publish(self.provider, self.path, data, max_bytes=self.max_bytes,
                                expected_revision=expected, validate=validate, cancelled=cancelled,
                                alive=lambda: not self.closed)
        self.revision = revision
        if baseline is not None:
            self._content_baseline = revision, sha256(data).hexdigest()
        return revision

    @staticmethod
    def publish(provider, path, data, *, max_bytes, expected_revision=None,
                validate=lambda data: None, cancelled=lambda: False, alive=lambda: True, after_publish=None):
        policy = DocumentPolicy.for_provider(provider)
        if not document_writable(provider):
            raise PermissionError('Cloud files are read-only. Create a local copy before editing.')
        if expected_revision is not None and not policy.writable:
            raise PermissionError('This document is read-only.')
        if len(data) > max_bytes:
            raise DocumentSizeExceeded('Document is too large; exceeds its format size limit.')
        check_cancelled(lambda: cancelled() or not alive())
        validate(data)
        def reopen():
            with DocumentResource(provider, path, max_bytes=max_bytes, independent=False) as saved:
                try:
                    content = saved.read()
                except _ReadRevisionChanged:
                    # Android SD-card/FUSE metadata can retain the replaced
                    # inode until open() refreshes it. Retry once after publication;
                    # the second read must be stable and match the saved bytes.
                    content = saved.read()
                if sha256(content).digest() != sha256(data).digest():
                    raise ValueError('The saved file changed after publication.')
                validate(content)
                return after_publish(saved.revision) if after_publish is not None else saved.revision
        return save_resource_and_reopen(provider, path, data, reopen=reopen,
            expected_revision=expected_revision, cancelled=lambda: cancelled() or not alive())

    def delete(self, *, cancelled=lambda: False):
        """Delete an admitted file revision, honoring every wrapper's policy."""
        if not self.policy.writable:
            raise PermissionError('This document is read-only.')
        for source in document_sources(self.provider):
            capabilities = getattr(source, 'capabilities', None)
            if capabilities is not None and not capabilities.delete:
                raise PermissionError('This storage does not support document deletion.')
        if self.revision is None:
            raise ValueError('Read the document before deleting it.')
        with document_operation(self.provider, cancelled):
            check_cancelled(cancelled)
            row = self.check()
            if row['directory'] or row['revision'] != self.revision:
                raise ValueError('File changed; reopen it before deleting.')
            self.provider.remove_empty(self.path, self.revision)

    def close(self):
        if not self.closed:
            self.closed = True
            self._release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def write_local_document(path, data, *, expected=None, allow_overwrite=False):
    """Ordinary host adapter preserves established permissions and conflict policy."""
    from commonUtils.persistence.text import write_text_file
    return write_text_file(path, data, expected=expected, allow_overwrite=allow_overwrite)


def export_local_document(path, data, *, max_bytes, validate=lambda data: None,
                          cancelled=lambda: False):
    """Publish a picker-approved local copy without retargeting its source.

    Capture an existing destination before validation so publication refuses
    concurrent replacement. LocalFiles enforces host-owned path boundaries.
    """
    from commonUtils.runtime.resources.local import LocalFiles
    target = Path(path).absolute()
    provider = LocalFiles(target.parent)
    try:
        revision = provider.entry(target.name)['revision']
    except FileNotFoundError:
        revision = None
    return DocumentResource.publish(provider, target.name, data, max_bytes=max_bytes,
                                    expected_revision=revision, validate=validate, cancelled=cancelled)


@contextmanager
def stage_local_document_export(path, *, cancelled=lambda: False):
    """Give a streaming export a private stage and publish it without replacement."""
    import os
    from tempfile import NamedTemporaryFile
    from commonUtils.filesystem.local_access import check_local_path
    from commonUtils.persistence.publication import rename_exclusive

    target = Path(path).absolute()
    check_local_path(target)
    check_cancelled(cancelled)
    if os.path.lexists(target):
        raise FileExistsError('A file already exists at the chosen destination.')
    stage = None
    try:
        with NamedTemporaryFile(prefix='.document-export-', dir=target.parent, delete=False) as stream:
            stage = Path(stream.name)
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        check_local_path(target)
        check_cancelled(cancelled)
        rename_exclusive(stage, target)
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)


def local_document_resource(path, *, max_bytes):
    """Resolve an ordinary path inside the host, including protected-root checks."""
    from commonUtils.runtime.resources.local import LocalFiles
    target = Path(path).absolute()
    return DocumentResource(LocalFiles(target.parent), target.name, max_bytes=max_bytes)


def read_local_bytes(path, *, max_bytes, cancelled=lambda: False):
    with local_document_resource(path, max_bytes=max_bytes) as resource:
        return resource.read(cancelled=cancelled)
