"""Focused native Back/close through the shared session transition coordinator."""

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
        self.storage_root = Path(self.paths.cache) / 'session-transition-fixture'
        super().startup()

    def on_running(self):
        if not getattr(self, '_session_probe_started', False):
            self._session_probe_started = True
            self.loop.create_task(self.check())

    async def check(self):
        result = dict(success=False, backend=type(self._impl).__module__)
        try:
            self.new_document(name='Native close.txt', content='Synthetic saved content')
            key = self.editor_view.session.id
            self.show_documents(edit=True)
            await asyncio.sleep(.3)
            assert not self.close_session(key, choice='cancel')
            assert key in self.workspace.sessions
            assert self.routes.back()
            await asyncio.sleep(.3)
            assert key not in self.workspace.sessions
            self.new_document(name='Native save.txt', content='Saved before close')
            key = self.editor_view.session.id
            assert self.close_session(key, choice='save')
            assert key not in self.workspace.sessions
            result.update(success=True, cancel_veto=True, native_back=True, save_then_close=True)
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'refactor-session-result.json').write_text(json.dumps(result))


def main():
    return Probe('Session refactor QA', 'io.github.ispaure.logisticsrefactorqa')
