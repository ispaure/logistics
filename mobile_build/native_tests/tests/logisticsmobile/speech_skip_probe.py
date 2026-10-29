"""Silent native WebView regression for replaced speech ranges after skips."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4
import toga
from toga.style import Pack
from features.books.locations import ChapterText, utf16_length
from features.books.mobile.presentation import chapter_view
from features.books.mobile.speech_view import ReadAloudPanel
from mobile.app import LogisticsMobile
from mobile.markdown_speech import MarkdownSpeech
from .speech_controls_probe import SilentEngine
from .fixtures import capture_window


class SpeechSkipProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('speech-skip-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def check(self, panel, web, name, result):
        await panel.ready_task
        await panel.play()
        for paused in (False, True):
            if paused:
                panel.session.pause()
            for direction in (15, -15):
                session = panel.session
                if not paused:
                    length = utf16_length(session.ranges[session.index][0].split()[0])
                    session.progress(session.token, 0, length)
                await asyncio.sleep(.05)
                before = await web.evaluate_javascript("window.previousSpeech=CSS.highlights.get('logistics-speech'); String(previousSpeech && previousSpeech.size)")
                assert before == '1', (name, before)
                token = session.token
                session.skip(direction)
                session.progress(token, 0, 4)  # Late callback from the stopped utterance.
                if not paused:
                    length = utf16_length(session.ranges[session.index][0].split()[0])
                    session.progress(session.token, 0, length)
                await asyncio.sleep(.05)
                state = json.loads(await web.evaluate_javascript('''JSON.stringify({old:previousSpeech.size,
                    ranges:CSS.highlights.get('logistics-speech').size,
                    text:[...CSS.highlights.get('logistics-speech')].map(r=>r.toString()).join(''),
                    selection:String(getSelection())})'''))
                assert state['old'] == 0 and state['ranges'] == 1 and state['text'], (name, state)
                assert not state['selection'], (name, state)
                result.append(dict(reader=name, paused=paused, direction=direction, **state))
                await capture_window(self, self.probe_output / f'{name}-{paused}-{direction}.png')
        panel.dispose()

    async def probe(self):
        result = dict(success=False, silent_fixture_engine=True, samples=[])
        self.probe_output = Path(self.paths.cache) / 'speech-skip-pixels'
        self.probe_output.mkdir(exist_ok=True)
        try:
            await asyncio.sleep(1)
            text = ' '.join(f'word{i}😀' for i in range(200))
            html = '<html><head></head><body><p>' + text + '</p></body></html>'
            chapter = ChapterText(html)
            web = chapter_view(html)
            box = toga.Box(children=[web], style=Pack(direction='column', flex=1))
            self.show_view(box, destination='home', route='speech-skip', title='Speech skip fixture')
            await asyncio.sleep(.5)
            async def source():
                return chapter, 0, None
            panel = ReadAloudPanel(loop=self.loop, source=source, on_range=web._chapter_bridge.highlight,
                close=lambda: None, engine=SilentEngine())
            await self.check(panel, web, 'EPUB', result['samples'])
            self.show_documents()
            self.editor.value = text
            self.show_preview()
            await asyncio.sleep(.5)
            owner = self.editor_view.markdown_speech
            panel = ReadAloudPanel(loop=self.loop, source=owner.source, on_range=owner.highlight,
                close=lambda: None, engine=SilentEngine())
            await self.check(panel, owner.web, 'Markdown', result['samples'])
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'speech-skip-result.json').write_text(json.dumps(result, indent=2))
        print('SPEECH_SKIP_RESULT=' + json.dumps(result), flush=True)


def main():
    return SpeechSkipProbe('Speech Skip Preview', 'io.github.ispaure.logisticsspeechskip')
