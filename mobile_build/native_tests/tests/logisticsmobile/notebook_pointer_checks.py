"""Synthetic pen/touch arbitration checks executed by the actual browser engine.

These events verify application behavior, not a physical Apple Pencil digitizer.
Capture is stubbed because untrusted PointerEvents cannot acquire native capture.
"""
import json

POINTER_CHECKS = r'''(()=>{
const saved={send,mode,active,points,pan,start,last,selected,pendingInk,inkSettings,
    capture:canvas.setPointerCapture,finger:$('finger').checked,
    x:$('viewport').scrollLeft,y:$('viewport').scrollTop};
const captured=[];let result={};
function require(value,message){if(!value)throw Error(message)}
try{
    send=action=>captured.push(action);mode='ink';active=null;points=[];pan=null;
    selected=new Set();pendingInk=null;canvas.setPointerCapture=()=>{};
    $('finger').checked=false;
    const rect=canvas.getBoundingClientRect();
    const event=(type,id,kind,x,y,pressure)=>new PointerEvent(type,{
        bubbles:true,cancelable:true,pointerId:id,pointerType:kind,
        clientX:rect.left+x,clientY:rect.top+y,pressure,
        buttons:type==='pointerup'?0:1,isPrimary:kind==='pen'});
    canvas.dispatchEvent(event('pointerdown',71,'touch',20,20,.5));
    require(active===null&&pan?.id===71,'Finger should pan with finger drawing off');
    result.finger_pan=true;
    canvas.dispatchEvent(event('pointerdown',72,'pen',30,30,.2));
    require(active===72&&pan===null,'Pen contact must cancel an existing finger pan');
    const x=$('viewport').scrollLeft,y=$('viewport').scrollTop;
    canvas.dispatchEvent(event('pointermove',71,'touch',80,80,.5));
    require($('viewport').scrollLeft===x&&$('viewport').scrollTop===y,
        'Finger/palm motion shifted the document during pen input');
    result.palm_motion_ignored=true;
    let move=event('pointermove',72,'pen',60,60,.8);
    Object.defineProperty(move,'getCoalescedEvents',{value:()=>[
        event('pointermove',72,'pen',45,45,.4)]});
    canvas.dispatchEvent(move);
    canvas.dispatchEvent(event('pointerup',72,'pen',60,60,0));
    require(captured.length===1&&captured[0].op==='stroke','Pen did not complete a stroke');
    const pressures=captured[0].points.map(p=>p[2]);
    require(pressures.some(p=>Math.abs(p-.2)<.001)&&pressures.some(p=>Math.abs(p-.4)<.001)
        &&pressures.some(p=>Math.abs(p-.8)<.001),'Pen/coalesced pressure was not retained');
    result.pen_pressure=pressures;result.coalesced_samples=true;
    canvas.dispatchEvent(event('pointerup',71,'touch',80,80,0));
    require(captured.length===1,'Finger pan created unwanted ink');
    canvas.dispatchEvent(event('pointerdown',73,'pen',30,30,.5));
    canvas.dispatchEvent(event('pointercancel',73,'pen',35,35,0));
    require(active===null&&points.length===0&&captured.length===1,'Cancelled pen stroke was saved');
    result.cancellation=true;
    canvas.dispatchEvent(event('pointerdown',74,'pen',30,30,.5));
    canvas.dispatchEvent(event('lostpointercapture',74,'pen',35,35,0));
    require(active===null&&points.length===0&&captured.length===1,'Lost capture saved an incomplete pen stroke');
    result.capture_loss=true;
    $('finger').checked=true;
    canvas.dispatchEvent(event('pointerdown',75,'touch',30,30,.5));
    canvas.dispatchEvent(event('pointerup',75,'touch',40,40,0));
    require(captured.length===2&&captured[1].op==='stroke','Explicit finger drawing failed');
    result.finger_drawing=true;
    return JSON.stringify(result);
}finally{
    send=saved.send;mode=saved.mode;active=saved.active;points=saved.points;pan=saved.pan;
    start=saved.start;last=saved.last;selected=saved.selected;pendingInk=saved.pendingInk;
    inkSettings=saved.inkSettings;canvas.setPointerCapture=saved.capture;
    $('finger').checked=saved.finger;draw();
    $('viewport').scrollLeft=saved.x;$('viewport').scrollTop=saved.y;
}
})()'''


async def exercise_pointer_input(panel):
    report = json.loads(await panel.web.evaluate_javascript(POINTER_CHECKS))
    report['backend'] = type(panel.web._impl).__module__
    if report['backend'].startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        assert panel.web._impl.native.isKindOfClass_(ObjCClass('WKWebView'))
        report['native_view'] = 'WKWebView'
    return report


async def exercise_continuous_ink(panel):
    """Burst handwriting through the real ordered native bridge, all nine nibs."""
    import asyncio
    import time
    report = []
    async def drained():
        for _ in range(600):
            status = json.loads(await panel.web.evaluate_javascript('JSON.stringify({busy,queued:queue.length,active})'))
            if not status['busy'] and not status['queued'] and not panel.busy:
                return
            await asyncio.sleep(.05)
        raise AssertionError('Notebook drawing queue did not drain: ' + repr(status))
    count = len(panel.editor.notebook.page(panel.editor.index).strokes)
    for tool in panel.editor.state()['tools'].values():
        started = time.monotonic()
        payload = r'''(()=>{
            const capture=canvas.setPointerCapture;canvas.setPointerCapture=()=>{};
            let clears=0;const clear=ctx.clearRect.bind(ctx);ctx.clearRect=(...a)=>{clears++;clear(...a)};
            try{
                $('tool').value=TOOL;$('tool').onchange();mode='ink';
                const r=canvas.getBoundingClientRect();
                for(let n=0;n<12;n++){
                    const event=i=>({pointerId:301+n,pointerType:'pen',clientX:r.left+25+i*2,
                        clientY:r.top+130+n*4+Math.sin(i)*3,pressure:.2+i/40,
                        preventDefault(){},getCoalescedEvents:()=>[]});
                    canvas.onpointerdown(event(0));
                    if(active!==301+n)throw Error('A quick stroke was refused at '+n);
                    for(let i=1;i<=20;i++)canvas.onpointermove(event(i));
                    canvas.onpointerup(event(20));
                }
                return JSON.stringify({queued:queue.length,clears});
            }finally{canvas.setPointerCapture=capture;ctx.clearRect=clear}
        })()'''.replace('TOOL', str(tool))
        burst = json.loads(await panel.web.evaluate_javascript(payload))
        assert burst['queued'] == 12 and burst['clears'] == 0, burst
        await drained()
        count += 12
        ink = panel.editor.notebook.page(panel.editor.index)
        assert len(ink.strokes) == count, (tool, count, len(ink.strokes))
        assert all(s.tool == tool for s in ink.strokes[-12:])
        state = json.loads(await panel.web.evaluate_javascript('JSON.stringify({count:state.strokes.length,busy,active})'))
        assert state == dict(count=count, busy=False, active=None), state
        recovered = panel.repository.open(panel.key).page(panel.editor.index)
        assert len(recovered.strokes) == count
        # The existing buttons must still work after each burst and recovery.
        await panel.web.evaluate_javascript("$('undo').click()")
        await drained()
        assert len(panel.editor.notebook.page(panel.editor.index).strokes) == count-1
        await panel.web.evaluate_javascript("$('redo').click()")
        await drained()
        assert len(panel.editor.notebook.page(panel.editor.index).strokes) == count
        report.append(dict(tool=tool, strokes=12, full_page_clears_during_burst=burst['clears'],
                           seconds=round(time.monotonic()-started,3)))
    return report


async def exercise_document_actions(app):
    """Present native decisions, cancel closing, resume ink, reveal and delete."""
    import asyncio
    from unittest.mock import patch
    from features.notebooks.notebook import Notebook
    from features.notebooks.mobile.documents import open_notebook
    from features.text_editor.mobile.document_dialogs import DocumentDialog
    from .web_checks import wait_for_text

    from services.documents.locations import collection_path
    from uuid import uuid4
    source = collection_path(app.private_root) / ('menu-actions-' + uuid4().hex + '.rmdoc')
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(Notebook.new('Menu actions').to_bytes())
    await asyncio.sleep(.5)
    opened = False
    for _ in range(3):
        if await open_notebook(app, path=source):
            opened = True
            break
        await asyncio.sleep(.5)
    assert opened, (app.active_host, app.checkpoint(), getattr(app.notebook_panel.status, 'text', ''), app.navigation_generation)
    panel = app.notebook_panel
    await wait_for_text(panel.web, 'Menu actions')
    async def idle():
        for _ in range(200):
            status = json.loads(await panel.web.evaluate_javascript('JSON.stringify({busy,queued:queue.length})'))
            if not panel.busy and not status['busy'] and not status['queued']:
                return
            await asyncio.sleep(.05)
        raise AssertionError('Document action blocked the drawing bridge')
    original = DocumentDialog._show
    choices, presented = [], []
    def respond(dialog, window):
        future = original(dialog, window)
        choice = choices.pop(0)
        async def decide():
            await asyncio.sleep(.35)
            native = dialog.native
            assert native is not None
            if type(app._impl).__module__.startswith('toga_iOS.'):
                assert native.presentingViewController is not None
                native.dismissViewControllerAnimated(False, completion=None)
                if not future.done():
                    future.set_result(choice)
            else:
                native.getButton(-2 if choice == 'cancel' else -1).performClick()
            presented.append(choice)
        app.loop.create_task(decide())
        return future
    async def await_choice(count):
        for _ in range(200):
            if len(presented) == count and not app.__dict__.get('_document_close_tasks') and not panel.busy:
                return
            await asyncio.sleep(.05)
        raise AssertionError('Native decision did not complete')
    with patch.object(DocumentDialog, '_show', respond):
        await panel.web.evaluate_javascript("send({op:'rename',name:'Dirty menu actions'})")
        await idle()
        choices.append('cancel')
        if hasattr(panel.view, '_native_reader_buttons'):
            await panel.view._reader_close_button.on_press()
        else:
            await panel.web.evaluate_javascript("document.querySelector('header button[aria-label=\"Close document\"]').click()")
        await await_choice(1)
        await idle()
        assert panel.document.dirty and not panel.closed
        await panel.web.evaluate_javascript("send({op:'stroke',points:[[100,200,.3],[140,230,.7]],tool:17,color:0,width:2})")
        await idle()
        assert len(panel.editor.notebook.page(0).strokes) == 1
        # Both menu paths use their ordinary host workflows.
        await panel.web.evaluate_javascript("document.querySelector('header button[aria-label=\"Notebook actions\"]').click();document.querySelector('[data-file-action=\"show-in-folder\"]').click()")
        await idle()
        assert app.native_host.state.destination == 'files'
        assert source.exists() and not panel.closed
        assert await open_notebook(app, key=panel.key)
        choices.append('cancel')
        await panel.web.evaluate_javascript("send({op:'delete-file'})")
        await await_choice(2)
        await idle()
        assert source.exists() and not panel.closed
        choices.append('delete')
        recovery = panel.repository.root / panel.key
        await panel.web.evaluate_javascript("send({op:'delete-file'})")
        await await_choice(3)
        assert panel.closed and not source.exists() and not recovery.exists()
        # Unsaved drafts expose deletion even though there is no folder source.
        assert await open_notebook(app, name='Draft to delete')
        panel = app.notebook_panel
        await wait_for_text(panel.web, 'Draft to delete')
        options = json.loads(await panel.web.evaluate_javascript('JSON.stringify({can_delete:state.can_delete,has_source:state.has_source})'))
        assert options == dict(can_delete=True, has_source=False), options
        recovery = panel.repository.root / panel.key
        choices.append('delete')
        await panel.web.evaluate_javascript("send({op:'delete-file'})")
        await await_choice(4)
        assert panel.closed and not recovery.exists()
    return dict(close_cancel_resumes_ink=True, show_in_folder=True, delete_cancel=True,
                saved_file_deleted=True, unsaved_draft_deleted=True, native_decisions=presented)
