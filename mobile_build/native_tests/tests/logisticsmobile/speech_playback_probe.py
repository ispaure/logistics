"""Require real native read-aloud completion; unavailable engines fail acceptance."""
import asyncio
import json
import linecache
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from commonUtils.ui.native.speech import NativeSpeech
from features.books.mobile.speech_view import ReadAloudPanel
from .links_images_voices_probe import LinksImagesVoicesProbe

TEST_STAGE = TestStage.REGRESSION


class SpeechPlaybackProbe(LinksImagesVoicesProbe):
    async def probe(self):
        self.report = dict(success=False, backend=type(self._impl).__module__, events=[])
        cache = Path(self.paths.cache)
        original = NativeSpeech._apple_resources
        panel = None
        def resources():
            # Trace the production function, rather than maintaining a second
            # implementation whose native call order could differ from the app.
            def trace(frame, event, arg):
                if frame.f_code is original.__code__ and event == 'line':
                    row = dict(at=time.monotonic(), line=frame.f_lineno,
                               source=linecache.getline(frame.f_code.co_filename, frame.f_lineno).strip())
                    with (cache / 'speech-initialization.jsonl').open('a') as stream:
                        stream.write(json.dumps(row) + '\n')
                return trace if frame.f_code is original.__code__ else None
            previous = sys.gettrace()
            sys.settrace(trace)
            try:
                return original()
            finally:
                sys.settrace(previous)
        try:
            if getattr(self, 'startup_task', None) is not None:
                await asyncio.shield(self.startup_task)
            self.record_stage('automatic-voices')
            self.preferences.save(speech_voice='QA removed voice')
            with patch.object(NativeSpeech, '_apple_resources', staticmethod(resources)):
                self.show_settings(rebuild=True)
                self.settings_navigation.choose('Read aloud')
                await asyncio.wait_for(asyncio.shield(self.speech_voice_load_task), 20)
                assert self.speech_voice_choice.value == 'System default'
                async def source():
                    return SimpleNamespace(text='This is actual read aloud playback through the system default voice on a disposable simulator.',
                                           language='en', breaks=()), 0, None
                panel = ReadAloudPanel(loop=self.loop, source=source, on_range=lambda *args: None,
                                       close=lambda: None, app=self, document_title=lambda: 'Synthetic speech QA')
                self.settings_navigation.sections['Read aloud'].add(panel)
                await panel.ready_task
            engine = panel.engine
            self.report.update(installed_voices=len(engine.voices), default_voice=engine.default_voice,
                               engine_error=engine.error)
            assert engine.ready, engine.error or 'Native engine did not become ready'
            assert panel.missing_saved_voice and panel.voice == engine.default_voice
            counts = dict(started=0, progress=0, completed=0, failed=0)
            for name in counts:
                previous = getattr(engine, name)
                def event(*args, name=name, previous=previous):
                    counts[name] += 1
                    self.report['events'].append(dict(kind=name, at=time.monotonic(), args=args))
                    previous(*args)
                setattr(engine, name, event)
            speak = engine.speak
            def submitted(text, voice, speed, token):
                self.report['submitted_voice'] = voice
                return speak(text, voice, speed, token)
            engine.speak = submitted
            self.record_stage('native-playback')
            before = time.monotonic()
            await self.tap(panel.play_button)
            await self.until(lambda: counts['completed'] or counts['failed'],
                             'Native playback did not finish', timeout=40)
            assert not counts['failed'] and counts['started'] and counts['progress'], counts
            assert self.report['submitted_voice'] == engine.default_voice
            self.report.update(callbacks=counts, playback_seconds=time.monotonic()-before,
                               missing_saved_default=True, success=True, stage='complete')
            await self.screenshot('speech-complete')
        except Exception:
            self.report['error'] = traceback.format_exc()
            await self.screenshot('speech-failure')
        finally:
            if panel is not None:
                panel.dispose()
            (cache / 'speech-playback-result.json').write_text(json.dumps(self.report, indent=2))


def main():
    return SpeechPlaybackProbe('Speech Playback QA', 'io.github.ispaure.logisticsnotebookqa')
