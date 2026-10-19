"""Cold-start progress evidence from a disposable native app identity."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from logisticsmobile.app import LogisticsMobile
from logisticsmobile.startup import StartupScreen, STEPS
from tests.logisticsmobile.fixtures import capture_window


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('startup-fixture-' + uuid4().hex)
        self.evidence = Path(self.paths.cache) / 'startup-progress-evidence'
        self.evidence.mkdir(exist_ok=True)
        self.stages, self.captures = [], []
        self.original_step = StartupScreen.show_step
        def changed(screen, index, name):
            self.original_step(screen, index, name)
            self.stages.append(dict(index=index, name=name,
                visible=self.main_window.content is screen.view,
                progress=screen.progress.value))
            if index in (0, 3, 6):
                self.captures.append(self.loop.create_task(capture_window(self,
                    self.evidence / f'stage-{index}.png')))
        StartupScreen.show_step = changed
        super().startup()
        assert hasattr(self, 'startup_task')
        assert self.main_window.content is self.startup_screen.view

    async def on_running(self):
        StartupScreen.show_step = self.original_step
        report = dict(success=False, stages=self.stages)
        try:
            await asyncio.gather(*self.captures)
            assert [step['name'] for step in self.stages] == list(STEPS)
            assert all(step['visible'] for step in self.stages)
            assert [step['progress'] for step in self.stages] == list(range(len(STEPS)))
            assert self.startup_screen.progress.value == len(STEPS)
            assert not self._startup_in_progress
            assert self.main_window is self._startup_window
            assert self.main_window.content is self.navigation
            assert self.native_host.state.destination == 'home'
            for destination in ('files', 'documents', 'settings', 'home'):
                assert self.select_destination(destination)
                self.native_host.activate(destination)
                await asyncio.sleep(.1)
            await capture_window(self, self.evidence / 'ready.png')
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (self.evidence / 'result.json').write_text(json.dumps(report, indent=2))
        print('STARTUP_PROGRESS=' + json.dumps(report), flush=True)


def main():
    return Probe('Startup Progress QA', 'io.github.ispaure.logisticsstartupqa')
