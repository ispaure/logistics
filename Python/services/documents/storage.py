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
from commonUtils.runtime.resources.provider import capabilities
from commonUtils.runtime.streams import read_up_to


class _ReadRevisionChanged(ValueError):
    """The provider's revision changed across one bounded document read."""


@dataclass(frozen=True)
class DocumentPolicy:
    persistent: bool
    writable: bool

    @classmethod
    def for_provider(cls, provider):
        remote = bool(getattr(provider, 'remote_storage', False))
        return cls(not (getattr(provider, 'private', False) or remote),
                   capabilities(provider).replace and not remote and not getattr(provider, 'read_only', False))

    def confirm_plaintext(self, destination):
        return not self.persistent and destination.persistent


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
            raise ValueError('Document exceeds its format size limit.')
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
        if getattr(provider, 'remote_storage', False) or getattr(provider, 'read_only', False):
            raise PermissionError('Cloud files are read-only. Create a local copy before editing.')
        if expected_revision is not None and not policy.writable:
            raise PermissionError('This document is read-only.')
        if len(data) > max_bytes:
            raise ValueError('Document exceeds its format size limit.')
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
