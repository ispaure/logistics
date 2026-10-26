"""Focused synthetic notebook checks in an isolated disposable QA application."""
import asyncio
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
        acceptance = Path(self.paths.cache) / 'notebook-ui' / 'acceptance'
        checkpoint = acceptance / 'checkpoint.json'
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
            from .notebook_acceptance_checks import exercise_storage, exercise_mobile, signature, write_report
            from features.notebooks.recovery import Repository
            if checkpoint.exists():
                result = json.loads(checkpoint.read_text())
                recovered = Repository(acceptance / 'recovery').open(result['storage']['key'])
                assert signature(recovered) == result['storage']['signature']
                from features.notebooks.mobile.documents import open_notebook
                assert await open_notebook(app)
                assert await app.notebook_panel.load(lambda: recovered)
                from .web_checks import wait_for_text
                await wait_for_text(app.notebook_panel.web, 'Synthetic hardware acceptance')
                assert signature(app.notebook_panel.editor.notebook) == result['storage']['signature']
                result['process_restart'] = True
                write_report(Path(self.paths.cache) / 'notebook-result.json', result)
                return
            print('Notebook QA: basic editor and pointer checks', flush=True)
            pointer = await exercise_notebooks(app, return_to_home=False)
            from .notebook_chrome_checks import CHROME_CHECKS
            from .fixtures import capture_window
            from mobile.palette import EINK_CSS
            panel = app.notebook_panel
            print('Notebook QA: native export failure/cancellation and rotation', flush=True)
            result['export_failures'] = await exercise_mobile(panel)
            from .rotation_checks import rotate
            before_rotation = signature(panel.editor.notebook)
            dimensions = []
            for orientation in ('portrait', 'landscape-left', 'portrait'):
                await rotate(app, orientation)
                assert signature(panel.editor.notebook) == before_rotation
                dimensions.append(json.loads(await panel.web.evaluate_javascript('JSON.stringify([innerWidth,innerHeight])')))
            assert dimensions[0][0] < dimensions[0][1] and dimensions[1][0] > dimensions[1][1], dimensions
            result['rotation'] = dimensions
            from .notebook_pointer_checks import exercise_continuous_ink
            print('Notebook QA: ordered handwriting bursts', flush=True)
            result['handwriting_bursts'] = await exercise_continuous_ink(panel)
            if type(panel.web._impl).__module__.startswith('toga_iOS.'):
                assert hasattr(panel.view, '_reader_close_button')
                assert await panel.web.evaluate_javascript("document.querySelector('header button[aria-label=\"Close document\"]').hidden")
                controller = app.native_host.adapter.content_controller(app.native_host.state.destination)
                assert controller.navigationItem.hidesBackButton, 'UIKit still presents a Back arrow'
            chrome = json.loads(await panel.web.evaluate_javascript(CHROME_CHECKS))
            captures = Path(self.paths.cache) / 'notebook-ui'
            captures.mkdir(exist_ok=True)
            await asyncio.sleep(.4)  # Allow the separate WebKit compositor to present the DOM change.
            await capture_window(self, captures / 'top-tools.png')
            await panel.web.evaluate_javascript("document.getElementById('brushToggle').click()")
            await asyncio.sleep(.4)  # Allow the separate WebKit compositor to present the DOM change.
            await capture_window(self, captures / 'brush-palette.png')
            await panel.web.evaluate_javascript("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));var probeContrastStyle=document.createElement('style');probeContrastStyle.id='probeContrast';probeContrastStyle.textContent=" + json.dumps(EINK_CSS) + ";document.head.append(probeContrastStyle)")
            contrast = json.loads(await panel.web.evaluate_javascript(CHROME_CHECKS))
            assert contrast['painted_swatches'] == chrome['painted_swatches']
            await panel.web.evaluate_javascript("document.getElementById('brushToggle').click()")
            await asyncio.sleep(.4)  # Allow the separate WebKit compositor to present the DOM change.
            await capture_window(self, captures / 'brush-palette-eink.png')
            await panel.web.evaluate_javascript("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));document.getElementById('probeContrast').remove();document.querySelector('header button[aria-label=\"Notebook actions\"]').click()")
            await asyncio.sleep(.4)  # Allow the separate WebKit compositor to present the DOM change.
            await capture_window(self, captures / 'notebook-menu.png')
            await panel.web.evaluate_javascript("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
            from .notebook_pointer_checks import exercise_document_actions
            print('Notebook QA: native file actions and cancel-close', flush=True)
            result['document_actions'] = await exercise_document_actions(app)
            print('Notebook QA: long archive, publication faults and checkpoint recovery', flush=True)
            import time
            heartbeat = []
            async def tick():
                while True:
                    heartbeat.append(time.monotonic())
                    await asyncio.sleep(.01)
            timer = asyncio.create_task(tick())
            try:
                result['storage'] = await asyncio.to_thread(exercise_storage, acceptance)
            finally:
                timer.cancel()
                try:
                    await timer
                except asyncio.CancelledError:
                    pass
            assert len(heartbeat) > 3, 'Native event loop did not run during long export'
            result['storage']['ui_heartbeat_ticks'] = len(heartbeat)
            result['storage']['max_heartbeat_gap_seconds'] = max(b-a for a,b in zip(heartbeat, heartbeat[1:]))
            from features.notebooks.mobile.documents import open_notebook
            assert await open_notebook(app)
            recovered = Repository(acceptance / 'recovery').open(result['storage']['key'])
            assert await app.notebook_panel.load(lambda: recovered)
            from .web_checks import wait_for_text
            await wait_for_text(app.notebook_panel.web, 'Synthetic hardware acceptance')
            await app.notebook_panel.perform(dict(op='page', index=35))
            assert app.notebook_panel.editor.index == 35
            result.update(success=True, chrome=chrome, contrast=contrast, rename=True, layers=True, native_ink=True,
                          pages=True, recovery=True, archive_reopen=True, pointer=pointer)
            write_report(checkpoint, result)
        except Exception:
            result['pointer'] = getattr(self, '_notebook_pointer_report', None)
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'notebook-result.json').write_text(json.dumps(result, indent=2))
        if result['success']:
            # Host backgrounds/resumes the real app, then requests a live model
            # comparison before killing and relaunching this isolated process.
            control = acceptance / 'resume'
            for _ in range(600):
                if control.exists():
                    recovered = Repository(acceptance / 'recovery').open(result['storage']['key'])
                    assert signature(recovered) == result['storage']['signature']
                    assert signature(app.notebook_panel.editor.notebook) == result['storage']['signature']
                    result['background_resume'] = True
                    write_report(checkpoint, result)
                    write_report(acceptance / 'resumed.json', dict(success=True))
                    break
                await asyncio.sleep(.1)


def main():
    return NotebookProbe('Notebook QA', 'io.github.ispaure.logisticsnotebookqa')
