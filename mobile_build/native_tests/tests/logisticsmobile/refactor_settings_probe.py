"""Native compact/detail settings navigation and connection-form smoke."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from mobile.app import LogisticsMobile


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'settings-refactor-fixture'
        super().startup()

    def on_running(self):
        if not getattr(self, '_settings_probe_started', False):
            self._settings_probe_started = True
            self.loop.create_task(self.check())

    async def check(self):
        result = dict(success=False, backend=type(self._impl).__module__)
        try:
            self.show_settings()
            await asyncio.sleep(.3)
            nav = self.settings_navigation
            assert 'App' in nav.sections and 'About' in nav.sections
            nav.choose('Text')
            await asyncio.sleep(.2)
            assert 'Text' in nav.sections.built
            nav.choose('Workspaces')
            await asyncio.sleep(.2)
            self.show_smb_connection()
            await asyncio.sleep(.3)
            assert self.smb_view is not None
            assert self.smb_host is not None
            result.update(success=True, lazy_text_category=True, workspace_category=True,
                          native_navigation=True, connection_form=True)
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'refactor-settings-result.json').write_text(json.dumps(result))


def main():
    return Probe('Settings refactor QA', 'io.github.ispaure.logisticsrefactorqa')
