"""Actual WebView input bridge, native ink encoding and on-device recovery."""

from commonUtils.testing.stages import TestStage
from commonUtils.runtime.diagnostics import Severity, log

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from .web_checks import wait_for_text


def verify_native_pencil_binding(app, panel, state):
    """The ordinary release gate must not silently accept iOS DOM fallback."""
    from commonUtils.ui.native.text_size import native_backend
    if not native_backend(app).startswith('toga_iOS.'):
        return
    from rubicon.objc import ObjCClass
    from toga_iOS.window import MainWindow
    from commonUtils.ui.native.keyboard import native_value
    assert isinstance(app.main_window._impl, MainWindow), 'Expected the pinned iOS window backend (including SceneBackend)'
    window = app.main_window._impl.native
    assert window.isKindOfClass(ObjCClass('LogisticsNotebookInputWindow')), 'Compiled native Pencil window is unavailable'
    assert native_value(panel.web._impl.native.window) == window, 'Notebook WK view is not attached to its owning window'
    feed = getattr(panel, 'pen_input', None)
    assert feed is not None and feed.enabled is True, 'Compiled native Pencil binding is unavailable'
    nonce = state.get('native_nonce')
    assert isinstance(nonce, str) and len(nonce) == 32 and all(c in '0123456789abcdef' for c in nonce), 'Missing native canvas lifetime'
    assert state.get('native_pen') is True and nonce == feed.view_id == state.get('input_view'), 'Native feed and canvas nonce disagree'


async def reopen_renamed_notebook(app, resource):
    """Check the native reader and prompts after a file-backed Recents rename."""
    from threading import Event
    from unittest.mock import AsyncMock, patch
    from mobile.document_mutations import prepare_document_mutation
    from mobile.file_operations import FileOperationRequest, retiring_work

    name = 'Renamed Notebook QA.rmdoc'
    request = FileOperationRequest('rename', resource.provider, resource.path, name)
    plan = await prepare_document_mutation(app, request)
    try:
        await retiring_work(plan.execute, Event(), completed=plan.apply)
    finally:
        plan.release()
    matches = [(session, summary) for session, summary in app.recent_items() if summary[0] == name]
    assert len(matches) == 1 and not any(summary[0] == 'Notebook QA.rmdoc' for _, summary in app.recent_items())
    session, _ = matches[0]
    await app.recent_opener(session)()
    panel = app.notebook_panel
    assert panel.document.resource.path == name
    await wait_for_text(panel.web, 'Native notebook')
    await panel.perform({'op': 'rename', 'name': 'Unsaved native title'})
    assert panel.document.dirty
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value='cancel')) as dialog:
        app.request_reader_close(panel.session.id)
        pending = getattr(panel, '_native_close_task', None)
        if pending is not None:
            await asyncio.wait_for(pending, 10)
        pending = app.__dict__.get('_document_close_tasks', {}).get(panel.session.id)
        if pending is not None:
            await asyncio.wait_for(pending, 10)
        dialog.assert_awaited_once()
        assert 'Save changes' in dialog.call_args.args[0].title
    assert not panel.closed and panel.document.dirty
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value='cancel')) as dialog:
        assert not await panel.delete_document()
        assert dialog.call_args.args[0].title == f'Delete {name}?'
    await panel.perform({'op': 'save'})
    assert not panel.document.dirty
    return panel


async def exercise_notebooks(app, *, return_to_home=True):
    from features.notebooks.mobile.documents import open_notebook
    from mobile.navigation import DESTINATIONS
    assert 'notebooks' not in DESTINATIONS
    app.set_feature_enabled('notebooks', True, refresh=False)
    app.show_home()
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:create')
    from .fixtures import choose_creation_type
    await choose_creation_type(app, 'rmdoc')
    form = app.editor_picker()
    form.save_as_name.value = 'Notebook QA'
    form.creation_type.value = 'Remarkable Document (.rmdoc)'
    await form.choose_creation_location()
    picker = app.editor_picker()
    # Native Selection change callbacks can start another directory read after
    # the push; wait for actual readiness rather than a fixed animation delay.
    for _ in range(200):
        if picker.editor_picker_location == ('All files', '') and not picker.cloud_busy:
            break
        await asyncio.sleep(.1)
    assert picker.editor_picker_location == ('All files', ''), (picker.editor_picker_location, picker.save_as_status.value)
    row = next(row for row in picker.editor_picker_rows.values() if row['name'] == 'Local')
    assert await picker.browser_editor_folder(row), picker.save_as_status.value
    assert picker.effective_name.text == 'Save as: Notebook QA.rmdoc'
    await picker.confirm_editor_file()
    assert hasattr(app, 'notebook_panel'), (picker.save_as_status.value, picker.save_as_name.value, picker.source_filename, form.save_as_status.value)
    panel = app.notebook_panel
    assert panel.session.provider == 'notebook', picker.save_as_status.value
    assert panel.session.id in app.workspace.sessions
    assert app.native_host.state.destination == 'home'
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:initial-web-ready')
    await wait_for_text(panel.web, 'Notebook')
    result = await panel.web.evaluate_javascript("JSON.stringify({canvas:!!document.getElementById('paper'),pen:typeof PointerEvent,tools:document.getElementById('tool').options.length,native_pen:state.native_pen,native_nonce:state.native_pen_nonce,input_view:window.logisticsInputTrace?.().view_id})")
    properties = json.loads(result)
    assert properties['canvas'] and properties['pen'] == 'function' and properties['tools'] == len(panel.editor.state()['tools'])
    verify_native_pencil_binding(app, panel, properties)
    retired = panel.web
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:reload')
    assert await panel.load(lambda: panel.repository.open(panel.key), panel.key)
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:initial-web-ready')
    await wait_for_text(panel.web, 'Notebook')
    verify_native_pencil_binding(app, panel, json.loads(await panel.web.evaluate_javascript(
        'JSON.stringify({native_pen:state.native_pen,native_nonce:state.native_pen_nonce,input_view:window.logisticsInputTrace?.().view_id})')))
    assert retired.on_navigation_starting._raw is None
    panel.navigate(retired, panel.bridge.url + '?command=ignored')
    assert panel.bridge.sequence == 0
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:oversized-command')
    status = await panel.web.evaluate_javascript("send({op:'stroke',points:[],padding:'x'.repeat(8*1024*1024)});document.getElementById('status').textContent")
    assert 'too large' in status
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:mobile-controls')
    await panel.web.evaluate_javascript("document.querySelector('#mobileNotice button').click()")
    tools = getattr(panel, 'native_drawing_tools', None)
    # A compact iOS row leases the original DOM controls. On other allocations
    # the WebView itself still owns their geometry.
    async def native_drawing_row():
        return await panel.web.evaluate_javascript(
            "document.body.classList.contains('native-drawing-tools')")
    native_tools = await native_drawing_row()
    title_controls = getattr(panel.view, '_document_title_controls', ())
    if tools is not None and not title_controls and getattr(panel.view, '_reader_top_band_state', None) is None:
        controller = app.native_host.adapter.content_controller(app.native_host.state.destination)
        if tools.fits(controller):
            for _ in range(15):
                if native_tools:
                    break
                await asyncio.sleep(.1)
                native_tools = await native_drawing_row()
            if not native_tools:
                from features.notebooks.mobile.panel import _bounded_input_result
                try:
                    dom = await _bounded_input_result(panel.web.evaluate_javascript(
                        "JSON.stringify({lease:document.body.classList.contains('native-drawing-tools'),"
                        "hidden:document.body.classList.contains('tools-hidden'),"
                        "hook:typeof window.notebookNativeTools,busy,active:active!==null,queued:queue.length})"), 1)
                except Exception as error:
                    dom = type(error).__name__
                raise AssertionError(('Eligible notebook row did not acquire its DOM lease',
                    dict(canvas_ready=panel._canvas_ready, strip_mounted=tools.strip is not None,
                         current=tools.current(), observer_running=tools.task is not None and not tools.task.done(),
                         pending_queries=len(tools.pending), epoch=tools.epoch,
                         observer_exit=tools.observer_exit, dom=dom)))
    if native_tools:
        assert tools is not None and tools.current()
        frames = [tools.anchor(name) for name in tools.buttons]
        assert len(frames) == 5 and all(width >= 44 and height >= 44 for _, _, width, height in frames)
        assert all(abs(frame[1] - frames[0][1]) <= 1 for frame in frames)
        title_host = tools.header._title_content._impl.native
        strip = tools.strip._impl.native
        assert title_host.frame.origin.x + title_host.frame.size.width <= strip.frame.origin.x + 1
    sizes = json.loads(await panel.web.evaluate_javascript("JSON.stringify({viewport:document.getElementById('viewport').getBoundingClientRect().toJSON(),toolbar:document.querySelector('header').getBoundingClientRect().toJSON(),innerWidth,buttons:[...document.querySelectorAll('.mobile-tools button')].map(b=>({id:b.id,label:b.getAttribute('aria-label'),rect:b.getBoundingClientRect().toJSON()})),body:document.body.clientHeight,page:document.getElementById('viewport').clientHeight,overflow:document.body.scrollWidth>innerWidth,targets:[...document.querySelectorAll('.mobile-tools button')].every(b=>b.getBoundingClientRect().width>=44&&b.getBoundingClientRect().height>=44)})"))
    assert (sizes['viewport']['top'] >= sizes['toolbar']['bottom']
            and abs(sizes['viewport']['bottom'] - sizes['body']) <= 1
            and sizes['page'] >= sizes['body'] - sizes['viewport']['top'] - 1
            and not sizes['overflow'] and (native_tools or sizes['targets'])), sizes
    await panel.web.evaluate_javascript("document.getElementById('brushToggle').click()")
    choices = json.loads(await panel.web.evaluate_javascript("JSON.stringify({open:!document.getElementById('mobileSheet').hidden,brushes:document.querySelectorAll('.brush-card').length,selected_focused:document.activeElement.matches('.brush-card[aria-pressed=true]')})"))
    assert choices == dict(open=True, brushes=properties['tools'], selected_focused=True), choices
    await panel.web.evaluate_javascript("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
    assert await panel.web.evaluate_javascript("document.getElementById('mobileSheet').hidden")
    for _ in range(3):
        # A native resize or toolbar lease update may land between separate
        # WK evaluations. Measure the hide/show effect within one layout turn.
        visibility = json.loads(await panel.web.evaluate_javascript("""(() => {
            const frame = () => $('paper').getBoundingClientRect().toJSON();
            const before = frame();
            window.notebookNativeAction('hide-tools');
            const hidden = document.body.classList.contains('tools-hidden');
            const visibleButtons = [...document.querySelectorAll('button')].filter(button =>
                button.getClientRects().length && getComputedStyle(button).visibility !== 'hidden');
            const hiddenFrame = frame();
            $('restoreTools').click();
            return JSON.stringify({before, hiddenFrame, restoredFrame:frame(), hidden,
                onlyRestore:visibleButtons.length === 1 && visibleButtons[0].id === 'restoreTools',
                restored:!document.body.classList.contains('tools-hidden')});
        })()"""))
        assert visibility['hidden'] and visibility['onlyRestore'] and visibility['restored'], visibility
        assert visibility['before'] == visibility['hiddenFrame'] == visibility['restoredFrame'], visibility
    from .notebook_pointer_checks import exercise_pointer_input
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:pointer-input')
    pointer_report = await exercise_pointer_input(panel)
    app._notebook_pointer_report = pointer_report
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:populated-page-render')
    # Measure work on a populated page: pointer motion must not replay old ink.
    await panel.web.evaluate_javascript(r"""(()=>{
        const saved=state.strokes, capture=canvas.setPointerCapture;
        const tool=$('tool').value;
        const clear=ctx.clearRect.bind(ctx),stroke=ctx.stroke.bind(ctx);
        let clears=0,segments=0;
        window.notebookMoveMetrics=null;window.notebookCancelContext=null;
        const restore=()=>{
            state.strokes=saved;canvas.setPointerCapture=capture;
            ctx.clearRect=clear;ctx.stroke=stroke;
            $('tool').value=tool;$('tool').onchange();draw();
        };
        try {
            $('tool').value='17';$('tool').onchange();
            state.strokes=Array.from({length:2000},(_,id)=>({id,layer:state.layers[0][0],tool:12,color:0,scale:1,points:[[20,20,1,2],[25,25,1,2]]}));
            draw();canvas.setPointerCapture=()=>{};
            ctx.clearRect=(...args)=>{clears++;clear(...args)};
            ctx.stroke=(...args)=>{segments++;stroke(...args)};
            const rect=canvas.getBoundingClientRect();
            const event=i=>({pointerId:91,pointerType:'pen',clientX:rect.left+10+i/4,clientY:rect.top+10+i/4,pressure:.6,preventDefault(){},getCoalescedEvents:()=>[]});
            canvas.onpointerdown(event(0));
            for(let i=1;i<=400;i++)canvas.onpointermove(event(i));
            const moving={clears,segments,samples:points.length};
            requestAnimationFrame(()=>{
                try {
                    const afterFrame=segments;
                    window.notebookCancelContext={resizePending:viewportResizePending,deferredUpdate:!!deferredUpdate};
                    canvas.onpointercancel(event(400));
                    window.notebookMoveMetrics={...moving,afterFrame,batched:frameBatchedInk,
                        cancelled:active===null&&points.length===0,cancelClears:clears};
                } catch(error){window.notebookMoveMetrics={error:String(error)}}
                finally{restore()}
            });
        } catch(error){restore();throw error}
        return true;
    })()""")
    for _ in range(200):
        metrics = json.loads(await panel.web.evaluate_javascript('JSON.stringify(window.notebookMoveMetrics)'))
        if metrics is not None:
            break
        await asyncio.sleep(.05)
    assert metrics is not None and 'error' not in metrics, metrics
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:populated-page-complete')
    expected = dict(clears=0, segments=0 if metrics['batched'] else 400, samples=401,
                    afterFrame=1 if metrics['batched'] else 400, batched=metrics['batched'],
                    cancelled=True, cancelClears=1)
    if metrics != expected:
        context = json.loads(await panel.web.evaluate_javascript('JSON.stringify(window.notebookCancelContext)'))
        raise AssertionError(dict(metrics=metrics, before_cancel=context))
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:durable-stroke')
    await panel.web.evaluate_javascript("send({op:'stroke',points:[[100,100,.2],[120,130,.8]],tool:12,color:6,width:3})")
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:stroke-command-returned')
    for _ in range(100):
        if panel.editor.notebook.page(0).strokes:
            break
        await asyncio.sleep(.1)
    assert len(panel.editor.notebook.page(0).strokes) == 1, 'Native WebView did not deliver editable ink'
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:stroke-received')
    while panel.busy:
        await asyncio.sleep(.1)
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:stroke-saved')
    assert len(panel.repository.open(panel.key).page(0).strokes) == 1
    await panel.web.evaluate_javascript("send({op:'add-page'})")
    for _ in range(100):
        if len(panel.editor.notebook.pages) == 2 and not panel.busy:
            break
        await asyncio.sleep(.1)
    assert len(panel.editor.notebook.pages) == 2
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:page-added')
    await panel.web.evaluate_javascript("send({op:'rename',name:'Native notebook'});document.getElementById('layerName').value='Details';document.getElementById('addLayer').click()")
    for _ in range(100):
        if panel.editor.notebook.name == 'Native notebook' and len(panel.editor.notebook.page(1).layers) == 2 and not panel.busy:
            break
        await asyncio.sleep(.1)
    assert panel.editor.notebook.name == 'Native notebook'
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:renamed')
    assert panel.editor.notebook.page(1).layers[-1][1] == 'Details'
    recovered = panel.repository.open(panel.key)
    assert len(recovered.pages) == 2 and len(recovered.page(0).strokes) == 1
    exported = recovered.to_bytes()
    from features.notebooks.notebook import Notebook
    imported = Notebook.read(exported)
    assert not imported.page(0).warning and imported.page(0).strokes[0].tool == 12
    key, session_id = panel.key, panel.session.id
    log(Severity.INFO, 'Native notebook', 'LOGISTICS_NATIVE_DETAIL=notebook:reopen')
    assert app.close_session(session_id)
    assert session_id not in app.workspace.sessions
    assert panel.web is None
    assert await open_notebook(app, key=key)
    assert len(app.notebook_panel.editor.notebook.pages) == 2
    reopened = app.notebook_panel
    await wait_for_text(reopened.web, 'Native notebook')
    # The corner control follows the shared document-close workflow. Save this
    # synthetic local resource first so closing does not request a user choice.
    await reopened.perform(dict(op='save'))
    resource = reopened.document.resource
    await reopened.web.evaluate_javascript("send({op:'library'})")
    for _ in range(100):
        if reopened.web is None and app.native_host.state.destination == 'home':
            break
        await asyncio.sleep(.1)
    assert reopened.web is None and app.native_host.state.destination == 'home'
    if tools is not None:
        current = await reopen_renamed_notebook(app, resource)
    else:
        assert await open_notebook(app, key=key)
        current = app.notebook_panel
        await wait_for_text(current.web, 'Native notebook')
    state = json.loads(await current.web.evaluate_javascript('JSON.stringify({busy})'))
    assert not state['busy'], 'Reopened canvas was left waiting for acknowledgement'
    if return_to_home:
        app.show_home()
    return pointer_report
