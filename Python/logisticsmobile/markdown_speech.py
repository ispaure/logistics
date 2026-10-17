"""Session-owned offline speech for rendered Markdown; no plaintext cache."""
import json
from types import SimpleNamespace
from weakref import WeakSet

import toga
from toga.style import Pack

from features.books.mobile.speech_view import ReadAloudPanel


class MarkdownSpeechPanel(ReadAloudPanel):
    def state(self, state, message):
        if state == 'speaking':
            message = 'Reading Markdown aloud'
        elif message.startswith('Finished'):
            message = 'Finished reading Markdown.'
        super().state(state, message)


class MarkdownSpeech:
    def __init__(self, app, web, container, *, privacy_gate=lambda: None, valid=lambda: True):
        self.app, self.web, self.container = app, web, container
        self.privacy_gate, self.valid = privacy_gate, valid
        self.panel = None
        self.generation = 0
        self.button = toga.Button('Read aloud', on_press=self.show, style=Pack(height=48))
        if not hasattr(app, '_markdown_speech'):
            app._markdown_speech = WeakSet()
        app._markdown_speech.add(self)

    def show(self, widget=None, **kwargs):
        stop_markdown_speech(self.app)
        self.panel = MarkdownSpeechPanel(loop=self.app.loop, source=self.source,
            on_range=lambda start, end: None, close=self.close, app=self.app, privacy_gate=self.privacy_gate, valid=self.valid)
        self.container.insert(0, self.panel)

    async def source(self):
        generation = self.generation
        # Read rendered text, including tables and code, rather than Markdown
        # punctuation or image data. Native selection wins when it is nonempty.
        value = await self.web.evaluate_javascript('JSON.stringify(String(window.getSelection()).trim() || document.body.innerText)')
        text = json.loads(value) if isinstance(value, str) else ''
        if generation != self.generation or not isinstance(text, str):
            text = ''
        return SimpleNamespace(text=text), 0, None

    def close(self, widget=None, **kwargs):
        self.generation += 1
        if self.panel is not None:
            self.panel.dispose()
            if self.panel in self.container.children:
                self.container.remove(self.panel)
            self.panel = None


def stop_markdown_speech(app, *, keep=None):
    for speech in tuple(getattr(app, '_markdown_speech', ())):
        if speech.panel is not keep:
            speech.close()
