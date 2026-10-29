"""Focused native startup/composition evidence using an isolated QA app."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.SMOKE
import asyncio
import json
from pathlib import Path
import traceback
from mobile.app import LogisticsMobile


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'refactor-startup-fixture'
        super().startup()

    def on_running(self):
        if not getattr(self, '_refactor_probe_started', False):
            self._refactor_probe_started = True
            self.loop.create_task(self.check())

    async def check(self):
        result = dict(success=False, backend=type(self._impl).__module__)
        try:
            assert not self._startup_in_progress
            assert self.active_host
            assert self.main_window.content is not None
            self.show_home()
            await asyncio.sleep(.3)
            first = self.folder_controller()
            assert first is self.folder_controller()
            assert first.app is self
            assert self.rclone_ui.settings.group is not None
            result.update(success=True, startup=True, lazy_owner_identity=True,
                          grouped_connection_services=True)
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'refactor-startup-result.json').write_text(json.dumps(result))


def main():
    return Probe('Refactor startup QA', 'io.github.ispaure.logisticsrefactorqa')
