"""Focused cold/warm native destination selection acceptance on owned QA devices."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4
from mobile.app import LogisticsMobile
from . import start_native_check
from .navigation_checks import exercise_first_selection
from .rotation_checks import rotate
from .fixtures import capture_window


class FirstTapProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('first-tap-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def probe(self):
        report = dict(success=False, backend=type(self._impl).__module__, samples=[])
        try:
            await asyncio.sleep(.5)
            for orientation in ('portrait', 'landscape-left', 'portrait'):
                await rotate(self, orientation, settle=.3)
                samples = await exercise_first_selection(self)
                report['samples'].append(dict(orientation=orientation, selections=samples))
            await capture_window(self, Path(self.paths.cache) / 'first-tap-final.png')
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'first-tap-result.json').write_text(json.dumps(report, indent=2))


def main():
    return FirstTapProbe('First selection QA', 'io.github.ispaure.logisticsnotebookqa')
