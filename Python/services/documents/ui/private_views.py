"""Retire displayed private views when their credential generation is revoked."""
from commonUtils.ui import pyside as qt
from services.documents.protection import document_protections
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
        affected = any(protection.affected_by(paths) for protection in guard.protections)
        if affected:
            if not guard.prepare_lock():
                return False
    return True


class PrivateViewGuard(qt.QObject):
    revoked = qt.Signal()

    def __init__(self, window, provider):
        super().__init__(window)
        self.window, self.locked, self.provider = window, False, provider
        self.subscriptions = []
        self.protections = ()
        self._retiring = self._retired = False
        self.revoked.connect(self.check_revocation)
        window.installEventFilter(self)
        self.bind(provider)
        _guards.add(self)
        window.destroyed.connect(lambda: _guards.discard(self))
        window.destroyed.connect(self.unsubscribe)
        idle = getattr(window, 'idle', None)
        if idle is not None:
            idle.connect(self.check_revocation)

    def unsubscribe(self, *_):
        subscriptions, self.subscriptions = self.subscriptions, []
        failure = None
        for release in subscriptions:
            try:
                release()
            except Exception as error:
                self.subscriptions.append(release)
                failure = failure or error
        if failure is not None:
            raise failure

    def bind(self, provider):
        try:
            self.unsubscribe()
            self.provider = provider
            self.protections = tuple(document_protections(provider))
            for protection in self.protections:
                self.subscriptions.append(protection.on_revoke(self.invalidate))
        except Exception:
            # A failed handoff must not leave newly private content interactive.
            self.retire()
            raise

    def current_provider(self):
        resolve = getattr(self.window, 'resource_provider', None)
        if resolve is not None:
            return resolve() or self.provider
        choice = getattr(self.window, 'pending_choice', None) or getattr(self.window, 'choice', None)
        if choice is not None:
            return choice.provider
        storage = getattr(getattr(self.window, 'viewer', None), 'storage', None)
        return getattr(storage, 'provider', self.provider)

    def follow_provider(self):
        try:
            current = self.current_provider()
        except Exception:
            self.retire()
            raise
        if current is not self.provider:
            self.bind(current)

    def check_revocation(self):
        self.follow_provider()
        try:
            for protection in self.protections:
                protection.check()
        except (OSError, ValueError):
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
        if self._retiring:
            return
        self._retiring = True
        try:
            first = not self.locked
            self.locked = True
            self.window.hide()
            self.window.setEnabled(False)
            self.window.setWindowTitle('Private session locked')
            if first:
                changed = getattr(self.window, 'title_changed', None)
                if changed is not None:
                    changed.emit('Private session locked')
            if not self._retired:
                retire = getattr(self.window, 'retire_private_content', None)
                if retire is not None:
                    retire()
                self._retired = True
        finally:
            # Failed cleanup remains locked and can be retried after recovery.
            self._retiring = False

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
    if not hasattr(window, '_private_view_guard'):
        # Ordinary editors can become private through Save As. Follow their
        # provider from the beginning, including commonUtils text hosts.
        window._private_view_guard = PrivateViewGuard(window, provider)
    window._private_view_guard.check_revocation()
    return window
