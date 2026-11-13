"""One Now Playing owner; private readers never publish titles or passage text."""
from weakref import WeakSet
from services.access_policy import speech_allowed

_owners = WeakSet()
_active = None


class SpeechPlayback:
    def __init__(self, panel, app, *, gate=lambda: None, valid=lambda: True, factory=None, audio_output=None):
        self.panel, self.app, self.gate, self.valid = panel, app, gate, valid
        self.factory = factory or native_media
        self.media, self.closed = None, False
        self.media_error = ""
        self.timer_text = ''
        _owners.add(self)
        self.audio_output = audio_output
        self.scope = audio_output.scope if audio_output is not None else app
        if audio_output is not None:
            audio_output.register(self, self.pause_audio)

    def pause_audio(self):
        if self.panel.session.state in {'speaking', 'paused'}:
            getattr(self.panel, 'pause_playback', self.panel.session.pause)()

    def request_start(self):
        return self.credential_start() and (self.audio_output is None or self.audio_output.request_play())

    def can_start(self):
        return self.credential_start() and (self.audio_output is None or self.audio_output.permitted())

    def allowed(self):
        allows_background = getattr(self.panel, 'allows_background', None)
        if allows_background is not None:
            return (not self.closed and getattr(self.app, 'active_host', True) and self.valid()
                    and allows_background())
        return (not self.closed and getattr(self.app, 'active_host', True) and self.valid() and (self.gate() is None
            or self.app.preferences.values.get('session_speech_when_locked', 'false') == 'true'))

    def active(self):
        return self.allowed() and self.panel.session.state in {'speaking', 'paused'}

    def credential_start(self):
        playback_allowed = getattr(self.panel, 'playback_allowed', None)
        if playback_allowed is not None:
            return not self.closed and getattr(self.app, 'active_host', True) and self.valid() and playback_allowed()
        privacy = getattr(self.app, 'screen_privacy', None)
        if privacy is not None and getattr(privacy, 'sensitive', lambda: False)() and not speech_allowed(
                protected=getattr(privacy, 'sensitive', lambda: False)(),
                inactive=privacy.inactive, captured=getattr(privacy, 'captured', False),
                locked=any(gate.locked for gate in privacy.gates()),
                continue_locked=self.app.preferences.values.get('session_speech_when_locked') == 'true'):
            return False
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
                previous = _active.panel
                getattr(previous, 'stop_playback', previous.session.stop)()
            _active = self
            if self.allowed():
                try:
                    if self.media is None:
                        self.media = self.factory(self.app.loop, self.command)
                    self.media.update_content(self.content())
                    self.media.update(state, timer_text=self.timer_text)
                except Exception as error:
                    self.media_error = str(error)
                    self.clear()
            else:
                self.clear()
        else:
            self.clear()
            if _active is self:
                _active = None

    def content(self):
        # Hosts opt ordinary readers in with a title provider. Private hosts leave
        # it empty; credential-session readers remain generic even with opt-in audio.
        privacy = getattr(self.app, 'screen_privacy', None)
        private = (getattr(self.panel, 'private_metadata', False) or self.gate() is not None
                   or bool(privacy is not None and getattr(privacy, 'sensitive', lambda: False)()))
        title = getattr(self.panel, 'document_title', lambda: '')() if not private else ''
        if not title:
            return 'Read aloud'
        title = ' '.join(str(title).replace('\\', '/').rsplit('/', 1)[-1].split())[:120]
        return title or 'Read aloud'

    def timer_changed(self, text):
        """Refresh existing system controls without activating audio or an owner."""
        if self.closed or text == self.timer_text:
            return
        self.timer_text = text
        if self.media is not None and self.active():
            try:
                self.media.update_timer(text)
            except Exception as error:
                self.media_error = str(error)
                self.clear()

    def command(self, action):
        if not self.active():
            self.enforce()
            return False
        session = self.panel.session
        if action == 'interrupt':
            if self.audio_output is not None:
                self.audio_output.invalidate()
            self.pause_audio()
        elif action == 'play':
            if not self.can_start():
                return False
            self.resume()
        elif action == 'pause':
            self.pause_audio()
        elif action == 'toggle':
            if session.state == 'paused' and not self.can_start():
                return False
            self.resume() if session.state == 'paused' else self.pause_audio()
        elif action == 'back':
            getattr(self.panel, 'skip', session.skip)(-15)
        elif action == 'forward':
            getattr(self.panel, 'skip', session.skip)(15)
        elif action == 'stop':
            getattr(self.panel, 'stop_playback', session.stop)()
        else:
            return False
        return True

    def resume(self):
        resume = getattr(self.panel, 'resume_playback', None)
        if resume is not None:
            resume(explicit=False)
        else:
            self.panel.session.resume()

    def enforce(self):
        enforce = getattr(self.panel, 'enforce_playlist_access', None)
        if enforce is not None:
            enforce()
            if not self.allowed():
                self.clear()
            elif self.media is not None:
                self.media.update_content(self.content())
            return
        if not self.credential_start():
            self.pause_audio()
        if self.media is not None:
            self.media.update_content(self.content())
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
        if self.audio_output is not None:
            self.audio_output.unregister(self)
        _owners.discard(self)
        self.gate = self.valid = lambda: None


def enforce_privacy(app, *, playlists_only=False):
    for owner in tuple(_owners):
        if owner.app is app and (not playlists_only or hasattr(owner.panel, 'enforce_playlist_access')):
            owner.enforce()


def current_panel(app):
    return _active.panel if _active is not None and _active.app is app and _active.active() else None


def settings_changed(app):
    output = getattr(app, 'audio_output', None)
    scope = output.scope if output is not None else app
    for owner in tuple(_owners):
        if owner.scope is scope:
            if owner.app is not app:
                owner.app.preferences.reload()
            owner.enforce()
            owner.changed(owner.panel.session.state)


def stop_media(app):
    for owner in tuple(_owners):
        if owner.app is app:
            getattr(owner.panel, 'stop_playback', owner.panel.session.stop)()
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
