"""Feature-owned inline speech controls; private text never enters a route cache."""
import asyncio
import textwrap
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .speech import SpeechSession
from .speech_native import NativeSpeech


class ReadAloudPanel(toga.Box):
    def __init__(self, *, loop, source, on_range, close, engine=None):
        self.source, self.closed = source, False
        self.engine = engine or NativeSpeech(loop)
        self.status = toga.Label('Starting system speech engine…')
        self.voice_choice = toga.Selection(items=[], style=Pack(height=44, width=250))
        self.speed_choice = toga.Selection(items=['0.5', '0.75', '1', '1.25', '1.5', '2'], value='1', style=Pack(height=44, width=80))
        self.play_button = toga.Button('Play', on_press=self.play, enabled=False, style=Pack(height=44, flex=1))
        self.pause_button = toga.Button('Pause', on_press=self.pause, enabled=False, style=Pack(height=44, flex=1))
        self.session = SpeechSession(self.engine, on_range=on_range, on_state=self.state)
        super().__init__(children=[self.status,
            toga.Box(children=[self.voice_choice, self.speed_choice], style=Pack(direction=ROW)),
            toga.Box(children=[self.play_button, self.pause_button,
                toga.Button('Stop', on_press=lambda w: self.session.stop(), style=Pack(height=44, flex=1)),
                toga.Button('Close', on_press=close, style=Pack(height=44, flex=1))], style=Pack(direction=ROW))],
            style=Pack(direction=COLUMN))
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
            self.status.text = textwrap.fill(message, 30)
            self.pause_button.enabled = state in ('speaking', 'paused')
            self.pause_button.text = 'Resume' if state == 'paused' else 'Pause'

    async def play(self, widget=None, **kwargs):
        if self.closed:
            return
        chapter, start, end = await self.source()
        if not self.closed:
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
            self.closed = True
            self.voice_choice.items = []
            self.status.text = ''
            self.source = None
