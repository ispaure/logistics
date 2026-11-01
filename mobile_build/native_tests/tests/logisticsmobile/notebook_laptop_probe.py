"""Real WebKit notebook geometry, settings and lower-screen pen mapping."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from unittest.mock import patch

from mobile.app import LogisticsMobile
from . import start_native_check
from .fixtures import capture_window
from .notebook_laptop_checks import LAPTOP_CHECKS


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'notebook-laptop-fixtures'
        super().startup()

    def on_running(self):
        start_native_check(self, self.check)

    async def check(self, app):
        report = dict(success=False, scope='Real WebKit with injected horizontal reserved region')
        output = Path(self.paths.cache) / 'notebook-ui'
        output.mkdir(exist_ok=True)
        try:
            from features.notebooks.mobile.documents import open_notebook
            from mobile.fold_layout import Division, division
            from .web_checks import wait_for_text
            self.set_feature_enabled('notebooks', True, refresh=False)
            assert await open_notebook(self, name='Laptop notebook')
            panel = self.notebook_panel
            await wait_for_text(panel.web, 'Laptop notebook')
            await asyncio.sleep(.5)
            native = panel.web._impl.native
            bounds = native.bounds.size
            report['actual_region'] = repr(division(self, panel.web))
            region = Division(0, float(bounds.height)*.48, float(bounds.width), float(bounds.height)*.04)
            with patch('mobile.fold_layout.division', return_value=region):
                panel.refresh_fold()
                await asyncio.sleep(.4)
                report['layout'] = json.loads(await panel.web.evaluate_javascript(LAPTOP_CHECKS))
                await capture_window(self, output / 'laptop.png')
            with patch('mobile.fold_layout.division', return_value=None):
                panel.refresh_fold()
                await asyncio.sleep(.3)
                assert await panel.web.evaluate_javascript("$('laptopTools').hidden && $('viewport').clientHeight===innerHeight")
                await panel.web.evaluate_javascript("$('brushToggle').click()")
                assert await panel.web.evaluate_javascript("!$('mobileSheet').hidden && $('mobileSheet').contains($('tool'))")
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'notebook-laptop-result.json').write_text(json.dumps(report, indent=2))


def main():
    return Probe('Notebook laptop QA', 'io.github.ispaure.logisticsstorageqa')
