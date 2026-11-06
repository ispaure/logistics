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
        self.recovery_deleted = False
        self.changed = changed

    @property
    def writable(self):
        return self.resource is None or self.resource.policy.writable

    @property
    def can_autosave(self):
        return self.resource is not None and self.resource.policy.persistent and self.writable

    @property
    def deletion_started(self):
        return self.source_deleted or self.recovery_deleted

    def _check_editable(self):
        if self.deletion_started:
            raise ValueError('This notebook was deleted. Retry Delete to finish cleanup, or use Save As.')

    def checkpoint(self, book):
        self._check_editable()
        if not self.writable:
            raise ValueError('This notebook is read-only. Make a local copy before editing.')
        if self.resource is not None:
            self.resource.check()
        previous_dirty = self.dirty
        self.dirty = self.resource is not None or self.recovery is None
        try:
            # Publish the host's dirty/source binding before committing recovery.
            # A rejected binding must not leave a durable edit that Editor rolls
            # back in memory. If recovery then fails, a dirty binding safely
            # selects the previous recovery draft instead of hiding a saved edit.
            self.changed(self)
            if self.recovery is not None:
                self.recovery.save(self.key, book)
        except Exception:
            self.dirty = previous_dirty
            raise

    def save(self, *, cancelled=lambda: False):
        self._check_editable()
        if self.resource is not None:
            data = self.book.to_bytes()
            self.resource.save(data, validate=Notebook.read, cancelled=cancelled)
        elif self.recovery is not None:
            self.recovery.save(self.key, self.book)
        self.dirty = False
        self.changed(self)

    def discard(self):
        """Retire an explicit discard without leaving a resumable dirty draft."""
        if not self.dirty or self.deletion_started:
            return
        if self.recovery is None:
            self.dirty = False
            return
        if self.resource is None:
            # Explicitly discarding an orphan removes only this observed draft;
            # never overwrite a different same-named file or another window's edits.
            self.recovery.delete(self.key, expected=self.book)
            self.recovery_deleted = True
            self.dirty = False
            self.changed(self)
            return
        revision = self.resource.revision
        try:
            saved = Notebook.read(self.resource.read())
            # Use this editor's observed recovery revision: never discard changes
            # checkpointed by another window after this editor last wrote.
            self.recovery.adopt(self.key, saved, self.book)
            self.recovery.save(self.key, saved, replace_base=True)
            # If source-binding publication fails, the still-open draft must
            # remain able to checkpoint again against the new recovery revision.
            self.recovery.adopt(self.key, self.book, saved)
            # If the host rejects the binding, this draft remains editable.
            # Its next checkpoint must restore its own archive, not reuse the
            # freshly published source's identity, artwork and sidecars.
            self.book.structure_dirty = True
            self.dirty = False
            self.changed(self)
        except Exception:
            self.resource.revision = revision
            self.dirty = True
            raise
        self.book = saved

    def delete(self):
        if not self.writable and not self.deletion_started:
            raise ValueError('This notebook is read-only.')
        if self.resource is not None and not self.source_deleted:
            self.resource.delete()
            self.source_deleted = True
        if self.recovery is not None and not self.recovery_deleted:
            try:
                self.recovery.delete(self.key)
                self.recovery_deleted = True
            except OSError as error:
                if self.source_deleted:
                    raise OSError('Notebook file deleted, but recovery cleanup failed. '
                                  'Your draft is still open; retry Delete or use Save As.') from error
                raise

    def close(self):
        if self.resource is not None:
            self.resource.close()
