"""Focused synthetic notebook checks in an isolated disposable QA application."""
import json
from pathlib import Path
import traceback

from mobile.app import LogisticsMobile
from . import start_native_check
from .notebook_checks import exercise_notebooks


class NotebookProbe(LogisticsMobile):
    def startup(self):
        import mobile.incoming_files
        mobile.incoming_files.native_queues = lambda app: []
        self.storage_root = Path(self.paths.cache) / 'synthetic-notebooks'
        super().startup()

    def on_running(self):
        start_native_check(self, self.check)

    async def check(self, app):
        result = dict(success=False)
        try:
            await exercise_notebooks(app)
            result.update(success=True, rename=True, layers=True, native_ink=True,
                          pages=True, recovery=True, archive_reopen=True)
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'notebook-result.json').write_text(json.dumps(result, indent=2))


def main():
    return NotebookProbe('Notebook QA', 'io.github.ispaure.logisticsnotebookqa')
