"""Provider document state and resource lifetime, separate from format commands."""
import asyncio
import threading

from commonUtils.runtime.operations import check_cancelled
from services.worker_retirement import drain_worker


class _DocumentOperation:
    """One session reservation, spanning worker borrows and a saved-reader handoff."""

    def __init__(self, session, current):
        self.reader = session.reader
        self._current = current
        self.cancel = threading.Event()
        self.cancellation = None

    def current(self):
        return self._current(self.reader)

    def raise_cancelled(self):
        if self.cancellation is not None:
            raise self.cancellation


class ProviderDocumentSession:
    def __init__(self, owner):
        self.owner = owner
        self.cancel = None
        self.busy = False
        from .provider_opening import ProviderDocumentOpening
        self.opening = ProviderDocumentOpening(owner, self)
        self._reader = None
        self.metadata_fields = {}
        self.metadata_initial = {}
        self.metadata_values = {}
        self.closed = False
        self.terminal = False
        self.worker = None
        self._operation = None
        self._disposed = set()
        self._reader_cleanup = []
        self._progress_cleanup = []

    def set_busy(self, busy):
        """Notify document controls without changing the connection's busy state."""
        self.busy = busy
        self.owner.set_document_busy(busy)

    @property
    def reader(self):
        return self._reader

    @reader.setter
    def reader(self, value):
        if self.terminal:
            raise OSError('This private document has retired.')
        if (self._operation is not None or self.worker is not None
                or getattr(getattr(self.owner, '_provider_progress', None), 'worker', None) is not None):
            raise OSError('The private document is still in use.')
        self._replace_reader(value)

    def _replace_reader(self, value):
        previous, self._reader = self._reader, value
        if previous is not None and previous is not value:
            self.release_reader(previous)
        if value is not None:
            self.closed = False
            self._disposed.clear()

    def can_start(self):
        return (not self.terminal and not self.busy and self._operation is None and self.worker is None
                and getattr(getattr(self.owner, '_provider_progress', None), 'worker', None) is None)

    def capture(self):
        """Capture one live reader owner, independent of selected presentation."""
        owner, reader = self.owner, self.reader
        app = getattr(owner, 'app', owner)
        workspace, session = getattr(owner, 'workspace', None), getattr(owner, 'session', None)
        token = workspace.token(session.id) if workspace is not None and session is not None else None
        manager = getattr(owner, 'manager', None)
        def current(expected_reader=reader):
            if (self.terminal or self.reader is not expected_reader or not getattr(app, 'active_host', True)
                    or getattr(owner, 'app', owner) is not app
                    or getattr(owner, 'workspace', None) is not workspace
                    or getattr(owner, 'session', None) is not session
                    or getattr(owner, 'manager', None) is not manager
                    or getattr(owner, '_provider_document', None) is not self
                    or (manager is not None and getattr(app, 'private_sessions', manager) is not manager)
                    or (session is not None and workspace.sessions.get(session.id) is not session)
                    or (token is not None and not workspace.accepts(token))
                    or (manager is not None and (getattr(manager, 'terminal', False)
                        or manager.controllers.get(session.id) is not owner))):
                return False
            try:
                access = getattr(owner, 'document_access', None)
                if access is not None:
                    access()
            except ValueError:
                return False
            return True
        return current

    def begin_operation(self, current):
        """Reserve this reader until all borrows and any committed save settle."""
        if not self.can_start() or not current():
            raise OSError('The private document is no longer available.')
        operation = self._operation = _DocumentOperation(self, current)
        self.cancel = operation.cancel
        try:
            self.set_busy(True)
        except BaseException:
            self._operation = self.cancel = None
            self.busy = False
            idle = getattr(self.owner, 'operation_idle', None)
            if idle is not None:
                idle.set()
            raise
        return operation

    async def _borrow(self, operation, function, *args, reconcile=False, **kwargs):
        """Keep the compatibility worker marker until the actual thread retires."""
        if self._operation is not operation or self.worker is not None:
            raise OSError('The private document operation does not own this reader.')
        worker = self.worker = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        try:
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError as error:
                if operation.cancellation is None:
                    operation.cancellation = error
                operation.cancel.set()
                await drain_worker(worker)
                # Writes may already have committed. Their returned reader and
                # progress must be reconciled before propagating cancellation.
                if reconcile and not worker.cancelled() and worker.exception() is None:
                    return worker.result()
                operation.raise_cancelled()
        finally:
            self.worker = None

    async def read(self, operation, function, *args):
        """Borrow a decoder; cancelled reads never publish their late output."""
        if not operation.current():
            raise PermissionError('The current provider session cannot read this document.')
        check_cancelled(operation.cancel.is_set)
        result = await self._borrow(operation, function, *args)
        check_cancelled(operation.cancel.is_set)
        return result

    async def save_reader(self, operation, save, value, *, sample_progress=False):
        """Own a committed result through progress preparation and adoption.

        An obsolete or failed handoff releases only a newly returned reader;
        returning the existing reader never transfers its ownership away.
        Cancellation is deferred until the caller reconciles its editable
        baseline, then raised by the caller or finish_operation.
        """
        if not operation.current():
            raise PermissionError('The current provider session cannot save this document.')
        original = operation.reader
        result = await self._borrow(operation, save, original, value,
                                    cancelled=operation.cancel.is_set, reconcile=True)
        replacement = None
        try:
            if not operation.current():
                return result
            progress = getattr(self.owner, '_provider_progress', None)
            if progress is not None:
                if sample_progress:
                    progress.sample_surface()

                def prepare():
                    nonlocal replacement
                    from .provider_progress import ProviderProgress
                    replacement = ProviderProgress(self.owner, self.owner._crypt_reader_store, result, result.key)
                    replacement.load()

                await self._borrow(operation, prepare, reconcile=True)
            if not operation.current():
                return result
            self._replace_reader(result)
            operation.reader = result
            if replacement is not None and operation.current():
                progress = progress.replace_with(replacement)
                replacement = None  # replace_with adopts or closes its successor.
                if sample_progress and operation.current():
                    progress.watch_surface(initial=True)
            return result
        finally:
            # Also runs on progress load failure or cancellation. The session
            # retains failed reader closes for its normal disposal retry.
            if result is not original and self.reader is not result:
                self.release_reader(result)
            if replacement is not None and getattr(self.owner, '_provider_progress', None) is not replacement:
                if not self.release_progress(replacement):
                    raise OSError('Saved reader progress cleanup is incomplete; retry retirement.')

    def finish_operation(self, operation):
        """Release internal ownership even when its old native controls are stale."""
        if self._operation is not operation or self.worker is not None:
            raise OSError('The private document operation has not retired.')
        self._operation = None
        self.cancel = None
        self.busy = False
        idle = getattr(self.owner, 'operation_idle', None)
        if idle is not None:
            idle.set()
        if operation.current():
            self.owner.set_cloud_busy(False)
        else:
            manager = getattr(self.owner, 'manager', None)
            revoke = getattr(manager, 'revoke_stale', None)
            app = getattr(self.owner, 'app', self.owner)
            if (revoke is not None and getattr(app, 'active_host', True)
                    and getattr(app, 'private_sessions', manager) is manager
                    and manager.controllers.get(self.owner.session.id) is self.owner
                    and not getattr(manager, 'terminal', False)):
                revoke()
        operation.raise_cancelled()

    def release_progress(self, progress):
        """Retain an unpublished progress owner if retiring it needs a retry."""
        if not any(retained is progress for retained in self._progress_cleanup):
            self._progress_cleanup.append(progress)
        try:
            progress.close()
        except Exception:
            return False
        self._progress_cleanup[:] = [item for item in self._progress_cleanup if item is not progress]
        return True

    def release_reader(self, reader):
        """Retry failed native closes without repeating successful source closes."""
        if reader is None:
            return True
        entry = next((entry for entry in self._reader_cleanup if entry[0] is reader), None)
        if entry is None:
            entry = (reader, set())
            self._reader_cleanup.append(entry)
        done = entry[1]
        failed = False
        for name in ('_markdown_media', 'pdf', 'source'):
            resource = getattr(reader, name, None)
            if name in done:
                continue
            try:
                close = getattr(resource, 'close', None)
                if close is not None:
                    close()
            except Exception:
                failed = True
            else:
                done.add(name)
        if hasattr(reader, 'password'):
            reader.password = ''
        if not failed:
            self._reader_cleanup[:] = [item for item in self._reader_cleanup if item is not entry]
        return not failed

    def dispose(self):
        """Reusable close, or retry of already admitted terminal retirement."""
        progress = getattr(self.owner, '_provider_progress', None)
        if self._operation is not None or self.worker is not None or getattr(progress, 'worker', None) is not None:
            raise OSError('The private document is still in use.')
        if self.closed and not self._reader_cleanup and not self._progress_cleanup:
            return
        owner = self.owner
        failed = []
        def clean(name, action):
            if name in self._disposed:
                return
            try:
                action()
            except Exception:
                failed.append(name)
            else:
                self._disposed.add(name)
        def resource(name, target, method):
            if target is not None:
                clean(name, getattr(target, method))
        from .comic_feedback import clear as clear_comic_feedback
        clean('comic-guidance', lambda: clear_comic_feedback(getattr(owner, 'app', owner), owner=owner))
        resource('footer', getattr(getattr(owner, 'crypt_view', None), 'page_footer', None), 'dispose')
        resource('progress', progress, 'retire' if self.terminal else 'close')
        for retained in tuple(self._progress_cleanup):
            if not self.release_progress(retained):
                failed.append('retained-progress')
        for name in ('_provider_layout_task', '_provider_width_task'):
            resource(name, getattr(owner, name, None), 'cancel')
        for name in ('provider_epub_view', 'pdf_search', 'pdf_contents'):
            resource(name, getattr(owner, name, None), 'dispose')
        reader = self._reader
        # Presentation failure must never skip decoder/source/password cleanup.
        if self.release_reader(reader):
            self._reader = None
            if reader is not None and getattr(reader, 'kind', None) == '.pdf':
                reader.data = b''
                from services.documents.readers import MemorySource
                if isinstance(reader.source, MemorySource):
                    reader.source.data = b''
        else:
            failed.append('reader')
        for retained, _ in tuple(self._reader_cleanup):
            if retained is not reader and not self.release_reader(retained):
                failed.append('retained-reader')
        from .page_animation import cancel_page_slide
        clean('page-slide', lambda: cancel_page_slide(getattr(owner, 'crypt_content', None)))
        from .ios_content_background import clear
        clean('background', lambda: clear(getattr(owner, 'app', owner)))
        for key, field in self.metadata_fields.items():
            clean('metadata:' + key, lambda field=field: setattr(field, 'value', ''))
        if hasattr(owner, 'crypt_metadata_view'):
            clean('metadata-view', lambda: setattr(owner.crypt_metadata_view, 'content', None))
            clean('metadata-status', lambda: setattr(owner.crypt_metadata_status, 'text', ''))
        resource('markdown', getattr(owner, '_provider_markdown', None), 'dispose')
        if hasattr(owner, 'crypt_text'):
            clean('text-value', lambda: setattr(owner.crypt_text, 'value', ''))
            if hasattr(owner.crypt_text, 'dispose'):
                resource('text', owner.crypt_text, 'dispose')
        for name in ('provider_spread', 'crypt_image'):
            resource(name, getattr(owner, name, None), 'dispose')
        if hasattr(owner, 'crypt_page'):
            clean('page', lambda: setattr(owner.crypt_page, 'items', []))
        for name in ('epub_session_bookmarks', 'crypt_bookmarks'):
            resource(name, getattr(owner, name, None), 'clear')
        if hasattr(owner, 'crypt_bookmark_selector'):
            clean('bookmarks', lambda: setattr(owner.crypt_bookmark_selector, 'items', []))
        if hasattr(owner, 'crypt_title'):
            clean('title', lambda: setattr(owner.crypt_title, 'text', 'Encrypted copy closed'))
        if hasattr(owner, 'crypt_password'):
            clean('password', lambda: setattr(owner.crypt_password, 'value', ''))
        from .external_display import sync as sync_external
        clean('external', lambda: sync_external(getattr(owner, 'app', owner)))
        if failed:
            raise OSError('Private document cleanup is incomplete; retry retirement.')
        owner._provider_epub_locations = {}
        owner._provider_progress = None
        for name in ('provider_epub_view', '_provider_layout_task', '_provider_width_task'):
            if hasattr(owner, name):
                delattr(owner, name)
        self.metadata_fields = {}
        self.metadata_initial = {}
        self.metadata_values = {}
        self.closed = True
