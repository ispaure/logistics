"""Synthetic native tiles and offline speech lifecycle; never uses personal data."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import traceback
from mobile.app import LogisticsMobile


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'runtime-refactor-fixtures'
        super().startup()

    def on_running(self):
        if not getattr(self, '_runtime_probe_started', False):
            self._runtime_probe_started = True
            self.loop.create_task(self.check())

    async def tiles(self):
        from mobile.browser_ui import FileBrowser
        browser = FileBrowser()
        provider = SimpleNamespace(root=Path('/synthetic'), relative=lambda path: path)
        rows = [dict(path=f'file-{i:05}.txt', name=f'file-{i:05}.txt', directory=False) for i in range(10005)]
        browser.set_entries(provider, '', rows)
        self.show_view(browser.scroll_container(), destination='files', route='runtime-tiles', title='Synthetic tiles')
        browser.show_tiles()
        await asyncio.sleep(1)
        initial = len(browser._tile_cards)
        assert 0 < initial < 150, initial
        browser.show_list()
        await asyncio.sleep(.2)
        browser.set_entries(provider, '', rows[:2])
        browser.show_tiles()
        await asyncio.sleep(.5)
        assert len(browser._tile_cards) <= 2, len(browser._tile_cards)
        await browser.work.close()
        assert not browser.work.tasks
        return dict(initial_cards=initial, replacement_cards=len(browser._tile_cards), retired=True)

    async def speech(self):
        from commonUtils.ui.native.speech import NativeSpeech
        from commonUtils.runtime.speech import SpeechSession
        engine = NativeSpeech(self.loop)
        session = SpeechSession(engine, on_range=lambda *args: None, on_state=lambda *args: None)
        try:
            for _ in range(100):
                if engine.ready or engine.error:
                    break
                await asyncio.sleep(.1)
            if not engine.ready:
                return dict(blocked=engine.error, backend=engine.backend)
            starts = []
            started = engine.started
            def capture(token):
                starts.append(token)
                started(token)
            engine.started = capture
            session.play('Synthetic speech lifecycle. ' * 30, voice=engine.default_voice)
            for _ in range(60):
                if starts:
                    break
                await asyncio.sleep(.1)
            assert starts, 'Native speech never reported starting'
            session.pause()
            assert session.state == 'paused'
            session.resume()
            await asyncio.sleep(.2)
            token = session.token
            session.stop()
            engine.deliver(token)
            await asyncio.sleep(.2)
            assert session.state == 'stopped'
            return dict(started=True, pause_resume=True, stop_rejects_late_completion=True)
        finally:
            session.dispose()

    async def check(self):
        result = dict(success=False, backend=type(self._impl).__module__)
        for name in ('tiles', 'speech'):
            try:
                result[name] = await asyncio.wait_for(getattr(self, name)(), 25)
            except Exception:
                result[name] = dict(error=traceback.format_exc())
        result['success'] = all('error' not in result[name] for name in ('tiles', 'speech'))
        (Path(self.paths.cache) / 'refactor-runtime-result.json').write_text(json.dumps(result))


def main():
    return Probe('Runtime refactor QA', 'io.github.ispaure.logisticsrefactorqa')
