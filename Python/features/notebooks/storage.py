"""Notebook editing over a host-supplied document resource and recovery adapter."""
from uuid import uuid4
from .notebook import Notebook


class NotebookDocument:
    """RAM draft with explicit Save; format code does not choose storage backends."""
    def __init__(self, book, *, resource=None, recovery=None, key=None, changed=lambda document: None):
        self.book, self.resource, self.recovery = book, resource, recovery
        self.key = key or (recovery.create(book) if recovery else uuid4().hex)
        self.dirty = False
        self.source_deleted = False
        self.changed = changed

    @property
    def writable(self):
        return self.resource is None or self.resource.policy.writable

    def checkpoint(self, book):
        if not self.writable:
            raise ValueError('This notebook is read-only. Make a local copy before editing.')
        if self.resource is not None:
            self.resource.check()
        if self.recovery is not None:
            self.recovery.save(self.key, book)
        self.dirty = self.resource is not None or self.recovery is None
        self.changed(self)

    def save(self, *, cancelled=lambda: False):
        if self.resource is not None:
            data = self.book.to_bytes()
            self.resource.save(data, validate=Notebook.read, cancelled=cancelled)
        elif self.recovery is not None:
            self.recovery.save(self.key, self.book)
        self.dirty = False
        self.changed(self)

    def delete(self):
        if not self.writable:
            raise ValueError('This notebook is read-only.')
        if self.resource is not None and not self.source_deleted:
            self.resource.delete()
            self.source_deleted = True
        if self.recovery is not None:
            try:
                self.recovery.delete(self.key)
            except OSError as error:
                if self.source_deleted:
                    raise OSError('Notebook file deleted, but recovery cleanup failed. '
                                  'Your draft is still open; retry Delete or use Save As.') from error
                raise

    def close(self):
        if self.resource is not None:
            self.resource.close()
