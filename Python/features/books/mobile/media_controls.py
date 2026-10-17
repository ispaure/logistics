"""One process-wide Now Playing owner; metadata never contains document text."""
from weakref import WeakSet

_owners = WeakSet()
_active = None


class SpeechPlayback:
    def __init__(self, panel, app, *, gate=lambda: None, valid=lambda: True, factory=None):
        self.panel, self.app, self.gate, self.valid = panel, app, gate, valid
        self.factory = factory or native_media
        self.media, self.closed = None, False
        self.media_error = ""
        _owners.add(self)

    def allowed(self):
        return (not self.closed and getattr(self.app, 'active_host', True) and self.valid() and (self.gate() is None
            or self.app.preferences.values.get('session_speech_when_locked', 'false') == 'true'))

    def active(self):
        return self.allowed() and self.panel.session.state in {'speaking', 'paused'}

    def can_start(self):
        gate = self.gate()
        inactive = getattr(getattr(self.app, 'screen_privacy', None), 'inactive', False)
        return (not self.closed and getattr(self.app, 'active_host', True) and self.valid()
            and (gate is None or (not gate.locked and not inactive) or self.allowed()))

    def changed(self, state):
        global _active
        if self.closed:
            return
        if state in {'speaking', 'paused'}:
            if _active is not None and _active is not self:
                _active.panel.session.stop()
            _active = self
            if self.allowed():
                try:
                    if self.media is None:
                        self.media = self.factory(self.app.loop, self.command)
                    self.media.update(state)
                except Exception as error:
                    self.media_error = str(error)
                    self.clear()
            else:
                self.clear()
        else:
            self.clear()
            if _active is self:
                _active = None

    def command(self, action):
        if not self.active():
            self.enforce()
            return False
        session = self.panel.session
        if action == 'play':
            session.resume()
        elif action == 'pause':
            session.pause()
        elif action == 'toggle':
            session.resume() if session.state == 'paused' else session.pause()
        elif action == 'back':
            session.skip(-15)
        elif action == 'forward':
            session.skip(15)
        elif action == 'stop':
            session.stop()
        else:
            return False
        return True

    def enforce(self):
        if not self.allowed():
            self.clear()
            gate = self.gate()
            inactive = getattr(getattr(self.app, 'screen_privacy', None), 'inactive', False)
            if not getattr(self.app, 'active_host', True) or not self.valid() or (gate is not None and (gate.locked or inactive)):
                self.panel.session.stop()

    def clear(self):
        if self.media is not None:
            self.media.close()
            self.media = None

    def dispose(self):
        global _active
        self.clear()
        if _active is self:
            _active = None
        self.closed = True
        _owners.discard(self)
        self.gate = self.valid = lambda: None


def enforce_privacy(app):
    for owner in tuple(_owners):
        if owner.app is app:
            owner.enforce()


def current_panel(app):
    return _active.panel if _active is not None and _active.app is app and _active.active() else None


def settings_changed(app):
    for owner in tuple(_owners):
        if owner.app.preferences.path == app.preferences.path:
            if owner.app is not app:
                owner.app.preferences.reload()
            owner.enforce()
            owner.changed(owner.panel.session.state)


def stop_media(app):
    for owner in tuple(_owners):
        if owner.app is app:
            owner.panel.session.stop()
            owner.clear()


def native_media(loop, command):
    from toga.platform import get_factory
    backend = get_factory().WebView.__module__
    if backend.startswith('toga_iOS.'):
        from .media_ios import AppleMedia
        kind = AppleMedia
    elif backend.startswith('toga_android.'):
        from .media_android import AndroidMedia
        kind = AndroidMedia
    else:
        raise RuntimeError('System media controls require iOS or Android.')
    adapter = kind.__new__(kind)
    try:
        kind.__init__(adapter, loop, command)
        return adapter
    except Exception:
        try:
            adapter.close()
        except Exception:
            pass
        raise
