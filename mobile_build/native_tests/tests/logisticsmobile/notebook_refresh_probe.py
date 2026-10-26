"""Focused WebView and refresh lifecycle QA; requires the test-only Java driver."""
import asyncio
import json
from pathlib import Path
import traceback

from .notebook_probe import NotebookProbe
from .notebook_checks import exercise_notebooks
from .web_checks import wait_for_text


class NotebookRefreshProbe(NotebookProbe):
    async def check(self, app):
        result = dict(success=False, physical_boox_latency_measured=False)
        checks = None
        try:
            from features.notebooks.mobile.documents import open_notebook
            await open_notebook(app)
            panel = app.notebook_panel
            await panel.new()
            await wait_for_text(panel.web, 'Notebook')
            from java import jclass
            checks = jclass('io.github.ispaure.logistics.notebooks.BooxRefreshChecks')(panel.web._impl.native)
            await asyncio.sleep(.3)
            assert checks.checkAndClose()
            checks = None
            await exercise_notebooks(app)
            result.update(success=True, incremental_canvas=True, refresh_lifecycle=True,
                          recovery=True, archive_reopen=True)
        except Exception:
            result['error'] = traceback.format_exc()
        finally:
            if checks is not None:
                checks.close()
        (Path(self.paths.cache) / 'notebook-result.json').write_text(json.dumps(result, indent=2))


def main():
    return NotebookRefreshProbe('Notebook refresh QA', 'io.github.ispaure.logisticsnotebookqa')
