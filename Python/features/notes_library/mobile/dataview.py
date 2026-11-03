"""Mobile adapter for the same disposable JSON/view worker as desktop."""
import asyncio
import json
from ..dataview import ViewFiles, runtime_script, javascript, completed_results
from ..dataview_script import POLL, STOP


async def execute_views(web, library, path, plan, *, valid, marker=None):
    files = ViewFiles(library, path)
    # A delayed load callback for the previous note must not start this run in
    # its document. The marker belongs to the exact new HTML publication.
    while marker is not None and valid():
        actual = await web.evaluate_javascript('document.body?.getAttribute("data-logistics-data-view")')
        if actual == marker:
            break
        await asyncio.sleep(.04)
    if not valid():
        return None
    await web.evaluate_javascript(runtime_script(plan))
    try:
        while valid():
            raw = await web.evaluate_javascript(POLL)
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
                    await web.evaluate_javascript('window.logisticsDataView?.reply(' + javascript(reply) + ')')
            await asyncio.sleep(.04)
    finally:
        if valid():
            await web.evaluate_javascript(STOP)
