"""Feature-owned floating speech controls; private text never enters a route cache."""
import asyncio
import textwrap
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .speech import SpeechSession
from .speech_native import NativeSpeech


class ReadAloudPanel(toga.Box):
    def __init__(self, *, loop, source, on_range, close, engine=None, app=None, privacy_gate=lambda: None, valid=lambda: True):
        from logisticsmobile.control_icons import icon_button
        self.playback = None
        self.source, self.closed = source, False
        self.engine = engine or NativeSpeech(loop)
        self.status = toga.Label('Starting system speech engine…', style=Pack(height=24))
        self.speech_app = app
        self.voice = ''
        self.overlay = None
        self.speed_choice = toga.Selection(items=['0.5', '0.75', '1', '1.25', '1.5', '2'], value='1', style=Pack(height=44, width=80))
        self.play_button = icon_button('play', 'Play read-aloud', on_press=self.toggle_playback)
        self.play_button.enabled = False
        self.skip_back = icon_button('skip_back', 'Skip back about 15 seconds', on_press=lambda w: self.session.skip(-15))
        self.skip_forward = icon_button('skip_forward', 'Skip forward about 15 seconds', on_press=lambda w: self.session.skip(15))
        self.skip_back.enabled = self.skip_forward.enabled = False
        self.session = SpeechSession(self.engine, on_range=on_range, on_state=self.state)
        super().__init__(children=[self.status,
            toga.Box(children=[toga.Label('Speed', style=Pack(margin_right=12)), self.speed_choice], style=Pack(direction=ROW)),
            toga.Box(children=[self.skip_back, self.play_button, self.skip_forward,
                icon_button('stop', 'Stop read-aloud', on_press=lambda w: self.session.stop()),
                icon_button('close', 'Hide read-aloud controls', on_press=self.hide)], style=Pack(direction=ROW))],
            style=Pack(direction=COLUMN, margin=12))
        self.speed_choice.on_change = self.change_speed
        if app is not None:
            from .media_controls import SpeechPlayback
            self.playback = SpeechPlayback(self, app, gate=privacy_gate, valid=valid)
            self.session.can_speak = self.playback.can_start
        self.ready_task = loop.create_task(self.wait_ready())

    def show_over(self, owner):
        from logisticsmobile.speech_overlay import SpeechOverlay
        if not self.closed and self.overlay is None:
            self.overlay = SpeechOverlay(self, owner, self.speech_app)

    def hide(self, widget=None, **kwargs):
        if self.overlay is not None:
            self.overlay.close()
            self.overlay = None

    def change_speed(self, widget=None, **kwargs):
        self.session.set_speed(float(self.speed_choice.value))

    @property
    def overlay_height(self):
        # Status, speed picker, playback buttons and the panel's outer margins.
        return self.status.style.height + 44 + 48 + 24

    def set_status(self, message):
        self.status.text = textwrap.fill(message, 36)
        self.status.style.height = 24 * max(1, len(self.status.text.splitlines()))
        if self.overlay is not None:
            self.overlay.reposition()

    async def wait_ready(self):
        for _ in range(150):
            if self.engine.ready or self.engine.error or self.closed:
                break
            await asyncio.sleep(.1)
        if self.closed:
            return
        if self.engine.ready:
            voices = sorted(self.engine.voices)
            saved = self.speech_app.preferences.values.get('speech_voice', '') if self.speech_app is not None else ''
            self.voice = saved if saved in voices else self.engine.default_voice or next((v for v in voices if v.startswith('en-US')), voices[0])
            self.play_button.enabled = True
            self.set_status('Select text, or read from here.')
        else:
            self.set_status(self.engine.error or 'Speech engine did not start.')

    def state(self, state, message):
        if not self.closed:
            if self.playback is not None:
                self.playback.changed(state)
            self.set_status(message)
            from logisticsmobile.control_icons import apply_icon
            self.skip_back.enabled = self.skip_forward.enabled = state in ('speaking', 'paused')
            apply_icon(self.play_button, 'pause' if state == 'speaking' else 'play',
                'Pause read-aloud' if state == 'speaking' else 'Resume read-aloud' if state == 'paused' else 'Play read-aloud')

    async def toggle_playback(self, widget=None, **kwargs):
        if self.closed:
            return
        if self.session.state == 'speaking':
            self.session.pause()
        elif self.session.state == 'paused':
            self.session.resume()
        else:
            await self.play()

    async def play(self, widget=None, **kwargs):
        if self.closed:
            return
        generation = self.session.generation
        try:
            chapter, start, end = await self.source()
        except Exception:
            if not self.closed and generation == self.session.generation:
                self.session.stop()
                self.set_status('Could not read this passage. Try reopening the document.')
            return
        if not self.closed and generation == self.session.generation:
            if self.playback is not None and not self.playback.can_start():
                self.session.stop()
                self.set_status('Unlock the credential session before reading aloud.')
                return
            self.session.play(chapter.text, start, end, voice=self.voice,
                speed=float(self.speed_choice.value), breaks=getattr(chapter, 'breaks', ()))

    def pause(self, widget=None, **kwargs):
        if self.session.state == 'paused':
            self.session.resume()
        else:
            self.session.pause()

    def dispose(self):
        if not self.closed:
            self.ready_task.cancel()
            self.session.dispose()
            if self.playback is not None:
                self.playback.dispose()
            self.closed = True
            self.voice = ''
            if self.overlay is not None:
                self.overlay.close()
                self.overlay = None
            self.status.text = ''
            self.source = None
