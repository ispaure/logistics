"""Mobile adapter for the same disposable JSON/view worker as desktop."""
import asyncio
import json

from commonUtils.runtime.operations import OperationCancelled

from ..dataview import ViewFiles, runtime_script, javascript, completed_results
from ..dataview_script import POLL, STOP


def _view_document(marker):
    return ('document.body?.hasAttribute("data-logistics-data-view") && '
            'Array.from(document.childNodes).some(node => node.nodeType === 8 && node.data === '
            + javascript('logistics-note:' + marker) + ')')


def _document_script(marker, script):
    # JavaScript evaluation can outlive the Python check or cancellation.
    return f'if ({_view_document(marker)}) {{ {script} }}'


async def execute_views(web, library, path, plan, *, valid, marker=None):
    files = ViewFiles(library, path)

    async def evaluate(script):
        return await web.evaluate_javascript(script if marker is None else _document_script(marker, script))

    if marker is not None:
        while valid() and not await web.evaluate_javascript(_view_document(marker)):
            await asyncio.sleep(.04)
    if not valid():
        return None
    await evaluate(runtime_script(plan))
    try:
        while valid():
            raw = await evaluate(POLL)
            if not valid():
                return None
            if raw:
                state = json.loads(raw)
                if state['done']:
                    return plan.render(completed_results(state, len(plan.scripts)))
                for message in state['requests']:
                    reply = await asyncio.to_thread(files.request, message, cancelled=lambda: not valid())
                    if not valid():
                        return None
                    await evaluate('window.logisticsDataView?.reply(' + javascript(reply) + ')')
            await asyncio.sleep(.04)
    finally:
        if valid():
            await evaluate(STOP)


class PageDataViews:
    """Own a page's view plan and the job for its original HTML."""

    def __init__(self, web, library, plan):
        self.web, self.library = web, library
        self.plan = plan
        self.loading = plan is not None
        self.task = None
        self._running_marker = None
        self._closed = False

    def start(self, loop, render):
        if self.plan is not None and not self._closed:
            plan, self.plan = self.plan, None
            self.task = loop.create_task(render(plan))

    def close(self):
        self._closed = True
        self.plan = None
        self.loading = False
        if self.task is not None:
            self.task.cancel()
            self.task = None
        if self._running_marker is not None:
            self.web.evaluate_javascript(_document_script(self._running_marker, STOP))

    async def render(self, plan, path, marker, *, current, preview, remember_position, publish, show_error):
        def valid():
            return not self._closed and current()

        if not valid() or self._running_marker is not None:
            return
        self._running_marker = marker
        try:
            text = await asyncio.wait_for(execute_views(self.web, self.library, path, plan,
                                                       valid=valid, marker=marker), timeout=35)
            if text is None or not valid():
                return
            html, videos = await asyncio.to_thread(preview, text, cancelled=lambda: not valid())
            if not valid():
                return
            await remember_position()
            if valid():
                self.loading = False
                publish(html, videos)
        except OperationCancelled:
            return
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
            if valid():
                self.loading = False
                await show_error('Could not update data view', str(error) or 'Execution exceeded 35 seconds.')
        finally:
            self._running_marker = None
