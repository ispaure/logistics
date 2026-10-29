"""Synthetic speech regression; run as a separate-bundle native probe entry point.

Requires an installed offline system voice. Never opens user documents or remotes.
The result records synthetic ranges/highlight text, not microphone audio.
"""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

import toga
from toga.style import Pack
from features.books.locations import ChapterText
from features.books.mobile.presentation import chapter_view, speech_source
from features.books.mobile.speech_view import ReadAloudPanel
from mobile.app import LogisticsMobile

BUNDLE = 'io.github.ispaure.logisticsspeechprobe'
HIGHLIGHT = """window.CSS && CSS.highlights && CSS.highlights.get('logistics-speech')
    ? [...CSS.highlights.get('logistics-speech')].map(r=>r.toString()).join('')
    : String(getSelection())"""


class SpeechProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('speech-fixture-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_speech_probe_started', False):
            self._speech_probe_started = True
            self.loop.create_task(self.probe())

    async def exercise(self, panel, web):
        await asyncio.wait_for(panel.ready_task, 20)
        assert panel.engine.ready, panel.engine.error
        ranges, samples, native = [], [], []
        follow, progress = panel.session.on_range, panel.engine.progress

        def record(start, end):
            ranges.append([start, end])
            follow(start, end)

        def word(token, start, end):
            native.append([start, end])
            progress(token, start, end)

        panel.session.on_range, panel.engine.progress = record, word
        panel.play_button.on_press()
        try:
            for _ in range(100):
                await asyncio.sleep(.15)
                if panel.session.state == 'speaking':
                    value = await web.evaluate_javascript(HIGHLIGHT)
                    if value:
                        samples.append(value)
                elif ranges:
                    break
            result = dict(state=panel.session.state, status=panel.status.text,
                ranges=ranges, native_ranges=native, highlights=samples,
                media_error=panel.playback.media_error)
            assert panel.session.state == 'stopped', result
            assert panel.status.text.startswith('Finished'), result
            assert len(native) >= 3 and len(set(samples)) >= 3, result
            assert ranges[-1] == [-1, -1], result
            assert not await web.evaluate_javascript(HIGHLIGHT), 'Highlight survived completion'
            return result
        finally:
            panel.dispose()

    async def probe(self):
        result = {}
        try:
            self.show_documents()
            self.name.value = 'Speech.md'
            self.editor.value = '# Read this title.\n\nOne **small** sentence. Another sentence for word highlighting.'
            self.show_preview()
            await asyncio.sleep(1)
            speech = self.editor_view.markdown_speech
            geometry = 'JSON.stringify({width:innerWidth,height:innerHeight,scroll:document.documentElement.scrollHeight})'
            before = await speech.web.evaluate_javascript(geometry)
            speech.show()
            await asyncio.sleep(.2)
            assert before == await speech.web.evaluate_javascript(geometry), 'Speech changed Markdown layout'
            result['markdown'] = await self.exercise(speech.panel, speech.web)
            speech.close()

            content = ('<html><head></head><body><p>First paragraph with some words.</p>'
                '<p>Another sentence with more words.</p></body></html>')
            chapter = ChapterText(content)
            web = chapter_view(content)
            box = toga.Box(children=[web], style=Pack(direction='column', flex=1))
            self.show_view(box, destination='documents', route='speech-epub-probe', title='Speech EPUB')
            await asyncio.sleep(1)

            async def source():
                return await speech_source(web, chapter, 0)

            panel = ReadAloudPanel(loop=self.loop, source=source,
                on_range=web._chapter_bridge.highlight, close=lambda widget: None, app=self)
            before = await web.evaluate_javascript(geometry)
            panel.show_over(box)
            await asyncio.sleep(.2)
            assert before == await web.evaluate_javascript(geometry), 'Speech changed EPUB layout'
            result['epub'] = await self.exercise(panel, web)
            result['passed'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'speech-probe.json').write_text(json.dumps(result))
        print('SPEECH_PROBE=' + json.dumps(result), flush=True)


def main():
    SpeechProbe('Speech probe', BUNDLE).main_loop()
