"""Retire displayed private views when their credential generation is revoked."""
from commonUtils.ui import pyside as qt
from features.rclone import session


class PrivateViewGuard(qt.QObject):
    revoked = qt.Signal()

    def __init__(self, window, provider):
        super().__init__(window)
        self.window, self.locked, self.provider = window, False, provider
        self.unsubscribe = lambda: None
        self.revoked.connect(self.check_revocation)
        window.installEventFilter(self)
        self.bind(provider)
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
    if hasattr(window, '_private_view_guard'):
        return window
    if getattr(provider, 'private', False) and hasattr(provider, 'context'):
        window._private_view_guard = PrivateViewGuard(window, provider)
    return window
