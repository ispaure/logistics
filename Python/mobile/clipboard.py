"""Native clipboard routing for the shared credential runtime and every scene."""
from weakref import WeakKeyDictionary

from services.clipboard_policy import blocked

KEY = 'restrict_session_clipboard'
_controllers = WeakKeyDictionary()


def backend(app):
    return type(app._impl).__module__.partition('.')[0]


def supported(app):
    return backend(app) in {'toga_iOS', 'toga_android'}


def controller(app):
    process = app.protection.process
    return _controllers.get(process)


def install(app):
    if not supported(app) or controller(app) is not None:
        return
    policy = MobileClipboard(app.protection.process, app.preferences, backend(app))
    _controllers[policy.process] = policy
    policy.process.listeners.add(policy)


class MobileClipboard:
    def __init__(self, process, preferences, platform):
        self.process = process
        self.preferences = preferences
        self.android = platform == 'toga_android'
        if self.android:
            from .native.android_clipboard import install
            self.publish = install(self.restricted)
        else:
            from .native.ios_clipboard import install
            install(self.restricted)
            self.publish = lambda: None
        self.publish()

    def restricted(self):
        return blocked(self.preferences.values[KEY] == 'true', self.process)

    def protection_changed(self, _active):
        self.publish()

    def copy_text(self, text):
        if self.restricted():
            return False
        if self.android:
            from .native.android_clipboard import copy_text
        else:
            from .native.ios_clipboard import copy_text
        copy_text(text)
        return True
