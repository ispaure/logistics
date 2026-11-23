"""Notebook editing over a host-supplied document resource and recovery adapter."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from uuid import uuid4
from commonUtils.persistence.publication import serialize_mutation
from .notebook import Notebook
from .protocol import RecoveryIncomplete


class NotebookDocument:
    """RAM draft with explicit Save; format code does not choose storage backends."""
    def __init__(self, book, *, resource=None, recovery=None, key=None, changed=lambda document: None):
        self.book, self.resource, self.recovery = book, resource, recovery
        self.key = key or (recovery.create(book) if recovery else uuid4().hex)
        self.dirty = False
        self.source_unavailable = False
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

    @serialize_mutation
    def checkpoint(self, book, *, stroke_page=None):
        self._check_editable()
        if not self.writable:
            raise ValueError('This notebook is read-only. Make a local copy before editing.')
        if self.resource is not None:
            self.resource.check()
        if self.recovery is not None:
            self.recovery.check_revision(self.key, book)
        previous_dirty = self.dirty
        self.dirty = self.source_unavailable or self.resource is not None or self.recovery is None
        rollback = None
        try:
            # The host publishes intent and owns its conditional rollback.
            # Recovery's receipt decides whether the edit may be rolled back.
            rollback = self.changed(self)
            if self.recovery is not None:
                if stroke_page is None:
                    self.recovery.save(self.key, book)
                else:
                    self.recovery.append_stroke(self.key, book, stroke_page)
        except RecoveryIncomplete as error:
            if error.published is not True:
                self.dirty = True
            raise  # Preserve the edit, history and dirty intent for the caller.
        except Exception:
            if callable(rollback):
                try:
                    rollback()
                except Exception as error:
                    raise RecoveryIncomplete('Notebook source binding could not be restored. '
                                             'Keep this draft open and use Save As.', published=None) from error
            self.dirty = previous_dirty
            raise

    def checkpoint_stroke(self, book, index):
        self.checkpoint(book, stroke_page=index)

    def save(self, *, cancelled=lambda: False):
        self._check_editable()
        if self.resource is not None:
            if self.book.large_pdf_view:
                self._save_large_archive(cancelled)
            else:
                data = self.book.to_bytes()
                self.resource.save(data, validate=lambda value: Notebook.read(value, max_bytes=self.book.max_bytes),
                                   cancelled=cancelled)
        elif self.recovery is not None:
            self.recovery.save(self.key, self.book)
        self.dirty = False
        self.changed(self)

    def _save_large_archive(self, cancelled):
        from os import fstat
        from services.documents.storage import stage_local_document_export

        resource = self.resource
        if not self.writable or not resource.policy.persistent or resource.revision is None:
            raise ValueError('Open the writable local notebook before saving.')
        target = resource.provider.transfer_location(resource.path)
        with stage_local_document_export(target, expected_revision=resource.revision,
                                         cancelled=cancelled) as staged:
            self.book.write_large_archive(staged, cancelled=cancelled)
            staged.flush()
            info = fstat(staged.fileno())
            expected = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        revision = resource.check()['revision']
        if revision[:4] != expected:
            raise ValueError('The notebook changed after saving. Reopen it to check the saved copy.')
        resource.revision = revision

    @serialize_mutation
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
            source_bytes = self.resource.read()
            saved = Notebook.read(source_bytes, max_bytes=self.book.max_bytes)
            # Use this editor's observed recovery revision: never discard changes
            # checkpointed by another window after this editor last wrote.
            self.recovery.adopt(self.key, saved, self.book)
            publication_error = None
            try:
                self.recovery.save(self.key, saved, source_bytes=source_bytes)
            except RecoveryIncomplete as error:
                if error.published is not True:
                    raise
                publication_error = error
            # If source-binding publication fails, the still-open draft must
            # remain able to checkpoint again against the new recovery revision.
            self.recovery.adopt(self.key, self.book, saved)
            # If the host rejects the binding, this draft remains editable.
            # Its next checkpoint must restore its own archive, not reuse the
            # freshly published source's identity, artwork and sidecars.
            self.book.structure_dirty = True
            if publication_error is not None:
                raise publication_error
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
        try:
            self.book.close_large_pdf()
        finally:
            if self.resource is not None:
                self.resource.close()
