"""Bounded, memory-only provider sessions; private bytes never enter recovery."""
from hashlib import sha256
from pathlib import Path
from logisticsmobile.provider_ui import ProviderUI
from .reader_host import ReaderHost

MAX_PRIVATE_SESSIONS = 4
MAX_PRIVATE_BYTES = 32 * 1024 * 1024


class PrivateController(ReaderHost, ProviderUI):
    def __init__(self, manager, session):
        self.manager, self.app, self.session = manager, manager.app, session
        self.crypt_reader = None
        self.crypt_metadata_fields = {}
        self.crypt_metadata_initial = {}
        self.crypt_metadata_values = {}
        self._crypt_cancel = None
        self.operation_busy = False
        self.presentation_destination = 'documents'
        self.privacy_gate = None

    @property
    def cloud_busy(self):
        return self.operation_busy

    def set_cloud_busy(self, busy):
        self.operation_busy = busy
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
        document_title = reader.name if reader is not None else self.session.title
        kwargs.update(destination=self.__dict__.get('presentation_destination', 'documents'), route=kwargs.get('route') or 'private:' + self.session.id,
                      title=kwargs.get('title') or document_title or 'Private document')
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
            if getattr(self, 'page_suspended', False):
                self.page_suspended = False
                self.app.loop.create_task(self.read_crypt_page())

    def close_crypt(self, widget=None, **kwargs):
        if self.private_dirty():
            return self.app.request_provider_close(self)
        if self.manager.close(self.session.id):
            self.app.show_documents_hub()

    def discard_crypt(self, widget=None, **kwargs):
        if self.manager.close(self.session.id, discard=True):
            self.app.show_documents_hub()

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

    def suspend(self, *, except_owner=None, keep_active_markdown=False):
        for owner in self.controllers.values():
            if owner is except_owner:
                continue
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

    async def open(self, copies, key, *, prepared=None, destination='documents', privacy_gate=None, edit=False):
        from .files_ui import local_read_available
        if not hasattr(self.app, 'cloud_view'):
            self.app.show_cloud(present=False)
            restore = getattr(self.app, 'cloud_restore_task', None)
            if restore is not None:
                await restore
        independent = self.app.cloud_busy and local_read_available(self.app, private=True) and getattr(copies, 'offline', False)
        if self.app.cloud_busy and not independent:
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
            self.app.cloud_status.value = 'Close a provider document before opening another (limit: 4). Unsaved edits were kept.'
            return False
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
        session = self.app.workspace.open('provider-session', identity, 'text', transient=True)
        self.app.workspace.active = selection
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
            opened = await ProviderUI.open_crypt(owner, copies=copies, key=key, prepared=prepared, independent=independent, edit=edit)
            if not opened or not self.app.active_host or not self.app.workspace.accepts(token):
                retire_open()
                return False
            reader = owner.crypt_reader
            total = sum(len(getattr(value.crypt_reader, 'data', b'') or b'')
                        for value in self.controllers.values())
            if total > MAX_PRIVATE_BYTES:
                retire_open()
                self.app.cloud_status.value = 'Private content exceeds the 32 MiB memory budget. Close an item and retry; existing edits were kept.'
                return False
            session.kind = ('pdf' if reader.kind == '.pdf' else 'epub' if reader.kind == '.epub' else 'comic' if not reader.editable
                            else 'markdown' if reader.kind in {'.md', '.markdown'} else 'text')
            session.title = reader.name
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
            return True
        except Exception:
            retire_open()
            raise
        finally:
            owner._opening_origin = owner._opening_token = None
            owner._independent_operation = False
            if remote_open:
                self.app.set_cloud_busy(False)
                self.app.remote_read_busy = False

    @staticmethod
    def offline_owner(owner):
        source = getattr(getattr(owner, 'crypt_reader', None), 'source', None)
        return (getattr(getattr(owner, '_crypt_reader_store', None), 'offline', False)
                or (getattr(source, 'cache_token', None) is not None and not source.closed))

    def activate(self, key, *, destination='documents'):
        owner = self.controllers.get(key)
        if not self.available(key) or (self.app.cloud_busy and not ((getattr(self.app, 'transfer_busy', False) or getattr(self.app, 'remote_read_busy', False)) and self.offline_owner(owner))):
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
        local = (getattr(self.app, 'transfer_busy', False) or getattr(self.app, 'remote_read_busy', False)) and self.offline_owner(owner)
        if not force and ((self.app.cloud_busy and not local) or owner._crypt_cancel is not None or owner.operation_busy):
            return False
        if not force and owner.private_dirty() and not discard:
            owner.resume_crypt()
            owner.crypt_title.text = 'Unsaved changes: save,\nor discard and close.'
            return False
        reader = owner.crypt_reader
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
        return True
