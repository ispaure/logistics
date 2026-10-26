"""Run document acceptance with an existing notebook in a disposable QA app."""
import asyncio
import json
from pathlib import Path
import traceback

from .notebook_probe import NotebookProbe
from .notebook_checks import exercise_notebooks
from .document_checks import exercise_documents


class DocumentWorkspaceProbe(NotebookProbe):
    result_name = 'document-workspace-result.json'

    def startup(self):
        from .navigation_trace import install
        install()
        super().startup()

    async def run_checks(self, app, report):
        await exercise_notebooks(app)
        report['cases'].append('native_notebooks')
        await exercise_documents(app, report['cases'])

    async def check(self, app):
        report = dict(success=False, cases=[])
        try:
            for _ in range(400):
                if not getattr(self, '_startup_in_progress', False):
                    break
                await asyncio.sleep(.1)
            assert not self._startup_in_progress, 'Native startup did not finish'
            background = getattr(self, 'cloud_startup_task', None)
            if background is not None:
                await background
            self.show_cloud(present=False)
            restoring = getattr(self, 'cloud_restore_task', None)
            if restoring is not None:
                await restoring
            await self.run_checks(app, report)
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / self.result_name).write_text(json.dumps(report, indent=2))


def main():
    return DocumentWorkspaceProbe('Document workspace QA', 'io.github.ispaure.logisticsnotebookqa')
