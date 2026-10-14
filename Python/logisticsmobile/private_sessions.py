"""Bounded, memory-only provider sessions; private bytes never enter recovery."""
from hashlib import sha256
from pathlib import Path
from .localcrypt_ui import LocalCryptUI

MAX_PRIVATE_SESSIONS = 4
MAX_PRIVATE_BYTES = 32 * 1024 * 1024
FIELDS = ('crypt_reader', '_crypt_reader_store', 'crypt_title', 'crypt_page',
          'crypt_read_page', 'crypt_text', 'crypt_image', 'crypt_content', 'crypt_save',
          'crypt_view', 'crypt_metadata_fields', 'crypt_metadata_initial',
          'crypt_metadata_values', 'crypt_metadata_view', 'crypt_metadata_status',
          'crypt_metadata_save', 'crypt_tools_view', 'crypt_actions', 'crypt_actions_menu')
SHARED = {'crypt_password', 'crypt_copies', 'crypt_labels', 'crypt_selector'}


class PrivateController(LocalCryptUI):
    def __init__(self, manager, session):
        self.manager, self.app, self.session = manager, manager.app, session
        self.crypt_reader = None
        self.crypt_metadata_fields = {}
        self.crypt_metadata_initial = {}
        self.crypt_metadata_values = {}
        self._crypt_cancel = None

    def __getattr__(self, name):
        if (name.startswith('crypt_') and name not in SHARED) or name == '_crypt_reader_store':
            raise AttributeError(name)
        return getattr(self.app, name)

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        if name == '_crypt_cancel' and hasattr(self, 'app'):
            self.app._crypt_cancel = value

    def set_cloud_busy(self, busy):
        self.app.set_cloud_busy(busy)
        self.manager.publish(self)

    def _show_crypt_content(self, kind, content, *, view=None):
        return self.app._show_crypt_content(kind, content, view=view or self)

    def show_view(self, view, **kwargs):
        self.manager.bind(self)
        kwargs.update(destination='documents', route=kwargs.get('route') or 'private:' + self.session.id,
                      title=kwargs.get('title') or 'Private document')
        return self.app.show_view(view, **kwargs)

    def resume_crypt(self, widget=None, **kwargs):
        if self.session.id in self.app.workspace.sessions and self.crypt_reader is not None:
            self.show_view(self.crypt_view)
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
        return await self.app.show_crypt_save_as(widget, **kwargs)


class PrivateSessions:
    def __init__(self, app):
        self.app = app
        self.controllers = {}
        self.active = None

    @staticmethod
    def identity(copies, key):
        provider = getattr(copies, 'provider', None)
        root = getattr(provider, 'root', getattr(copies, 'root', None))
        if root is None:
            raise ValueError('Provider sessions require a stable storage namespace.')
        namespace = str(Path(root).resolve())
        return sha256((namespace + '\0' + str(key)).encode()).hexdigest()

    def bind(self, owner):
        self.suspend(except_owner=owner)
        readers = getattr(self.app, 'readers', None)
        if readers is not None and readers.active is not None:
            readers.active.suspend()
        self.active = owner
        self.app.workspace.activate(owner.session.id)
        self.publish(owner)

    def publish(self, owner):
        owner.session.dirty = owner.private_dirty()
        if self.active is owner:
            for field in FIELDS:
                if field in owner.__dict__:
                    setattr(self.app, field, owner.__dict__[field])

    def suspend(self, *, except_owner=None):
        for owner in self.controllers.values():
            if owner is except_owner:
                continue
            image = getattr(owner, 'crypt_image', None)
            if image is not None and image.image is not None:
                image.image = None
                owner.page_suspended = True
            source = getattr(owner.crypt_reader, 'source', None)
            if hasattr(source, 'cache'):
                source.cache.clear()
                source.cache_bytes = 0

    async def open(self, copies, key, *, prepared=None):
        if self.app.cloud_busy:
            return False
        identity = self.identity(copies, key)
        existing = next((owner for owner in self.controllers.values()
                         if owner.session.resource == identity), None)
        if existing is not None and prepared is None:
            self.app.crypt_password.value = ''
            self.bind(existing)
            existing.resume_crypt()
            return True
        if len(self.controllers) >= MAX_PRIVATE_SESSIONS:
            self.app.cloud_status.value = 'Close a provider document before opening another (limit: 4). Unsaved edits were kept.'
            return False
        if prepared is None and not self.app.checkpoint():
            return False
        previous = self.active
        session = self.app.workspace.open('provider-session', identity, 'text', transient=True)
        owner = PrivateController(self, session)
        self.controllers[session.id] = owner
        token = self.app.workspace.token(session.id)
        try:
            opened = await LocalCryptUI.open_crypt(owner, copies=copies, key=key, prepared=prepared)
            if not opened or not self.app.active_host or not self.app.workspace.accepts(token):
                self.close(session.id, discard=True, force=True)
                if previous is not None and previous.session.id in self.controllers:
                    self.bind(previous)
                return False
            reader = owner.crypt_reader
            total = sum(len(getattr(value.crypt_reader, 'data', b'') or b'')
                        for value in self.controllers.values())
            if total > MAX_PRIVATE_BYTES:
                self.close(session.id, discard=True, force=True)
                if previous is not None and previous.session.id in self.controllers:
                    self.bind(previous)
                self.app.cloud_status.value = 'Private content exceeds the 32 MiB memory budget. Close an item and retry; existing edits were kept.'
                return False
            session.kind = ('epub' if reader.kind == '.epub' else 'comic' if not reader.editable
                            else 'markdown' if reader.kind in {'.md', '.markdown'} else 'text')
            session.title = reader.name
            self.bind(owner)
            self.app.save_workspace()
            return True
        except Exception:
            self.close(session.id, discard=True, force=True)
            if previous is not None and previous.session.id in self.controllers:
                self.bind(previous)
            raise

    def activate(self, key):
        owner = self.controllers.get(key)
        if owner is None or self.app.cloud_busy:
            return False
        self.bind(owner)
        owner.resume_crypt()
        return True

    def dirty(self):
        return any(owner.private_dirty() for owner in self.controllers.values())

    def close(self, key, *, discard=False, force=False):
        owner = self.controllers.get(key)
        if owner is None:
            return False
        if not force and (self.app.cloud_busy or owner._crypt_cancel is not None):
            return False
        if not force and owner.private_dirty() and not discard:
            owner.resume_crypt()
            owner.crypt_title.text = 'Unsaved changes: save,\nor discard and close.'
            return False
        reader = owner.crypt_reader
        if not LocalCryptUI.clear_private_reader(owner, discard=True):
            return False
        source = getattr(reader, 'source', None)
        if hasattr(source, 'close'):
            source.close()
        if hasattr(reader, 'password'):
            reader.password = ''
        owner.session.title = ''
        owner.session.view.clear()
        owner.session.dirty = False
        self.app.workspace.close(key, guard=lambda session: True)
        del self.controllers[key]
        if self.active is owner:
            self.publish(owner)
            self.active = None
            self.app.crypt_reader = None
        self.app.save_workspace()
        return True

    def clear(self, *, discard=False):
        owners = list(self.controllers.values())
        if any(owner._crypt_cancel is not None for owner in owners):
            return False
        dirty = next((owner for owner in owners if owner.private_dirty()), None)
        if dirty is not None and not discard:
            dirty.resume_crypt()
            dirty.crypt_title.text = 'Unsaved changes: save,\nor discard and close.'
            return False
        for owner in owners:
            self.close(owner.session.id, discard=True, force=True)
        return True
