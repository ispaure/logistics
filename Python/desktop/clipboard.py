"""Qt clipboard commands and the process-wide desktop protection scope."""
from pathlib import Path
from weakref import ref

from commonUtils.ui import pyside as qt
from features.settings import settings_store
from services.clipboard_policy import blocked
from services.desktop_video_access import session_contexts
from services.protection import ProtectionScope

FIELD = ('Privacy', 'restrict_session_clipboard_bool')
CONFIG = Path(__file__).resolve().parents[1] / 'configFile.ini'
PROTECTION = ProtectionScope(session_contexts)
_STANDARD_KEYS = qt.QKeySequence.StandardKey
_KEYS = (_STANDARD_KEYS.Cut, _STANDARD_KEYS.Copy, _STANDARD_KEYS.Paste)
_MENU_ACTIONS = {'edit-cut', 'edit-copy', 'edit-paste', 'link-copy'}
_WEB_ACTIONS = {'Cut', 'Copy', 'Paste', 'PasteAndMatchStyle', 'CopyLinkToClipboard',
                'CopyImageToClipboard', 'CopyImageUrlToClipboard', 'CopyMediaUrlToClipboard'}


def enabled():
    return settings_store(CONFIG).safe_values().get(FIELD, 'false').lower() == 'true'


def clipboard_blocked():
    return blocked(enabled(), PROTECTION)


def guarded(callback):
    def invoke():
        if not clipboard_blocked():
            return callback()
    return invoke


def guard_markdown_actions(viewer):
    """Bind the shared Actions used by the workspace and standalone Edit menus."""
    def select_copy_target():
        return viewer.active_editor() if viewer.edit_button.isChecked() else viewer.browser

    for action, target, method in (
        (viewer.cut_action, viewer.active_editor, 'cut'),
        (viewer.copy_action, select_copy_target, 'copy'),
        (viewer.paste_action, viewer.active_editor, 'paste'),
    ):
        action.triggered.disconnect()
        action.triggered.connect(guarded(lambda target=target, method=method: getattr(target(), method)()))


def _clipboard_target(widget):
    while isinstance(widget, qt.QWidget):
        if _text_target(widget) or widget.inherits('QWebEngineView'):
            return True
        widget = widget.parentWidget()
    return False


def _text_target(widget):
    return isinstance(widget, (qt.QLineEdit, qt.QTextEdit, qt.QPlainTextEdit)) or (
        isinstance(widget, qt.QLabel) and bool(widget.textInteractionFlags() & (
            qt.Qt.TextInteractionFlag.TextSelectableByMouse | qt.Qt.TextInteractionFlag.TextSelectableByKeyboard)))


def _clipboard_key(event):
    if any(event.matches(key) for key in _KEYS):
        return True
    # WebEngine also supports Paste and Match Style from the keyboard.
    if event.key() != qt.Qt.Key.Key_V:
        return False
    shift = qt.Qt.KeyboardModifier.ShiftModifier
    return any(binding.count() == 1 and binding[0].key() == event.key()
               and event.modifiers() == (binding[0].keyboardModifiers() | shift)
               for binding in qt.QKeySequence.keyBindings(_STANDARD_KEYS.Paste))


def _clipboard_menu_action(action):
    if action.objectName() in _MENU_ACTIONS:
        return True
    parent = action.parent()
    if parent is not None and parent.inherits('QWebEnginePage'):
        return any(parent.action(key) is action for key in type(parent).WebAction if key.name in _WEB_ACTIONS)
    return False


class ClipboardFilter(qt.QObject):
    def __init__(self, app):
        super().__init__(app)
        self.menu_states = {}
        app.installEventFilter(self)

    def _filter_menu(self, menu):
        if not clipboard_blocked():
            return
        for action in menu.actions():
            if action.isEnabled() and _clipboard_menu_action(action):
                if menu not in self.menu_states:
                    self.menu_states[menu] = set()
                    menu.destroyed.connect(lambda *_, owner=ref(menu): self.menu_states.pop(owner(), None))
                self.menu_states[menu].add(action)
                action.setEnabled(False)

    def eventFilter(self, receiver, event):
        kind = qt.QEvent.Type
        event_type = event.type()
        if isinstance(receiver, qt.QMenu):
            if event_type in (kind.Show, kind.KeyPress, kind.MouseButtonRelease):
                self._filter_menu(receiver)
            elif event_type == kind.Hide:
                # Qt hides a popup before dispatching the selected action.
                actions = self.menu_states.pop(receiver, ())
                if actions:
                    qt.QTimer.singleShot(0, self, lambda: _restore_actions(actions))
        if event_type in (kind.ShortcutOverride, kind.KeyPress) and _clipboard_key(event):
            if _clipboard_target(receiver) and clipboard_blocked():
                event.accept()
                return True
        if event_type in (kind.MouseButtonPress, kind.MouseButtonRelease) and (
            event.button() == qt.Qt.MouseButton.MiddleButton and _clipboard_target(receiver)
            and clipboard_blocked()
        ):
            return True
        return False


def _restore_actions(actions):
    from shiboken6 import isValid
    for action in actions:
        if isValid(action):
            action.setEnabled(True)


def install(app):
    if not hasattr(app, '_logistics_clipboard'):
        app._logistics_clipboard = ClipboardFilter(app)
