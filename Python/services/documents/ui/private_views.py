"""Retire displayed private views when their credential generation is revoked."""
from commonUtils.ui import pyside as qt
from features.rclone import session
from weakref import WeakSet

_guards = WeakSet()


def resolve_private_edits_before_lock(window, save):
    buttons = qt.QMessageBox.StandardButton
    answer = qt.QMessageBox.question(window, 'Lock credentials',
        'Save changes before locking this credential package?',
        buttons.Save | buttons.Discard | buttons.Cancel, buttons.Cancel)
    if answer == buttons.Save:
        save()
        return False  # A save worker must retire before locking.
    return answer == buttons.Discard


def prepare_credential_lock(paths):
    """Resolve private edits before a requested lock; revocation itself never waits."""
    paths = tuple(paths)
    for guard in tuple(_guards):
        guard.follow_provider()
        context = getattr(guard.provider, 'context', None)
        config = getattr(guard.provider, 'config_path', None)
        affected = (context is not None and any(session.registry.depends_on(context, path) for path in paths))
        affected = affected or (config is not None and any(config == path.with_suffix('.conf') for path in paths))
        if affected:
            if not guard.prepare_lock():
                return False
    return True


class PrivateViewGuard(qt.QObject):
    revoked = qt.Signal()

    def __init__(self, window, provider):
        super().__init__(window)
        self.window, self.locked, self.provider = window, False, provider
        self.unsubscribe = lambda: None
        self.revoked.connect(self.check_revocation)
        window.installEventFilter(self)
        self.bind(provider)
        _guards.add(self)
        window.destroyed.connect(lambda: _guards.discard(self))
        window.destroyed.connect(lambda: self.unsubscribe())
        idle = getattr(window, 'idle', None)
        if idle is not None:
            idle.connect(self.follow_provider)

    def bind(self, provider):
        self.unsubscribe()
        self.provider = provider
        self.unsubscribe = (session.on_forget(provider.context, self.invalidate)
                            if getattr(provider, 'private', False) and hasattr(provider, 'context') else lambda: None)

    def current_provider(self):
        choice = getattr(self.window, 'pending_choice', None) or getattr(self.window, 'choice', None)
        if choice is not None:
            return choice.provider
        storage = getattr(getattr(self.window, 'viewer', None), 'storage', None)
        return getattr(storage, 'provider', self.provider)

    def follow_provider(self):
        current = self.current_provider()
        if current is not self.provider:
            self.bind(current)

    def check_revocation(self):
        self.follow_provider()
        if (getattr(self.provider, 'private', False) and hasattr(self.provider, 'context')
                and session.credentials(self.provider.context) is None):
            self.retire()

    def invalidate(self):
        self.revoked.emit()

    def prepare_lock(self):
        if self.locked:
            return True
        prepare = getattr(self.window, 'prepare_credential_lock', None)
        if prepare is not None:
            return prepare()
        for name in ('operation', 'open_operation'):
            if getattr(getattr(self.window, name, None), 'busy', False):
                return False
        viewer = getattr(self.window, 'viewer', None)
        if viewer is not None and hasattr(viewer, 'can_close'):
            return viewer.can_close()
        editor = getattr(self.window, 'editor', None)
        if isinstance(editor, qt.QPlainTextEdit) and editor.document().isModified():
            return resolve_private_edits_before_lock(self.window, self.window.save)
        return True

    def retire(self):
        self.locked = True
        self.window.hide()
        self.window.setEnabled(False)
        self.window.setWindowTitle('Private session locked')
        changed = getattr(self.window, 'title_changed', None)
        if changed is not None:
            changed.emit('Private session locked')

    def eventFilter(self, watched, event):
        if self.locked and event.type() == qt.QEvent.Type.WindowTitleChange:
            if self.window.windowTitle() != 'Private session locked':
                self.window.setWindowTitle('Private session locked')
        if self.locked and event.type() == qt.QEvent.Type.Show:
            self.window.hide()
            return True
        return False


def protect_private_view(window, provider):
    window.document_provider = provider
    if hasattr(window, '_private_view_guard'):
        return window
    if getattr(provider, 'private', False) and hasattr(provider, 'context'):
        window._private_view_guard = PrivateViewGuard(window, provider)
    return window
