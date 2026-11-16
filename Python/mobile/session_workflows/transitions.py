"""Prepare, veto, commit and retirement orchestration for mobile sessions."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CloseDecision:
    key: str
    choice: str
    provider: str = ''
    token: tuple | None = None
    allowed: bool = False
    reason: str = ''


@dataclass(frozen=True)
class CloseResult:
    committed: bool
    reason: str = ''


class SessionTransitions:
    def __init__(self, host):
        self.host = host

    def prepare(self, key, *, choice='keep'):
        host = self.host
        session = host.workspace.sessions.get(key)
        if session is None or choice == 'cancel':
            return CloseDecision(key, choice, reason='missing' if session is None else 'cancelled')
        if choice not in ('keep', 'save', 'discard', 'delete'):
            raise ValueError('Unsupported close action.')
        if choice == 'delete' and (session.provider != 'managed-text' or key not in host.text_views):
            return CloseDecision(key, choice, reason='unsupported-delete')
        return CloseDecision(key, choice, session.provider, host.workspace.token(key), True)

    def commit(self, decision):
        host = self.host
        if not decision.allowed:
            return CloseResult(False, decision.reason)
        if not host.workspace.accepts(decision.token):
            return CloseResult(False, 'stale')
        from .adapters import ADAPTERS
        adapter = ADAPTERS.get(decision.provider)
        if adapter is None:
            return CloseResult(False, 'unsupported-provider')
        leaving = decision.key in host.__dict__.get('_reader_closing', ())
        done = adapter(host, decision.key, decision.choice, leaving_reader=leaving)
        return CloseResult(bool(done), '' if done else 'vetoed')

    def close(self, key, *, choice='keep'):
        return self.commit(self.prepare(key, choice=choice))

    def require_notebook_replacement_safe(self):
        # Match close_notebook's retention decision. A successful document.save
        # clears dirty even when the editor's last checkpoint flag remains set.
        for panel in getattr(self.host, '_notebook_views', {}).values():
            document = panel.document
            if (document is not None and document.dirty
                    and getattr(panel.editor, 'checkpoint_unconfirmed', False)):
                raise OSError('Notebook recovery is unconfirmed. Save or close the notebook before replacing this workspace.')

    def preserve_for_replacement(self, receipt=None):
        self.require_notebook_replacement_safe()
        host = self.host
        private = getattr(host, 'private_sessions', None)
        if private is not None:
            private.require_replacement_safe(receipt)
        library = getattr(host, 'vault_browser', None)
        if library is not None and library.embedded is not None:
            # A native DOM/ink event may still be queued even when dirty is false.
            raise OSError('Save or close the Notes Library document before replacing this workspace.')
        store = getattr(host, 'store', None)
        if store is not None:
            store.flush_checkpoints()
        lists = getattr(host, 'credential_document_lists', None)
        if lists is not None:
            lists.flush_writes()
        if hasattr(host, 'chat_current') and not host.checkpoint_chat():
            raise OSError('Could not preserve the previous conversation.')
        if private is not getattr(host, 'private_sessions', None):
            raise OSError('The private workspace changed during replacement.')
        if private is not None:
            private.require_replacement_safe(receipt)
        self.require_notebook_replacement_safe()

    def checkpoint_for_exit(self):
        host = self.host
        if host.__dict__.get('_document_close_tasks'):
            return False
        library = getattr(host, 'vault_browser', None)
        if library is not None and library.embedded is not None:
            # Always flush through the async close path: a clean Python model can
            # still have native keystrokes or ink waiting for bridge delivery.
            if library.session is not None:
                self.request_close_session(library.session.id)
            return False
        if hasattr(host, 'chat_current') and not host.checkpoint_chat():
            return False
        return host.checkpoint()

    def request_close_session(self, key, *, _markdown_flushed=False, _notebook_flushed=False,
                              _notebook_unflushed=False, _progress_flushed=False):
        host = self.host
        library = getattr(host, 'vault_browser', None)
        if not _markdown_flushed:
            if self._defer_notes_library_close(key, library) or self._defer_markdown_close(key):
                return True

        if host.visible_reader() == key:
            host.__dict__.setdefault('_reader_closing', set()).add(key)
        book = self._book_controller(key)
        if book is not None and host.book_edits_dirty(book):
            return host.request_book_close(book)

        notebook = getattr(host, '_notebook_views', {}).get(key)
        if notebook is not None:
            if not _notebook_flushed and _uses_native_notebook_input(notebook):
                return self._defer_notebook_close(key, notebook)
            if notebook.document is not None and (notebook.document.dirty or _notebook_unflushed
                    or getattr(notebook, 'native_input_pending', False)):
                return self._prompt_notebook_close(key, notebook)

        private = host.provider_sessions().controllers.get(key)
        if private is not None and private.private_dirty():
            return host.request_provider_close(private)
        progress = getattr(private, '_provider_progress', None)
        if progress is not None and not _progress_flushed:
            if self._defer_provider_progress_close(key, private, progress):
                return True

        owner = host.text_views.get(key)
        if owner is None or not owner.document.modified:
            return host.close_session(key)
        return host.document_close_dialog(key, owner.document.name,
            lambda: host.close_session(key, choice='save'),
            lambda: host.close_session(key, choice='discard'))

    def _defer_notes_library_close(self, key, library):
        if (library is None or library.session is None or library.session.id != key
                or library.embedded is None):
            return False
        if getattr(library, '_close_task', None):
            return True
        host = self.host

        async def close_library():
            try:
                if await library.prepare_leave() and host.active_host:
                    library._approved_close = library.embedded
                    try:
                        self.request_close_session(key, _markdown_flushed=True)
                    finally:
                        library._approved_close = None
            finally:
                library._close_task = None

        library._close_task = host.loop.create_task(close_library())
        return True

    def _defer_markdown_close(self, key):
        host = self.host
        owner = host.text_views.get(key) or host.provider_sessions().controllers.get(key)
        formatted = getattr(owner, 'formatted', None)
        area = getattr(owner, 'editor_area', None)
        workflow = getattr(owner, '_provider_markdown', None)
        if workflow is not None:
            formatted, area = workflow.formatted, workflow.content
        if formatted is None or area is None or formatted.view not in area.children:
            return False

        from commonUtils.ui.native.text_size import native_backend
        if not native_backend(formatted.view).startswith(('toga_iOS.', 'toga_android.')):
            return False
        if getattr(owner, '_markdown_close_task', None) is not None:
            return True

        async def flush_then_close():
            try:
                await formatted.flush()
                if host.active_host and key in host.workspace.sessions:
                    self.request_close_session(key, _markdown_flushed=True)
            except ValueError as error:
                target = getattr(owner, 'status', None) or getattr(owner, 'crypt_title', None)
                if target is not None:
                    target.text = str(error)
            finally:
                owner._markdown_close_task = None

        owner._markdown_close_task = host.loop.create_task(flush_then_close())
        return True

    def _defer_notebook_close(self, key, notebook):
        if getattr(notebook, '_native_close_task', None) is not None:
            return True
        host = self.host
        token = host.workspace.token(key)

        async def flush_notebook_then_close():
            try:
                await notebook.flush_input()
                if host.active_host and host.workspace.accepts(token):
                    self.request_close_session(key, _notebook_flushed=True)
            except (OSError, ValueError, TimeoutError):
                if not notebook.closed and host.active_host and host.workspace.accepts(token):
                    # A stalled WebView must not trap the user before the
                    # explicit Save/Discard/Cancel decision.
                    self.request_close_session(key, _notebook_flushed=True, _notebook_unflushed=True)
            finally:
                notebook._native_close_task = None

        notebook._native_close_task = host.loop.create_task(flush_notebook_then_close())
        return True

    def _prompt_notebook_close(self, key, notebook):
        from services.documents.mobile_notebooks import notebook_title
        host = self.host

        async def save_notebook():
            try:
                if _uses_native_notebook_input(notebook):
                    if not await notebook.save_from_view():
                        return
                else:
                    await notebook.perform({'op': 'save'})
                if not notebook.document.dirty and not getattr(notebook, 'native_input_pending', False):
                    host.close_session(key)
            except (OSError, ValueError, TimeoutError) as error:
                from services.documents.mobile_notebooks import show_notebook_close_error
                show_notebook_close_error(host, notebook, error)

        return host.document_close_dialog(key, notebook_title(notebook),
            lambda: host.loop.create_task(save_notebook()),
            lambda: host.close_session(key, choice='discard'))

    def _defer_provider_progress_close(self, key, owner, progress):
        progress.sample_surface()
        if progress.schedule(immediate=True) is None:
            return False
        if getattr(owner, '_progress_close_task', None) is not None:
            return True
        host = self.host
        token = host.workspace.token(key)

        async def close_after_progress():
            try:
                while host.active_host and host.workspace.accepts(token):
                    generation = progress.generation
                    await progress.flush()
                    if not host.active_host or not host.workspace.accepts(token):
                        return
                    if progress.pending is None and self.request_close_session(
                            key, _markdown_flushed=True, _progress_flushed=True):
                        return
                    # A native page callback can enqueue a newer position as
                    # the write finishes. Keep the close intent through that
                    # write, but leave a failed write available for explicit retry.
                    if progress.generation == generation:
                        host.__dict__.setdefault('_reader_closing', set()).discard(key)
                        return
            finally:
                owner._progress_close_task = None

        owner._progress_close_task = host.loop.create_task(close_after_progress())
        return True


    def cancel_close_session(self, key):
        host = self.host
        host.__dict__.setdefault('_reader_closing', set()).discard(key)
        owner = host.text_views.get(key)
        if owner is not None:
            owner.bind()
            host.workspace.activate(key)
            host.show_documents(resume=True)


    def request_reader_close(self, key):
        host = self.host
        if key not in host.workspace.sessions:
            return False
        token = host.workspace.token(key)
        host.__dict__.setdefault('_reader_closing', set()).add(key)

        book = self._book_controller(key)
        if book is not None:
            if getattr(book, '_exit_task', None) is not None:
                return True
            if book.book_busy or book.request_position_flush() is not None:
                return self._defer_reader_close(key, token, book, self._wait_for_book_close)
        else:
            private = host.provider_sessions().controllers.get(key)
            progress = getattr(private, '_provider_progress', None)
            if private is not None and (private.operation_busy
                                        or getattr(progress, 'worker', None) is not None):
                if getattr(private, '_exit_task', None) is not None:
                    return True
                return self._defer_reader_close(key, token, private, self._wait_for_provider_close)
        return host.request_close_session(key)

    def _book_controller(self, key):
        readers = getattr(self.host, 'readers', None)
        return readers.controllers.get(key) if readers is not None else None

    def _defer_reader_close(self, key, token, owner, wait_until_ready):
        if getattr(owner, '_exit_task', None) is not None:
            return True
        host = self.host

        async def finish():
            try:
                ready = await wait_until_ready(owner, token)
                if ready is not False and host.active_host and host.workspace.accepts(token):
                    host.request_close_session(key)
                elif ready is False:
                    host._reader_closing.discard(key)
            finally:
                owner._exit_task = None

        owner._exit_task = host.loop.create_task(finish())
        return True

    async def _wait_for_book_close(self, book, token):
        host = self.host
        while host.active_host and host.workspace.accepts(token):
            if book.book_busy:
                await book._book_idle.wait()
                continue
            progress = getattr(book, '_book_progress', None)
            if progress is None:
                return True
            await progress.flush()
            if progress.pending is not None:
                return False
            if not book.book_busy:
                return True
        return False

    async def _wait_for_provider_close(self, private, token):
        import asyncio
        host = self.host
        while host.active_host and host.workspace.accepts(token):
            if private.operation_busy:
                await private.operation_idle.wait()
                continue
            progress = getattr(private, '_provider_progress', None)
            if getattr(progress, 'worker', None) is None:
                break
            await asyncio.wait({progress.task})

    def keep_reader_editing(self, key):
        host = self.host
        host.__dict__.setdefault('_reader_closing', set()).discard(key)
        owner = host.provider_sessions().controllers.get(key)
        if owner is not None:
            owner.resume_crypt()
        else:
            book = self._book_controller(key)
            if book is not None:
                book.show_view(book.book_metadata_view, reader_route='metadata', title='Edit metadata')
            else:
                host.cancel_close_session(key)


    def request_book_close(self, owner):
        host = self.host
        async def save():
            await owner.save_book_metadata()
            if not host.book_edits_dirty(owner):
                host.close_session(owner.session.id)
        return host.document_close_dialog(owner.session.id, owner.session.title,
            save, lambda: host.close_session(owner.session.id, choice='discard'))


    def document_close_dialog(self, key, title, save, discard):
        host = self.host
        import inspect
        from services.documents.authoring.document_dialogs import DocumentDialog
        pending = host.__dict__.setdefault('_document_close_tasks', {})
        if key in pending:
            return True
        if key not in host.workspace.sessions:
            return False
        token = host.workspace.token(key)
        async def decide():
            try:
                choice = await host.main_window.dialog(DocumentDialog(
                    'Save changes to ' + title + '?',
                    'Your unsaved changes will be lost if you quit without saving.'))
                if not host.active_host or not host.workspace.accepts(token):
                    return
                if choice in ('save', 'discard'):
                    result = (save if choice == 'save' else discard)()
                    if inspect.isawaitable(result):
                        await result
            finally:
                # Cancellation or a failed dialog/save must also allow retrying.
                if key in host.workspace.sessions:
                    host.__dict__.setdefault('_reader_closing', set()).discard(key)
                pending.pop(key, None)
        pending[key] = host.loop.create_task(decide())
        return True


    def reader_closed(self, key, *, refresh_roots=False):
        host = self.host
        returns = host.__dict__.setdefault('_reader_returns', {})
        target = returns.pop(key, None)
        closing = host.__dict__.setdefault('_reader_closing', set())
        leaving = key in closing
        closing.discard(key)
        # Retire every presentation of this closed session, including a close
        # prompt or a retained reader in another destination's stack. List/menu
        # closes must do this too, even without a visible-reader exit intent.
        for current, screens in host.routes.screens.items():
            index = next((i for i, (name, panel, _) in enumerate(screens)
                          if name in ('private:' + key, 'reader:' + key, 'notebook:' + key,
                                      'notes-library:' + key, 'close:' + key,
                                      'private-close:' + key)
                          or any(getattr(child, '_reader_session_id', None) == key for child in panel.children)), None)
            if index is not None:
                host.routes.trim(current, index)
                if refresh_roots and not host.routes.screens[current]:
                    host.refresh_hub(current)
                host.routes.render(current)
        details = host.adaptive.detail_routes
        index = next((i for i, (name, panel, _) in enumerate(details)
                      if name == 'notebook:' + key or any(getattr(child, '_reader_session_id', None) == key for child in panel.children)), None)
        if index is not None:
            host.adaptive.trim_details(index)
        # Both hubs retain rows even while another destination is visible.
        # Publish the committed session state before returning to either hub.
        host.refresh_document_list()
        host.refresh_home_documents()
        if not leaving or target is None:
            if host.native_host.state.destination == 'home' and not host.routes.screens['home']:
                host.routes.render('home')
                return
            host.show_documents_hub()
            return
        destination, route, drawer = target
        screens = host.routes.screens[destination]
        count = next((i + 1 for i, screen in enumerate(screens) if screen[0] == route), 0)
        host.routes.trim(destination, count)
        if destination == 'documents' and host.adaptive.split is not None:
            host.adaptive.show_list()
        if refresh_roots and route is None:
            # A retained root can still contain the reader's old recent row.
            # Rebuild it from the committed workspace/store before revealing it.
            host.refresh_hub(destination)
        # This restores an existing route, not a second tap on Documents (which
        # intentionally collapses its stack to the overview).
        host.native_host.activate(destination)
        host.routes.render(destination)
        host.routes.folders.restore(destination)
        if drawer:
            host.adaptive.menu_open[destination] = True
            host.adaptive.render(preserve_drawer=True)
        if route is not None:
            host.loop.call_soon(host.routes.folders.restore_viewport, destination, route)


def _uses_native_notebook_input(notebook):
    return getattr(notebook, 'native_transport', False) or getattr(notebook, 'has_native_canvas', False)


def transitions_for(host):
    owner = host.__dict__.get('_session_transitions')
    if owner is None:
        owner = host._session_transitions = SessionTransitions(host)
    return owner
