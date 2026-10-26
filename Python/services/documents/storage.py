"""Host document I/O over resource providers; format code never opens virtual paths.

Providers retain encoding, credentials and publication mechanics. This session
adds a document baseline, bounded input, independent lifetime and host privacy
policy, without introducing a second storage backend or writing recovery data.
"""
from contextlib import nullcontext
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.resources.mutations import save_resource_and_reopen
from commonUtils.runtime.streams import read_up_to


class _ReadRevisionChanged(ValueError):
    """The provider's revision changed across one bounded document read."""


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

    def read(self, *, cancelled=lambda: False):
        before = self.check()['revision']
        operation = getattr(self.provider, 'operation', None)
        with operation(cancelled) if operation else nullcontext():
            with self.provider.open(self.path) as stream:
                data = read_up_to(stream, self.max_bytes + 1, cancelled=cancelled)
        check_cancelled(cancelled)
        if len(data) > self.max_bytes:
            raise ValueError('Document is too large; exceeds its format size limit.')
        if self.check()['revision'] != before:
            raise _ReadRevisionChanged('The document changed while opening; reopen it.')
        self.revision = before
        return data

    def save(self, data, *, validate=lambda data: None, cancelled=lambda: False):
        if self.revision is None:
            raise ValueError('Read the document before replacing it.')
        revision = self.publish(self.provider, self.path, data, max_bytes=self.max_bytes,
                                expected_revision=self.revision, validate=validate, cancelled=cancelled,
                                alive=lambda: not self.closed)
        self.revision = revision
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
            raise ValueError('Document is too large; exceeds its format size limit.')
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
