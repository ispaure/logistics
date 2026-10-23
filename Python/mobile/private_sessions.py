"""Bounded, memory-only provider sessions; private bytes never enter recovery."""
from .composition.assembly import composed_workflow
from features.books.mobile.provider_controller import ProviderBookController
from features.comics.mobile.provider_controller import ProviderComicController

from hashlib import sha256
from pathlib import Path
from mobile.provider_ui import ProviderUI
from .reader_host import ReaderHost

MAX_PRIVATE_SESSIONS = 4
from .reader_memory import PRIVATE_BUFFERS, private_buffer_bytes

MAX_PRIVATE_BYTES = PRIVATE_BUFFERS


@composed_workflow('provider_book_controller', ProviderBookController)
@composed_workflow('provider_comic_controller', ProviderComicController)
class PrivateController(ReaderHost, ProviderUI):
    def __init__(self, manager, session):
        self.manager, self.app, self.session = manager, manager.app, session
        from .composition.presentation import reading_presentation
        self.format_services = reading_presentation(self)
        self.provider_document()
        self._crypt_cancel = None
        self.operation_busy = False
        import asyncio
        self.operation_idle = asyncio.Event()
        self.operation_idle.set()
        self.presentation_destination = self.app.native_host.state.destination
        self.privacy_gate = None

    @property
    def cloud_busy(self):
        return self.operation_busy

    def set_cloud_busy(self, busy):
        self.operation_busy = busy
        if busy:
            self.operation_idle.clear()
        else:
            self.operation_idle.set()
        self.manager.update_session(self)
        if not busy:
            self.manager.revoke_stale()

    def cancel_cloud(self, widget=None, **kwargs):
        if self._crypt_cancel is not None:
            self._crypt_cancel.set()

    def _show_crypt_content(self, kind, content, *, view=None):
        return self.app._show_crypt_content(kind, content, view=view or self, owner=self)

    def show_view(self, view, **kwargs):
        origin = getattr(self, '_opening_origin', None)
        if origin is not None:
            if not self.app.active_host or not self.app.workspace.accepts(self._opening_token):
                return False
            destination, navigation, selection = origin
            if (self.app.native_host.state.destination != destination or self.app.navigation_generation != navigation
                    or self.app.workspace.active != selection):
                # The loaded session stays available without taking over the
                # view or selection the user chose while its bytes were read.
                return True
        self.manager.bind(self)
        reader = self.crypt_reader
        document_title = Path(reader.name).name if reader is not None else self.session.title
        suffix = ':metadata' if view is getattr(self, 'crypt_metadata_view', None) else ''
        kwargs.update(destination=self.__dict__.get('presentation_destination', 'documents'), route=kwargs.get('route') or 'private:' + self.session.id + suffix,
                      title=kwargs.get('title') or document_title or 'Private document')
        epub = getattr(self, 'provider_epub_view', None)
        if epub is not None:
            epub.on_tools_changed = self.app.adaptive.render
        presented = self.app.show_view(view, **kwargs)
        if origin is not None:
            self._open_presented = bool(presented)
        return presented

    def resume_crypt(self, widget=None, **kwargs):
        if self.manager.available(self.session.id) and self.crypt_reader is not None:
            self.show_view(self.crypt_view)
            mode = getattr(self, 'crypt_markdown_mode', None)
            if mode == 'preview' and getattr(self, 'crypt_preview', None) not in self.crypt_content.children:
                self.toggle_private_preview()
            elif (mode == 'edit' and getattr(self.crypt_edit_mode, 'value', '') == 'Formatted'
                  and getattr(self, 'crypt_formatted', None) is None):
                self.show_private_markdown_editor()
            self.resume_suspended_page()

    def resume_suspended_page(self):
        """Reload released pixels without changing the retained route or chrome."""
        task = getattr(self, '_resume_page_task', None)
        if (not getattr(self, 'page_suspended', False) or self.cloud_busy
                or not self.manager.available(self.session.id)
                or (task is not None and not task.done())):
            return
        self._resume_page_task = self.app.loop.create_task(self.read_crypt_page())

    def close_crypt(self, widget=None, **kwargs):
        return self.app.request_reader_close(self.session.id)

    def discard_crypt(self, widget=None, **kwargs):
        return self.app.close_session(self.session.id, choice='discard')

    async def show_editor_open(self, widget=None, **kwargs):
        return await self.app.show_editor_open(widget, **kwargs)

    async def show_crypt_save_as(self, widget=None, **kwargs):
        if self.app.cloud_busy or self.session.id not in self.app.workspace.sessions:
            return
        self.manager.bind(self)
        return await self.app.show_crypt_save_as(widget, owner=self, **kwargs)


class PrivateSessions:
    def __init__(self, app):
        self.app = app
        self.controllers = {}
        self.active = None
        self.positions = {}

    async def opening_rejected(self, message):
        """Admission failures must be visible from every folder entry point."""
        import toga
        self.app.cloud_status.value = message
        await self.app.main_window.dialog(toga.InfoDialog('Could not open document', message))
        return False

    def revoke_stale(self):
        """A credential replacement in any scene also retires displayed bytes."""
        import toga
        for key, owner in list(self.controllers.items()):
            if (getattr(owner, 'credential_client', None) is self.app.cloud_client
                    and getattr(owner, 'credential_generation', None) == getattr(self.app.cloud_client, 'generation', None)):
                continue
            if not getattr(getattr(owner, '_crypt_reader_store', None), 'encrypted', True):
                continue
            self.app.workspace.invalidate(key)
            pending = owner._crypt_cancel
            if pending is not None:
                pending.set()
            if pending is None and not owner.operation_busy:
                self.close(key, discard=True, force=True)
            else:
                # Cancellation may still be retiring a worker. Clear the UI now;
                # its completion cannot present content with the invalid token.
                reader = owner.crypt_reader
                owner._crypt_cancel = None
                try:
                    ProviderUI.clear_private_reader(owner, discard=True)
                finally:
                    owner._crypt_cancel = pending
                source = getattr(reader, 'source', None)
                if hasattr(source, 'close'):
                    source.close()
            owner.session.title = ''
            view = getattr(owner, 'crypt_view', None)
            if view is not None:
                for child in list(view.children):
                    view.remove(child)
                view.add(toga.Label('Private session locked. Reopen after unlocking.'))

    @staticmethod
    def identity(copies, key):
        provider = getattr(copies, 'provider', None)
        root = getattr(provider, 'root', getattr(copies, 'root', None))
        if root is None:
            raise ValueError('Provider sessions require a stable storage namespace.')
        namespace = str(Path(root).resolve())
        return sha256((namespace + '\0' + str(key)).encode()).hexdigest()

    def available(self, key):
        owner = self.controllers.get(key)
        if owner is None or owner.crypt_reader is None:
            return False
        store = getattr(owner, '_crypt_reader_store', None)
        if not getattr(store, 'encrypted', True):
            return True
        return (getattr(owner, 'credential_client', None) is self.app.cloud_client
                and self.app.cloud_client is not None
                and getattr(owner, 'credential_generation', None) == getattr(self.app.cloud_client, 'generation', None))

    def bind(self, owner):
        self.suspend(except_owner=owner)
        readers = getattr(self.app, 'readers', None)
        if readers is not None and readers.active is not None:
            readers.active.suspend()
        self.active = owner
        self.app.workspace.activate(owner.session.id)
        self.update_session(owner)

    def update_session(self, owner):
        owner.session.dirty = owner.private_dirty()

    def remember_position(self, owner):
        reader = owner.crypt_reader
        if reader is None:
            return
        from .reader_lifecycle import scroll_position
        position = self.positions.pop(owner.session.resource, {})
        if reader.editable:
            text = getattr(owner, 'crypt_text', None)
            preview = getattr(owner, 'crypt_preview', None)
            content = getattr(owner, 'crypt_content', None)
            if content is not None and preview is not None and preview in content.children:
                position['preview_scroll'] = scroll_position(preview)
            if content is not None and text in content.children:
                position['text_scroll'] = scroll_position(text)
        else:
            index = getattr(owner, '_provider_displayed_index', 0)
            panel = getattr(owner, 'provider_epub_view', None)
            offset = getattr(panel, 'offset', 0)
            if panel is None and reader.book is not None:
                offset = getattr(owner, '_provider_epub_locations', {}).get(reader.book.spine[index], 0)
            position.update(index=index, offset=offset)
        self.positions[owner.session.resource] = position
        while len(self.positions) > 256:
            del self.positions[next(iter(self.positions))]

    async def restore_text_position(self, owner, position):
        from .reader_lifecycle import restore_scroll, restore_loaded_scroll, restore_drawn_scroll
        from commonUtils.ui.native.draw_ready import wait_for_draw
        await wait_for_draw(owner.crypt_view)
        if not self.available(owner.session.id):
            return
        restore_scroll(owner.crypt_text, position.get('text_scroll'))
        preview = getattr(owner, 'crypt_preview', None)
        if preview is None or position.get('preview_scroll') is None:
            return
        valid = lambda: self.available(owner.session.id) and owner.crypt_preview is preview
        if not getattr(owner.crypt_preview_search, 'ready', False):
            restore_loaded_scroll(preview, position['preview_scroll'],
                valid)
        if valid():
            await restore_drawn_scroll(preview, position['preview_scroll'], valid)

    def suspend(self, *, except_owner=None, keep_active_markdown=False):
        from .ios_content_background import clear
        clear(self.app)
        for owner in self.controllers.values():
            if owner is except_owner:
                continue
            self.remember_position(owner)
            # Memory trimming also runs when Android backgrounds the activity.
            # The retained reader must still show the same surface on wake;
            # clearing its preview would expose the source input underneath.
            if (keep_active_markdown and owner is self.active
                    and getattr(owner.crypt_reader, 'kind', None) in {'.md', '.markdown'}):
                continue
            for name in ('_provider_layout_task', '_provider_width_task'):
                task = getattr(owner, name, None)
                if task is not None:
                    task.cancel()
                    setattr(owner, name, None)
            from .page_animation import cancel_page_slide
            cancel_page_slide(getattr(owner, 'crypt_content', None))
            owner.clear_private_preview()
            for name in ('provider_spread', 'provider_epub_view'):
                view = getattr(owner, name, None)
                if view is not None:
                    view.dispose()
                    if view in owner.crypt_content.children:
                        owner.crypt_content.remove(view)
                    delattr(owner, name)
                    owner.page_suspended = True
            image = getattr(owner, 'crypt_image', None)
            if image is not None and image.image is not None:
                image.image = None
                owner.page_suspended = True
            source = getattr(owner.crypt_reader, 'source', None)
            if hasattr(source, 'cache'):
                source.cache.clear()
                source.cache_bytes = 0
        from .external_display import sync as sync_external
        sync_external(self.app)

    async def open(self, copies, key, *, prepared=None, destination=None, privacy_gate=None, edit=False):
        destination = destination or self.app.native_host.state.destination
        from .files_ui import local_read_available, ordinary_local_copies
        if not hasattr(self.app, 'cloud_view'):
            self.app.show_cloud(present=False)
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None and not ordinary_local_copies(copies):
                await restore
        independent = (self.app.cloud_busy and getattr(copies, 'offline', False)
            and local_read_available(self.app, private=not ordinary_local_copies(copies)))
        if self.app.cloud_busy and not independent:
            if getattr(copies, 'remote_storage', False):
                from features.rclone.mobile.cloud_ui import explain_remote_busy
                await explain_remote_busy(self.app)
            return False
        identity = self.identity(copies, key)
        existing = next((owner for owner in self.controllers.values()
                         if owner.session.resource == identity), None)
        if existing is not None and prepared is None and not self.available(existing.session.id):
            self.app.cloud_status.value = 'Unlock the connection again before reopening this private document.'
            return False
        if existing is not None and prepared is None:
            existing.presentation_destination = destination
            self.app.crypt_password.value = ''
            self.bind(existing)
            existing.resume_crypt()
            if edit and existing.crypt_reader.kind in {'.md', '.markdown'} and not getattr(existing.crypt_reader, 'read_only', False):
                existing.clear_private_preview()
                existing.show_private_markdown_editor()
            return True
        if len(self.controllers) >= MAX_PRIVATE_SESSIONS:
            return await self.opening_rejected(
                f'All {MAX_PRIVATE_SESSIONS} file document slots are in use. Local, LocalCrypt and remote files share this limit. '
                'Go to Documents → Open documents and close one, then try again. Existing documents and unsaved edits were kept.')
        if prepared is None and not self.app.checkpoint():
            return False
        previous = self.active
        # A restored list entry is only metadata; release its placeholder slot
        # before claiming the real reader, and restore it automatically on failure.
        from .document_sources import file_source
        try:
            source = file_source(self.app, copies, key, session_only=True)
        except (OSError, ValueError, AttributeError, KeyError):
            source = None
        if source is not None:
            for pending in list(self.app.workspace.sessions.values()):
                if pending.provider == 'credential-reference' and getattr(pending, 'cache_source', None) == source:
                    self.app.workspace.close(pending.id, guard=lambda session: True)
        selection = self.app.workspace.active
        origin = self.app.native_host.state.destination, self.app.navigation_generation, selection
        try:
            session = self.app.workspace.open('provider-session', identity, 'text', transient=True)
        except ValueError as error:
            return await self.opening_rejected(str(error) + '\n\nGo to Documents → Open documents to manage open items.')
        self.app.workspace.active = selection
        owner = self._register_opening_owner(session, copies, destination=destination,
                                             privacy_gate=privacy_gate, independent=independent)
        token = self.app.workspace.token(session.id)
        owner._opening_origin, owner._opening_token, owner._open_presented = origin, token, False
        def retire_open():
            bound = self.active is owner
            self.close(session.id, discard=True, force=True)
            if bound and self.app.active_host and previous is not None and previous.session.id in self.controllers:
                previous.resume_crypt()
        remote_open = getattr(copies, 'remote_storage', False)
        if remote_open:
            self.app.remote_read_busy = True
            self.app.set_cloud_busy(True)
        try:
            opened = await owner.provider_document().opening.open( copies=copies, key=key, prepared=prepared, independent=independent, edit=edit)
            if not opened or not self.app.active_host or not self.app.workspace.accepts(token):
                retire_open()
                return False
            reader = owner.crypt_reader
            total = private_buffer_bytes(self.controllers.values())
            if total > MAX_PRIVATE_BYTES:
                retire_open()
                return await self.opening_rejected(
                    'This document would exceed the shared 32 MiB file content memory budget. '
                    'Go to Documents → Open documents and close an item, then try again. '
                    'A document that exceeds the budget by itself cannot be opened. Existing documents and unsaved edits were kept.')
            return await self._publish_opened_session(owner, session, reader, copies, key,
                                                      identity=identity, privacy_gate=privacy_gate)
        except Exception:
            retire_open()
            raise
        finally:
            owner._opening_origin = owner._opening_token = None
            owner._independent_operation = False
            if remote_open:
                self.app.set_cloud_busy(False)
                self.app.remote_read_busy = False

    def _register_opening_owner(self, session, copies, *, destination, privacy_gate, independent):
        owner = PrivateController(self, session)
        if getattr(copies, 'encrypted', True) or getattr(copies, 'remote_storage', False):
            owner.privacy_gate = getattr(self.app.cloud_client, 'session_privacy', None)
        if privacy_gate is not None:
            owner.privacy_gate = privacy_gate
        owner.credential_client = self.app.cloud_client
        owner.credential_generation = getattr(self.app.cloud_client, 'generation', None)
        owner.presentation_destination = destination
        owner._independent_operation = independent
        self.controllers[session.id] = owner
        return owner

    async def _publish_opened_session(self, owner, session, reader, copies, key, *, identity, privacy_gate):
        position = self.positions.get(identity)
        if position is not None and not reader.editable:
            index, offset = position.get('index', 0), position.get('offset', 0)
            index = min(index, len(reader.labels) - 1)
            if reader.book is not None:
                owner._provider_epub_locations = {reader.book.spine[index]: offset}
            await owner.move_private_page(index)
        session.kind = ('pdf' if reader.kind == '.pdf' else 'epub' if reader.kind == '.epub' else 'comic' if not reader.editable
                        else 'markdown' if reader.kind in {'.md', '.markdown'} else 'text')
        session.title = Path(reader.name).name
        from .document_sources import file_source
        try:
            session.history_source = file_source(self.app, copies, key) if privacy_gate is None else None
        except (OSError, ValueError, AttributeError, KeyError):
            session.history_source = None
        if privacy_gate is None:
            try:
                source = file_source(self.app, copies, key, session_only=True)
                self.app.credential_document_lists.remember(session, source)
            except (OSError, ValueError, AttributeError, KeyError):
                self.app.credential_document_lists.notice()
        if owner._open_presented:
            self.bind(owner)
        else:
            self.suspend(except_owner=self.active)
        self.app.save_workspace()
        if position is not None and reader.editable:
            await self.restore_text_position(owner, position)
        return True

    @staticmethod
    def offline_owner(owner):
        source = getattr(getattr(owner, 'crypt_reader', None), 'source', None)
        return (getattr(getattr(owner, '_crypt_reader_store', None), 'offline', False)
                or (getattr(source, 'cache_token', None) is not None and not source.closed))

    def activate(self, key, *, destination=None):
        destination = destination or self.app.native_host.state.destination
        owner = self.controllers.get(key)
        from .files_ui import ordinary_local_copies
        local = ordinary_local_copies(getattr(owner, '_crypt_reader_store', None))
        if not self.available(key) or (self.app.cloud_busy and not (local or ((getattr(self.app, 'transfer_busy', False) or getattr(self.app, 'remote_read_busy', False)) and self.offline_owner(owner)))):
            if self.available(key) and getattr(getattr(owner, '_crypt_reader_store', None), 'remote_storage', False):
                from features.rclone.mobile.cloud_ui import explain_remote_busy
                self.app.loop.create_task(explain_remote_busy(self.app))
            return False
        owner.presentation_destination = destination
        self.bind(owner)
        owner.resume_crypt()
        self.app.credential_document_lists.remember(owner.session)
        self.app.save_workspace()
        return True

    def dirty(self):
        return any(owner.private_dirty() for owner in self.controllers.values())

    def close(self, key, *, discard=False, force=False):
        owner = self.controllers.get(key)
        if owner is None:
            return False
        from .files_ui import ordinary_local_copies
        local = (ordinary_local_copies(getattr(owner, '_crypt_reader_store', None))
            or ((getattr(self.app, 'transfer_busy', False) or getattr(self.app, 'remote_read_busy', False)) and self.offline_owner(owner)))
        if not force and ((self.app.cloud_busy and not local) or owner._crypt_cancel is not None or owner.operation_busy):
            return False
        if not force and owner.private_dirty() and not discard:
            owner.resume_crypt()
            owner.crypt_title.text = 'Unsaved changes: save,\nor discard and close.'
            return False
        reader = owner.crypt_reader
        if reader is not None and not force:
            self.remember_position(owner)
        if not ProviderUI.clear_private_reader(owner, discard=True):
            return False
        source = getattr(reader, 'source', None)
        if hasattr(source, 'close'):
            source.close()
        if hasattr(reader, 'password'):
            reader.password = ''
        if not force:
            self.app.credential_document_lists.closed(owner.session)
        owner.session.title = ''
        owner.session.view.clear()
        owner.session.dirty = False
        self.app.workspace.close(key, guard=lambda session: True)
        del self.controllers[key]
        if self.active is owner:
            self.update_session(owner)
            self.active = None
        self.app.save_workspace()
        privacy = getattr(self.app, 'screen_privacy', None)
        if privacy is not None:
            privacy.refresh()
        return True

    def clear(self, *, discard=False):
        owners = list(self.controllers.values())
        if any(owner._crypt_cancel is not None or owner.operation_busy for owner in owners):
            return False
        dirty = next((owner for owner in owners if owner.private_dirty()), None)
        if dirty is not None and not discard:
            dirty.resume_crypt()
            dirty.crypt_title.text = 'Unsaved changes: save,\nor discard and close.'
            return False
        for owner in owners:
            self.close(owner.session.id, discard=True, force=True)
        self.positions.clear()
        return True
