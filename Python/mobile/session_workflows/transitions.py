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

    def preserve_for_replacement(self):
        host = self.host
        store = getattr(host, 'store', None)
        if store is not None:
            store.flush_checkpoints()
        lists = getattr(host, 'credential_document_lists', None)
        if lists is not None:
            lists.flush_writes()
        if hasattr(host, 'chat_current') and not host.checkpoint_chat():
            raise OSError('Could not preserve the previous conversation.')

    def checkpoint_for_exit(self):
        host = self.host
        if host.__dict__.get('_document_close_tasks'):
            return False
        if hasattr(host, 'chat_current') and not host.checkpoint_chat():
            return False
        return host.checkpoint()

    def request_close_session(self, key, *, _markdown_flushed=False):
        host = self.host
        if not _markdown_flushed:
            owner = host.text_views.get(key) or host.provider_sessions().controllers.get(key)
            formatted = getattr(owner, 'formatted', None)
            area = getattr(owner, 'editor_area', None)
            workflow = getattr(owner, '_provider_markdown', None)
            if workflow is not None:
                formatted, area = workflow.formatted, workflow.content
            if formatted is not None and area is not None and formatted.view in area.children:
                from commonUtils.ui.native.text_size import native_backend
                if native_backend(formatted.view).startswith(('toga_iOS.', 'toga_android.')):
                    if getattr(owner, '_markdown_close_task', None) is None:
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
        if host.visible_reader() == key:
            host.__dict__.setdefault('_reader_closing', set()).add(key)
        readers = getattr(host, 'readers', None)
        book = readers.controllers.get(key) if readers is not None else None
        if book is not None and host.book_edits_dirty(book):
            return host.request_book_close(book)
        private = host.provider_sessions().controllers.get(key)
        if private is not None and private.private_dirty():
            return host.request_provider_close(private)
        owner = host.text_views.get(key)
        if owner is None or not owner.document.modified:
            return host.close_session(key)
        return host.document_close_dialog(key, owner.document.name,
            lambda: host.close_session(key, choice='save'),
            lambda: host.close_session(key, choice='discard'))


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
        readers = getattr(host, 'readers', None)
        owner = readers.controllers.get(key) if readers is not None else None
        pending = getattr(owner, '_epub_location_task', None)
        if pending is not None and pending.done():
            pending = None
        if pending is not None:
            owner.request_position_flush()
        else:
            private = host.provider_sessions().controllers.get(key)
            if private is not None and private.operation_busy:
                owner = private
                if getattr(owner, '_exit_task', None) is not None:
                    return True
                pending = private.operation_idle.wait()
        if pending is not None:
            if getattr(owner, '_exit_task', None) is None:
                async def finish():
                    try:
                        await pending
                        if host.active_host and host.workspace.accepts(token):
                            host.request_close_session(key)
                    finally:
                        owner._exit_task = None
                owner._exit_task = host.loop.create_task(finish())
            return True
        return host.request_close_session(key)


    def keep_reader_editing(self, key):
        host = self.host
        host.__dict__.setdefault('_reader_closing', set()).discard(key)
        owner = host.provider_sessions().controllers.get(key)
        if owner is not None:
            owner.resume_crypt()
        else:
            readers = getattr(host, 'readers', None)
            book = readers.controllers.get(key) if readers is not None else None
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
        from ..document_dialogs import DocumentDialog
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


    def reader_closed(self, key):
        host = self.host
        returns = host.__dict__.setdefault('_reader_returns', {})
        target = returns.pop(key, None)
        closing = host.__dict__.setdefault('_reader_closing', set())
        leaving = key in closing
        closing.discard(key)
        if not leaving or target is None:
            host.show_documents_hub()
            return
        destination, route, drawer = target
        # Retire every presentation of this closed session, including a close
        # prompt or a retained reader in another destination's stack.
        for current, screens in host.routes.screens.items():
            index = next((i for i, (name, panel, _) in enumerate(screens)
                          if name in ('private:' + key, 'reader:' + key, 'close:' + key,
                                      'private-close:' + key)
                          or any(getattr(child, '_reader_session_id', None) == key for child in panel.children)), None)
            if index is not None:
                host.routes.trim(current, index)
        details = host.adaptive.detail_routes
        index = next((i for i, (_, panel, _) in enumerate(details)
                      if any(getattr(child, '_reader_session_id', None) == key for child in panel.children)), None)
        if index is not None:
            host.adaptive.trim_details(index)
        screens = host.routes.screens[destination]
        count = next((i + 1 for i, screen in enumerate(screens) if screen[0] == route), 0)
        host.routes.trim(destination, count)
        if destination == 'documents' and host.adaptive.split is not None:
            host.adaptive.show_list()
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



def transitions_for(host):
    owner = host.__dict__.get('_session_transitions')
    if owner is None:
        owner = host._session_transitions = SessionTransitions(host)
    return owner
