"""Actual WebView input bridge, native ink encoding and on-device recovery."""
import asyncio
import json
from .web_checks import wait_for_text


async def exercise_notebooks(app, *, return_to_home=True):
    from features.notebooks.mobile.documents import open_notebook
    from mobile.navigation import DESTINATIONS
    assert 'notebooks' not in DESTINATIONS
    app.set_feature_enabled('notebooks', True, refresh=False)
    app.show_home()
    await app.choose_document_type()
    form = app.editor_picker()
    form.save_as_name.value = 'Notebook QA'
    form.creation_type.value = 'Notebook (.rmdoc)'
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
    await wait_for_text(panel.web, 'Notebook')
    result = await panel.web.evaluate_javascript("JSON.stringify({canvas:!!document.getElementById('paper'),pen:typeof PointerEvent,tools:document.getElementById('tool').options.length})")
    properties = json.loads(result)
    assert properties['canvas'] and properties['pen'] == 'function' and properties['tools'] == len(panel.editor.state()['tools'])
    retired = panel.web
    assert await panel.load(lambda: panel.repository.open(panel.key), panel.key)
    await wait_for_text(panel.web, 'Notebook')
    assert retired.on_navigation_starting._raw is None
    panel.navigate(retired, panel.bridge.url + '?command=ignored')
    assert panel.bridge.sequence == 0
    status = await panel.web.evaluate_javascript("send({op:'stroke',points:[],padding:'x'.repeat(8*1024*1024)});document.getElementById('status').textContent")
    assert 'too large' in status
    await panel.web.evaluate_javascript("document.querySelector('#mobileNotice button').click()")
    sizes = json.loads(await panel.web.evaluate_javascript("JSON.stringify({body:document.body.clientHeight,page:document.getElementById('viewport').clientHeight,overflow:document.body.scrollWidth>innerWidth,targets:[...document.querySelectorAll('.mobile-tools button')].every(b=>b.getBoundingClientRect().width>=44&&b.getBoundingClientRect().height>=44)})"))
    assert sizes['page'] >= sizes['body'] * .95 and not sizes['overflow'] and sizes['targets'], sizes
    await panel.web.evaluate_javascript("document.getElementById('brushToggle').click()")
    choices = json.loads(await panel.web.evaluate_javascript("JSON.stringify({open:!document.getElementById('mobileSheet').hidden,brushes:document.querySelectorAll('.brush-card').length,focus:document.activeElement.getAttribute('aria-label')})"))
    assert choices == dict(open=True, brushes=properties['tools'], focus='Close panel'), choices
    await panel.web.evaluate_javascript("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
    assert await panel.web.evaluate_javascript("document.getElementById('mobileSheet').hidden")
    await panel.web.evaluate_javascript("document.querySelector('header button[aria-label=\"Notebook actions\"]').click();document.getElementById('hideTools').click()")
    assert await panel.web.evaluate_javascript("document.body.classList.contains('tools-hidden') && [...document.querySelectorAll('button')].filter(b=>b.getClientRects().length).length===1")
    await panel.web.evaluate_javascript("document.getElementById('restoreTools').click()")
    assert await panel.web.evaluate_javascript("!document.body.classList.contains('tools-hidden')")
    from .notebook_pointer_checks import exercise_pointer_input
    pointer_report = await exercise_pointer_input(panel)
    app._notebook_pointer_report = pointer_report
    # Measure work on a populated page: pointer motion must not replay old ink.
    metrics = json.loads(await panel.web.evaluate_javascript(r"""(()=>{
        const saved=state.strokes, capture=canvas.setPointerCapture;
        const clear=ctx.clearRect.bind(ctx),stroke=ctx.stroke.bind(ctx);
        let clears=0,segments=0;
        try {
            state.strokes=Array.from({length:2000},(_,id)=>({id,layer:state.layers[0][0],tool:12,color:0,scale:1,points:[[20,20,1,2],[25,25,1,2]]}));
            draw();canvas.setPointerCapture=()=>{};
            ctx.clearRect=(...args)=>{clears++;clear(...args)};
            ctx.stroke=(...args)=>{segments++;stroke(...args)};
            const rect=canvas.getBoundingClientRect();
            const event=i=>({pointerId:91,pointerType:'pen',clientX:rect.left+10+i/4,clientY:rect.top+10+i/4,pressure:.6,preventDefault(){},getCoalescedEvents:()=>[]});
            canvas.onpointerdown(event(0));
            for(let i=1;i<=400;i++)canvas.onpointermove(event(i));
            const moving={clears,segments,samples:points.length};
            canvas.onpointercancel(event(400));
            return JSON.stringify({...moving,cancelled:active===null&&points.length===0,cancelClears:clears});
        } finally {
            state.strokes=saved;canvas.setPointerCapture=capture;
            ctx.clearRect=clear;ctx.stroke=stroke;draw();
        }
    })()"""))
    assert metrics == dict(clears=0, segments=400, samples=401, cancelled=True, cancelClears=1), metrics
    await panel.web.evaluate_javascript("send({op:'stroke',points:[[100,100,.2],[120,130,.8]],tool:12,color:6,width:3})")
    for _ in range(100):
        if panel.editor.notebook.page(0).strokes:
            break
        await asyncio.sleep(.1)
    assert len(panel.editor.notebook.page(0).strokes) == 1, 'Native WebView did not deliver editable ink'
    while panel.busy:
        await asyncio.sleep(.1)
    assert len(panel.repository.open(panel.key).page(0).strokes) == 1
    await panel.web.evaluate_javascript("send({op:'add-page'})")
    for _ in range(100):
        if len(panel.editor.notebook.pages) == 2 and not panel.busy:
            break
        await asyncio.sleep(.1)
    assert len(panel.editor.notebook.pages) == 2
    await panel.web.evaluate_javascript("send({op:'rename',name:'Native notebook'});document.getElementById('layerName').value='Details';document.getElementById('addLayer').click()")
    for _ in range(100):
        if panel.editor.notebook.name == 'Native notebook' and len(panel.editor.notebook.page(1).layers) == 2 and not panel.busy:
            break
        await asyncio.sleep(.1)
    assert panel.editor.notebook.name == 'Native notebook'
    assert panel.editor.notebook.page(1).layers[-1][1] == 'Details'
    recovered = panel.repository.open(panel.key)
    assert len(recovered.pages) == 2 and len(recovered.page(0).strokes) == 1
    exported = recovered.to_bytes()
    from features.notebooks.notebook import Notebook
    imported = Notebook.read(exported)
    assert not imported.page(0).warning and imported.page(0).strokes[0].tool == 12
    key, session_id = panel.key, panel.session.id
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
    await reopened.web.evaluate_javascript("send({op:'library'})")
    for _ in range(100):
        if reopened.web is None and app.native_host.state.destination == 'home':
            break
        await asyncio.sleep(.1)
    assert reopened.web is None and app.native_host.state.destination == 'home'
    assert await open_notebook(app, key=key)
    current = app.notebook_panel
    await wait_for_text(current.web, 'Native notebook')
    state = json.loads(await current.web.evaluate_javascript('JSON.stringify({busy})'))
    assert not state['busy'], 'Reopened canvas was left waiting for acknowledgement'
    if return_to_home:
        app.show_home()
    return pointer_report
