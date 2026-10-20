"""Feature-owned floating speech controls; private text never enters a route cache."""
import asyncio
import math
import textwrap
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from .speech import PlaybackTimer, SpeechSession
from .speech_native import NativeSpeech


class ReadAloudPanel(toga.Box):
    def __init__(self, *, loop, source, on_range, close, engine=None, app=None, privacy_gate=lambda: None, valid=lambda: True,
                 document_title=lambda: ''):
        from logisticsmobile.control_icons import icon_button
        self.playback = None
        self.source, self.closed = source, False
        self.document_title = document_title
        self.engine = engine or NativeSpeech(loop)
        self.status = toga.Label('Starting system speech engine…', style=Pack(height=20, font_size=12, margin_top=8))
        self.speech_app = app
        self.voice = ''
        self.overlay = None
        self.speed_choice = toga.Slider(min=.5, max=2, tick_count=7, value=1,
            style=Pack(height=32, flex=1))
        self.speed_value = toga.Label('100%', style=Pack(font_size=14, font_weight='bold', text_align='right'))
        from logisticsmobile.appearance import surface, accessible_name
        accessible_name(self.speed_choice, 'Reading speed')
        def muted(text, font_size=11, **style):
            return surface(toga.Label(text, style=Pack(font_size=font_size, **style)),
                           background='transparent', foreground='muted', radius=0)
        self.speed_minimum, self.speed_maximum = muted('50%'), muted('200%')
        ticks = toga.Box(style=Pack(direction=ROW, margin_left=14, margin_right=14, height=12))
        for index in range(7):
            if index:
                ticks.add(toga.Box(style=Pack(flex=1)))
            ticks.add(muted('·', font_size=9, width=3, height=12, text_align='center'))
        self.speed_track = toga.Box(children=[self.speed_choice, ticks], style=Pack(direction=COLUMN, flex=1))
        self.play_button = icon_button('play', 'Play read-aloud', on_press=self.toggle_playback)
        self.play_button.enabled = False
        self.skip_back = icon_button('skip_back', 'Skip back about 15 seconds', on_press=lambda w: self.session.skip(-15))
        self.skip_forward = icon_button('skip_forward', 'Skip forward about 15 seconds', on_press=lambda w: self.session.skip(15))
        self.skip_back.enabled = self.skip_forward.enabled = False
        self.session = SpeechSession(self.engine, on_range=on_range, on_state=self.state)
        self.timer_choice = toga.Selection(items=['Off', '15 min', '30 min', '45 min', '1 hr'],
            value='Off', style=Pack(height=44, flex=1))
        accessible_name(self.timer_choice, 'Sleep timer duration')
        self.timer_remaining = toga.Label('Timer off', style=Pack(height=22, font_size=13, font_weight='bold', margin_top=4))
        self.reset_timer_button = icon_button('reset', 'Reset timer', on_press=self.reset_timer, enabled=False)
        self.reset_timer_button.style.update(width=44, height=44, margin_left=8)
        self.timer = PlaybackTimer(loop, changed=self.show_remaining, expired=self.timer_expired)
        self.playback_controls = toga.Box(children=[self.skip_back, self.play_button, self.skip_forward,
            icon_button('stop', 'Stop read-aloud', on_press=lambda w: self.session.stop())],
            style=Pack(direction=ROW, margin_top=12))
        for control in self.playback_controls.children:
            control.style.flex = 1
            del control.style.width
        super().__init__(children=[
            toga.Box(children=[toga.Label('Speed', style=Pack(font_size=14, flex=1)), self.speed_value],
                     style=Pack(direction=ROW, height=22)),
            toga.Box(children=[self.speed_minimum, self.speed_track, self.speed_maximum],
                     style=Pack(direction=ROW, align_items=CENTER, gap=8, height=44)),
            toga.Box(children=[toga.Label('Sleep timer', style=Pack(font_size=14, flex=1)), self.timer_choice,
                               self.reset_timer_button],
                     style=Pack(direction=ROW, align_items=CENTER, margin_top=8, height=44)),
            self.timer_remaining, self.playback_controls, self.status],
            style=Pack(direction=COLUMN, margin=16))
        self.speed_choice.on_change = self.change_speed
        self.timer_choice.on_change = self.change_timer
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
        self.speed_value.text = f'{self.speed_choice.value * 100:.0f}%'
        self.session.set_speed(float(self.speed_choice.value))

    def change_timer(self, widget=None, **kwargs):
        minutes = {'Off': 0, '15 min': 15, '30 min': 30, '45 min': 45, '1 hr': 60}
        self.timer.select(minutes[self.timer_choice.value] * 60)
        self.reset_timer_button.enabled = bool(self.timer.duration)

    def reset_timer(self, widget=None, **kwargs):
        self.timer.reset()

    def show_remaining(self, remaining):
        minutes, seconds = divmod(math.ceil(remaining), 60)
        self.timer_remaining.text = f'Time remaining: {minutes:02d}:{seconds:02d}' if self.timer.duration else 'Timer off'
        if self.playback is not None:
            self.playback.timer_changed(self.timer_remaining.text if self.timer.duration else '')

    def timer_expired(self):
        self.session.pause()
        self.set_status('Timer finished · Play to start a new timer.')

    @property
    def overlay_height(self):
        # Keep the detached native container in sync with section heights/gaps.
        return 22 + 44 + 8 + 44 + 4 + 22 + 12 + 48 + 8 + self.status.style.height + 32

    def set_status(self, message):
        self.status.text = textwrap.fill(message, 36)
        self.status.style.height = 20 * max(1, len(self.status.text.splitlines()))
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
            self.timer.set_running(state == 'speaking')
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
            self.timer.dispose()
            if self.playback is not None:
                self.playback.dispose()
            self.closed = True
            self.voice = ''
            if self.overlay is not None:
                self.overlay.close()
                self.overlay = None
            self.status.text = ''
            self.source = None
            self.document_title = lambda: ''
