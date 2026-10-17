"""Feature-owned inline speech controls; private text never enters a route cache."""
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
        self.status = toga.Label('Starting system speech engine…')
        self.voice_choice = toga.Selection(items=[], style=Pack(height=44, width=250))
        self.speed_choice = toga.Selection(items=['0.5', '0.75', '1', '1.25', '1.5', '2'], value='1', style=Pack(height=44, width=80))
        self.play_button = icon_button('play', 'Play read-aloud', on_press=self.play)
        self.play_button.enabled = False
        self.pause_button = icon_button('pause', 'Pause read-aloud', on_press=self.pause)
        self.pause_button.enabled = False
        self.skip_back = icon_button('skip_back', 'Skip back about 15 seconds', on_press=lambda w: self.session.skip(-15))
        self.skip_forward = icon_button('skip_forward', 'Skip forward about 15 seconds', on_press=lambda w: self.session.skip(15))
        self.skip_back.enabled = self.skip_forward.enabled = False
        self.session = SpeechSession(self.engine, on_range=on_range, on_state=self.state)
        super().__init__(children=[self.status,
            toga.Box(children=[self.voice_choice, self.speed_choice], style=Pack(direction=ROW)),
            toga.Box(children=[self.skip_back, self.play_button, self.pause_button, self.skip_forward,
                icon_button('stop', 'Stop read-aloud', on_press=lambda w: self.session.stop()),
                icon_button('close', 'Close read-aloud', on_press=close)], style=Pack(direction=ROW))],
            style=Pack(direction=COLUMN))
        if app is not None:
            from .media_controls import SpeechPlayback
            self.playback = SpeechPlayback(self, app, gate=privacy_gate, valid=valid)
            self.session.can_speak = self.playback.can_start
        self.ready_task = loop.create_task(self.wait_ready())

    async def wait_ready(self):
        for _ in range(150):
            if self.engine.ready or self.engine.error or self.closed:
                break
            await asyncio.sleep(.1)
        if self.closed:
            return
        if self.engine.ready:
            voices = sorted(self.engine.voices)
            self.voice_choice.items = voices
            picker = getattr(self.voice_choice._impl, 'native_picker', None)
            if picker is not None:
                picker.reloadAllComponents()
            self.voice_choice.value = self.engine.default_voice or next((v for v in voices if v.startswith('en-US')), voices[0])
            self.play_button.enabled = True
            self.status.text = 'Installed offline voice · speed\nSelect text, or read from here.'
        else:
            self.status.text = textwrap.fill(self.engine.error or 'Speech engine did not start.', 30)

    def state(self, state, message):
        if not self.closed:
            if self.playback is not None:
                self.playback.changed(state)
            self.status.text = textwrap.fill(message, 30)
            self.pause_button.enabled = state in ('speaking', 'paused')
            from logisticsmobile.control_icons import apply_icon
            self.skip_back.enabled = self.skip_forward.enabled = state in ('speaking', 'paused')
            apply_icon(self.pause_button, 'play' if state == 'paused' else 'pause',
                'Resume read-aloud' if state == 'paused' else 'Pause read-aloud')

    async def play(self, widget=None, **kwargs):
        if self.closed:
            return
        chapter, start, end = await self.source()
        if not self.closed:
            if self.playback is not None and not self.playback.can_start():
                self.session.stop()
                self.status.text = 'Unlock the credential session before reading aloud.'
                return
            self.session.play(chapter.text, start, end, voice=self.voice_choice.value,
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
            self.voice_choice.items = []
            self.status.text = ''
            self.source = None
