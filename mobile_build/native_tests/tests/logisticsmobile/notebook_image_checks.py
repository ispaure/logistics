"""One real WebView workflow shared by native desktop, Android and iOS probes."""
import asyncio
import json
import math

from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION

HELPERS = r'''window.imageQA = {
  captureMode(enabled) {
    if ((mode === 'capture') === enabled) return;
    if (document.body.classList.contains('notebook-mobile')) window.notebookNativeAction('view');
    const button=$('capture');
    if (!button.getClientRects().length) throw Error('Ordinary Capture action is not visible');
    button.click();
    if ((mode === 'capture') !== enabled) throw Error('Ordinary Capture action did not change mode');
  },
  event(p, type='touch') {
    const r=canvas.getBoundingClientRect();
    return {pointerId:731,pointerType:type,nativePen:true,
      clientX:r.left+p[0]/state.width*r.width,clientY:r.top+p[1]/state.height*r.height,
      pressure:.5,preventDefault(){}};
  },
  gesture(path,type='touch',cancel=false) {
    canvas.onpointerdown(this.event(path[0],type));
    for(const p of path.slice(1)) canvas.onpointermove(this.event(p,type));
    canvas[cancel?'onpointercancel':'onpointerup'](this.event(path.at(-1),type));
  },
  current() {return selectedPicture() || state.images.at(-1)},
  center(p=this.current()) {return p.corners.reduce((a,q)=>[a[0]+q[0]/4,a[1]+q[1]/4],[0,0])},
  edge(p=this.current()) {return Math.hypot(p.corners[1][0]-p.corners[0][0],p.corners[1][1]-p.corners[0][1])},
  pixel(p) {return [...ctx.getImageData(Math.floor(p[0]*canvas.width/state.width),Math.floor(p[1]*canvas.height/state.height),1,1).data]},
  snapshot() {return {index:state.index,images:state.images.map(p=>({id:p.id,corners:p.corners})),order:state.scene_order,
    strokes:state.strokes.map(s=>s.id),status:$('status').textContent,locked:state.password_required}},
  captureDiagnostic() {
    const bg=$('pdfBackground'), roi=imageClipboard.sourceCorners;
    const left=Math.min(...roi.map(p=>p[0])), top=Math.min(...roi.map(p=>p[1]));
    const b=state.pdf_paper || {x:0,y:0,width:state.width,height:state.height};
    const fit=Math.min(b.width/bg.naturalWidth,b.height/bg.naturalHeight);
    const w=bg.naturalWidth*fit,h=bg.naturalHeight*fit;
    const box={x:b.x+(b.width-w)/2,y:b.y+(b.height-h)/2,width:w,height:h};
    const point=[left+100*imageClipboard.width/window.qaClip.width,
                 top+150*imageClipboard.height/window.qaClip.height];
    let direct;
    try {
      const c=document.createElement('canvas');c.width=c.height=1;
      const g=c.getContext('2d');g.fillStyle='white';g.fillRect(0,0,1,1);
      g.drawImage(bg,box.x-point[0],box.y-point[1],box.width,box.height);
      direct=[...g.getImageData(0,0,1,1).data];
    } catch(e) { direct={error:e.name}; }
    const decode=window.imageQACaptureDecodeProof={available:typeof bg.decode==='function',requested:false,settled:false,ready:false};
    const snapshot={complete:bg.complete,naturalWidth:bg.naturalWidth,naturalHeight:bg.naturalHeight,
      pdf_paper:state.pdf_paper || null,width:state.width,height:state.height,
      clip_roi:roi,clip_size:[imageClipboard.width,imageClipboard.height],
      background_fit:box,document_sample:point,direct_background_sample:direct,
      sources:{original:window.imageQAOriginalBackground,current:bg.currentSrc||bg.src,clipboard:imageClipboard.src},
      decode_before_diagnostic_request:{...decode},latched_pixels_before_diagnostics:true,
      current_src_empty:!bg.currentSrc,latched_clip:window.qaClip};
    // This is AFTER the failed pixel value was latched. Never retry the capture.
    if(decode.available){decode.requested=true;bg.decode().then(()=>{decode.settled=true;decode.ready=true;},e=>{decode.settled=true;decode.error=e.name;});}
    return snapshot;
  },
  async clipPixels() {
    const img=new Image();img.src=imageClipboard.src;await img.decode();
    const c=document.createElement('canvas');c.width=img.width;c.height=img.height;
    const g=c.getContext('2d');g.drawImage(img,0,0);
    return {width:c.width,height:c.height,pixels:[[100,150],[250,170],[100,70],[390,310]].map(p=>[...g.getImageData(...p,1,1).data])};
  }
};true'''


def write_capture_diagnostic(output, label, snapshot):
    """Retain only this synthetic fixture's bounded data PNGs and scalar metadata."""
    import base64
    from hashlib import sha256
    if label not in ('Local', 'LocalCrypt'):
        raise ValueError('Unknown image QA provider label.')
    metadata = dict(snapshot)
    sources = metadata.pop('sources')
    metadata['source_hashes'] = {}
    for name in ('original', 'current', 'clipboard'):
        source = sources[name]
        if not isinstance(source, str) or len(source) > 24 * 1024 * 1024:
            raise ValueError('Invalid or oversized image QA source.')
        metadata['source_hashes'][name] = dict(src_sha256=sha256(source.encode()).hexdigest(), src_bytes=len(source))
        prefix = 'data:image/png;base64,'
        if not source.startswith(prefix):
            metadata['source_hashes'][name]['png'] = False
            continue
        data = base64.b64decode(source[len(prefix):], validate=True)
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Invalid image QA PNG signature.')
        metadata['source_hashes'][name].update(png=True, png_sha256=sha256(data).hexdigest())
        (output / (label+'-capture-failure-'+name+'.png')).write_bytes(data)
    (output / (label+'-capture-failure.json')).write_text(json.dumps(metadata, indent=2))


def signature(book):
    from features.notebooks.notebook import Notebook
    book = Notebook.read(book.to_bytes())
    return [dict(images=[p.payload() for p in book.page(i).images],
                 strokes=[s.payload() for s in book.page(i).strokes], order=book.page(i).order)
            for i in range(len(book.pages))]


class ImageWorkflow:
    def __init__(self, evaluate, editor, capture, progress=None, diagnostic=None):
        self.evaluate, self.editor, self.capture = evaluate, editor, capture
        self.cases = []
        self.progress = progress
        self.diagnostic = diagnostic

    async def js(self, expression):
        # A JSON result has the same shape in Qt, Android WebView and WKWebView.
        encoded = await self.evaluate('JSON.stringify((()=>{' + expression + '})())')
        return json.loads(encoded) if isinstance(encoded, str) else encoded

    async def wait(self, expression, message):
        for _ in range(400):
            snapshot = await self.js('const ready=Boolean(' + expression + r""");
                return {ready,documentReady:document.readyState,
                    hasIdle:typeof window.notebookIdle==='function',
                    busy:typeof busy==='undefined'?null:busy,
                    queued:typeof queue==='undefined'?null:queue.length,
                    active:typeof active==='undefined'?null:active,
                    passwordLocked:typeof state==='undefined'?null:!!state.password_required,
                    imageCount:typeof state==='undefined'?null:state.images?.length};
            """)
            if self.progress is not None:
                self.progress(dict(check=message, attempt=_, **snapshot))
            if snapshot['ready']:
                return
            await asyncio.sleep(.05)
        raise AssertionError(message + ': ' + str(await self.js("return {status:document.getElementById('status')?.textContent,ready:document.readyState,errors:window.imageQAErrors}")))

    async def idle(self):
        await self.wait("typeof window.notebookIdle==='function' && window.notebookIdle()", 'Notebook command queue did not drain')
        await self.wait("!state.images.length || state.images.every(p=>imageCache.get(p.src)?.complete && imageCache.get(p.src)?.naturalWidth)", 'Images did not decode')

    async def action(self, code):
        await self.evaluate('(()=>{' + code + ';return true})()')
        await self.idle()

    async def send(self, action):
        await self.action('send(' + json.dumps(action) + ')')

    async def unlock(self):
        await self.wait("typeof state!=='undefined' && state.password_required && !document.getElementById('pdfUnlock').hidden", 'Password form absent')
        await self.action("$('pdfPassword').value='wrong-password';$('pdfUnlock').requestSubmit()")
        result = await self.js("return {locked:state.password_required,error:$('status').textContent,cleared:$('pdfPassword').value===''}")
        assert result['locked'] and result['cleared'] and 'Incorrect' in result['error'], result
        await self.action("$('pdfPassword').value='image-qa-password';$('pdfUnlock').requestSubmit()")
        await self.wait("!state.password_required && $('pdfBackground').complete && $('pdfBackground').naturalWidth>0", 'Protected PDF did not render')
        self.cases.append('wrong password, retry, cleared password input, native protected-PDF raster')

    async def verify_capture(self, clip):
        red, green, ink, outside = clip['pixels']
        try:
            assert red[0]>180 and red[1]<120 and red[3]==255, clip
            assert green[1]>140 and green[0]<100 and green[3]==255, clip
            assert ink[0]<red[0]-40 and ink[3]==255 and outside[3]==0, clip
        except AssertionError as primary:
            try:
                snapshot = await self.js('return imageQA.captureDiagnostic()')
                await self.capture('capture-failure')
                snapshot['decode_after_capture'] = await self.js('return window.imageQACaptureDecodeProof')
                if self.diagnostic is not None:
                    self.diagnostic(snapshot)
            except BaseException as error:
                primary.add_note('Capture diagnostics failed: ' + type(error).__name__)
            raise

    async def run(self):
        await self.idle()
        await self.evaluate(HELPERS)
        await self.unlock()
        assert len(self.editor().notebook.page(0).images) == 1
        await self.evaluate("(()=>{window.imageQAOriginalBackground=$('pdfBackground').src;const c=document.createElement('canvas');c.width=100;c.height=50;const g=c.getContext('2d');g.fillStyle='#e64c26';g.fillRect(0,0,100,50);$('pdfBackground').src=c.toDataURL();return true})()")
        await self.wait("$('pdfBackground').complete && $('pdfBackground').naturalWidth===100", 'Wide background did not decode')
        await self.action("imageQA.captureMode(true);$('newCutout').click();imageQA.gesture([[100,100],[500,100],[500,350],[350,420],[100,420],[100,100]])")
        await self.evaluate("window.qaClip=null;imageQA.clipPixels().then(p=>window.qaClip=p);true")
        await self.wait('window.qaClip!==null', 'Wide-background capture did not decode')
        letterbox=await self.js('return window.qaClip.pixels[0]')
        assert all(v>245 for v in letterbox[:3]) and letterbox[3]==255, letterbox
        await self.evaluate("$('pdfBackground').src=window.imageQAOriginalBackground;true")
        await self.wait("$('pdfBackground').complete && $('pdfBackground').naturalWidth!==100", 'PDF background restore did not decode')
        self.cases.append('capture preserves displayed background aspect ratio and letterboxing')
        await self.action("imageQA.captureMode(true);$('newCutout').click();imageQA.gesture([[100,100],[500,100],[500,350],[350,420],[100,420],[100,100]])")
        await self.evaluate("window.qaClip=null;imageQA.clipPixels().then(p=>window.qaClip=p);true")
        await self.wait('window.qaClip!==null', 'Clipboard PNG did not decode')
        clip = await self.js('return window.qaClip')
        # Pointer coordinates round through each WebView's viewport scale.
        assert abs(clip['width']-400)<=1 and abs(clip['height']-320)<=1, clip
        await self.verify_capture(clip)
        self.cases.append('lasso PNG includes PDF, ink and image pixels; outside lasso transparent')
        await self.capture('captured')
        await self.action("$('pasteImage').click()")
        assert len(self.editor().notebook.page(0).images) == 2
        await self.action("$('pasteImage').click()")
        assert len(self.editor().notebook.page(0).images) == 3
        ids = [p.id for p in self.editor().notebook.page(0).images]
        assert len(set(ids)) == 3
        self.cases.append('capture clipboard and two independent pasted instances on one page')
        before = await self.js('return imageQA.current().corners')
        await self.action("const p=imageQA.center();imageQA.gesture([p,[p[0]+40,p[1]+35]],'touch')")
        moved = await self.js('return imageQA.current().corners')
        assert all(abs(b[0]-a[0]-40)<.01 and abs(b[1]-a[1]-35)<.01 for a,b in zip(before,moved)), moved
        await self.action("const p=imageQA.center();imageQA.gesture([p,[p[0]+10,p[1]+5]],'pen')")
        self.cases.append('finger and pen selection/movement via actual canvas handlers and durable bridge')
        await self.wait('!penTouchBlocked()', 'Pen release palm-rejection grace did not expire')
        edge = await self.js('return imageQA.edge()')
        await self.action("const p=imageQA.current(),c=imageQA.center(p),h=imageHandles(p)[1],a=Math.PI/6,x=h[0]-c[0],y=h[1]-c[1];imageQA.gesture([h,[c[0]+x*Math.cos(a)-y*Math.sin(a),c[1]+x*Math.sin(a)+y*Math.cos(a)]])")
        rotated = await self.js('return imageQA.current().corners')
        assert abs(rotated[1][1]-rotated[0][1])>20 and math.isclose(await self.js('return imageQA.edge()'),edge,abs_tol=.1), rotated
        await self.action("const p=imageQA.current(),c=imageQA.center(p),h=imageHandles(p)[0];imageQA.gesture([h,[c[0]+(h[0]-c[0])*1.25,c[1]+(h[1]-c[1])*1.25]])")
        assert math.isclose(await self.js('return imageQA.edge()'),edge*1.25,abs_tol=.1)
        await self.action("$('imageRotate').click()")
        await self.action("$('imageSmaller').click()")
        await self.action("$('imageLarger').click()")
        transformed = await self.js('return imageQA.current().corners')
        await self.send(dict(op='undo')); await self.send(dict(op='redo'))
        assert await self.js('return imageQA.current().corners') == transformed
        self.cases.append('rotation and scale handles, rotation/size buttons, undo/redo')
        await self.capture('transformed')
        selected = await self.js('return imageQA.current().id')
        center = await self.js('return imageQA.center()')
        ink = self.editor().notebook.page(0)
        original_strokes = {stroke.id for stroke in ink.strokes}
        picture = next(picture for picture in ink.images if picture.id == selected)
        # Stroke acknowledgements preserve ink already painted by real input.
        # Sending a bare command skips that painting and cannot prove overlap.
        await self.action("imageQA.captureMode(false);$('tool').value='17';$('tool').dispatchEvent(new Event('change'));$('color').value='0';$('color').dispatchEvent(new Event('change'));$('width').value='3';$('width').dispatchEvent(new Event('change'))")
        assert await self.js("return mode==='ink' && $('tool').value==='17' && $('color').value==='0' && $('width').value==='3'")
        await self.action('imageQA.gesture('+json.dumps([[center[0]-30,center[1]],[center[0]+30,center[1]]])+",'pen')")
        added = [stroke for stroke in self.editor().notebook.page(0).strokes
                 if stroke.id not in original_strokes]
        assert len(added) == 1, [stroke.payload() for stroke in added]
        assert (added[0].tool, added[0].color, added[0].layer) == (17, 0, picture.layer), added[0].payload()
        above = await self.js('return imageQA.pixel('+json.dumps(center)+')')
        assert max(above[:3]) < 80 and above[3] == 255, above
        await self.action("imageQA.captureMode(true);imageSelection="+json.dumps(selected)+";imageRender()")
        assert await self.js('return mode==="capture" && selectedPicture()?.id==='+json.dumps(selected))
        for direction in ('back','forward','front','backward','front'):
            await self.action("imageSelection="+json.dumps(selected)+";$('imageArrange').value="+json.dumps(direction)+";$('imageArrange').onchange()")
            ink=self.editor().notebook.page(0)
            index=ink.order.index(selected)
            assert index == (0 if direction=='back' else 1 if direction=='forward' else len(ink.order)-2 if direction=='backward' else len(ink.order)-1), (direction,index,ink.order)
        below = await self.js('return imageQA.pixel(imageQA.center())')
        assert sum(abs(a-b) for a,b in zip(above[:3],below[:3]))>40, (above,below)
        self.cases.append('mixed stroke/image forward/backward/front/back order with overlapping pixel change')
        await self.capture('arranged')
        copied = await self.js('return imageQA.current().corners')
        await self.action("$('zoom').value='1.5';$('zoom').dispatchEvent(new Event('change'));$('viewport').scrollLeft=175;$('viewport').scrollTop=350;$('copyImage').click()")
        await self.send(dict(op='add-page'))
        await self.action("$('zoom').value='fit';$('zoom').dispatchEvent(new Event('change'));$('viewport').scrollLeft=0;$('viewport').scrollTop=0;$('pasteImage').click()")
        await self.action("$('pasteImage').click()")
        assert len(self.editor().notebook.page(1).images)==2
        pasted=await self.js('return imageQA.current().corners')
        assert all(abs(a-b)<.1 for p,q in zip(copied,pasted) for a,b in zip(p,q)), (copied,pasted)
        self.cases.append('cross-page Copy preserves exact page position/rotation/scale across zoom and scroll; repeated paste')
        await self.capture('second-page')
        await self.action("$('zoom').value='1.5';$('zoom').dispatchEvent(new Event('change'));$('viewport').scrollTop=430;$('cutImage').click()")
        assert len(self.editor().notebook.page(1).images)==1
        await self.send(dict(op='page',index=0))
        await self.action("$('zoom').value='fit';$('zoom').dispatchEvent(new Event('change'));$('viewport').scrollTop=0;$('pasteImage').click()")
        cut_pasted=await self.js('return imageQA.current().corners')
        assert all(abs(a-b)<.1 for p,q in zip(copied,cut_pasted) for a,b in zip(p,q)), (copied,cut_pasted)
        assert len(self.editor().notebook.page(0).images)==4
        self.cases.append('cross-page Cut preserves original geometry under different viewport zoom/scroll')
        await self.capture('cut-pasted')
        return self.cases


IMAGE_FIXTURE_SHA256 = '53ea0caccddb485387031ade567c107bd9159fcbe30b3878433305f5dc69ab79'



def verify_native_image_view(panel, provider):
    """Resolve supported native subclasses and retain the actual privacy boundary."""
    from commonUtils.ui.native.text_size import native_backend
    from commonUtils.ui.native.keyboard import native_value
    from commonUtils.ui.native.private_webview import PrivateWebView
    web = panel.web
    backend = native_backend(web)
    assert backend.startswith(('toga_iOS.', 'toga_android.')), backend
    assert not panel.closed and web in panel.view.children and web._impl.interface is web
    resource = panel.document.resource
    assert resource.path == 'images.rmdoc' and not resource.closed
    assert resource.provider.root == provider.root
    assert resource.policy.persistent == (not provider.private)
    if provider.private:
        assert isinstance(web, PrivateWebView) and web.private_configured and not web.private_closed
        assert resource.provider.client is provider.client and resource.provider.remote == provider.remote
        assert resource.provider.identity == provider.identity and not resource.provider.closed
        assert panel.document.recovery is None
    else:
        assert not isinstance(web, PrivateWebView)
    native = web._impl.native
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        assert native.isKindOfClass_(ObjCClass('WKWebView'))
        assert native_value(native.window) is not None and not native.isHidden()
        bounds = native_value(native.bounds)
        assert bounds.size.width > 0 and bounds.size.height > 0
        if provider.private:
            assert not bool(native.configuration.websiteDataStore.isPersistent())
    else:
        from android.webkit import WebView as NativeWebView, WebSettings
        assert isinstance(native, NativeWebView)
        assert native.isAttachedToWindow() and native.isShown()
        assert native.getWidth() > 0 and native.getHeight() > 0
        if provider.private:
            settings = native.getSettings()
            assert settings.getCacheMode() == WebSettings.LOAD_NO_CACHE
            assert not settings.getDomStorageEnabled() and not settings.getAllowFileAccess()
            assert not settings.getAllowContentAccess()
    return backend


def _cleanup_image_run(app, run):
    """Synchronous teardown also runs during timeout/cancellation; never own credentials."""
    from services.documents.mobile_notebooks import close_notebook, panels
    from commonUtils.persistence import atomic_write_json
    cleanup=run['report']['cleanup']
    errors=cleanup['errors']
    def attempt(label, action):
        try:
            action()
        except BaseException as error:
            errors.append(label+': '+type(error).__name__+': '+str(error))
    def owned(panel):
        if panel is None or id(panel) in run['original_panels']:
            return False
        if id(panel) in run['panels']:
            return True
        # An open can fail after publication but before remember(). Admit that
        # partial panel only through its resource, never its arrival time.
        resource=getattr(getattr(panel,'document',None),'resource',None)
        provider=getattr(resource,'provider',None)
        if provider is not None and any(provider is row['provider'] for row in run['providers']):
            return True
        if run['root'] is None or provider is None:
            return False
        from pathlib import Path
        try:
            return Path(provider.root).resolve().is_relative_to(run['root'].resolve())
        except (AttributeError,TypeError,ValueError,OSError,RuntimeError):
            return False
    current=getattr(app,'notebook_panel',None)
    for panel in [*panels(app).values(),current]:
        if owned(panel):
            run['remember'](panel)
    for panel in run['panels'].values():
        session=getattr(panel,'session',None)
        key=getattr(session,'id',None)
        def retire(panel=panel,key=key,session=session):
            if panels(app).get(key) is panel:
                # A timed-out canvas can still be busy. Retire its bridge first;
                # pending production waits then stop at the existing lifetime guard.
                if getattr(panel,'busy',False):
                    panel.retire_canvas()
                if not close_notebook(app,key,'discard'):
                    raise AssertionError('Owned notebook refused teardown')
            elif not getattr(panel,'closed',False):
                panel.dispose()
            if session is not None and app.workspace.sessions.get(key) is session:
                app.workspace.close(key,guard=lambda session:True)
            assert panels(app).get(key) is not panel
            assert session is None or app.workspace.sessions.get(key) is not session
        attempt('panel '+str(key),retire)
    for record in run['providers']:
        if not record['closed']:
            def close(record=record):
                getattr(record['provider'],'close',lambda:None)()
                record['closed']=True
            attempt('provider '+record['label'],close)
    for repository,key in run['recoveries'].values():
        attempt('recovery '+key,lambda repository=repository,key=key:repository.delete(key))
    previous=run['previous_panel']
    def restore():
        if previous is None:
            if hasattr(app,'notebook_panel'):
                del app.notebook_panel
        else:
            app.notebook_panel=previous
        assert run['original_sessions'] <= set(app.workspace.sessions)
        for key,panel in run['original_registry'].items():
            assert panels(app).get(key) is panel
            assert getattr(panel,'closed',False)==run['original_closed'][id(panel)]
        active=run['previous_active']
        if active is not None:
            app.workspace.activate(active)
        # Restore the retained recent list as well: synthetic opens must not
        # evict pre-existing entries from its bounded history.
        recent=run['recent']
        if recent is not None:
            atomic_write_json(recent.path,run['recent_items'],max_bytes=64*1024,durable_directory=True)
            recent.items=run['recent_items']
        app.save_workspace()
        app.routes.render(run['previous_destination'])
        assert getattr(app,'notebook_panel',None) is previous
        assert app.cloud_client is run['client']
        assert getattr(app.cloud_client,'generation',None)==run['credential_generation']
        cleanup['original_restored']=True
    attempt('restore original session',restore)
    if run['temporary'] is not None:
        attempt('owned files',run['temporary'].cleanup)
    cleanup['files_removed']=run['root'] is None or not run['root'].exists()
    cleanup['providers_closed']=all(record['closed'] for record in run['providers'])
    cleanup['panels_closed']=all(getattr(panel,'closed',False) for panel in run['panels'].values())
    owned_sessions={id(panel.session) for panel in run['panels'].values() if getattr(panel,'session',None) is not None}
    cleanup['sessions_removed']=(not any(id(panel) in run['panels'] for panel in panels(app).values())
        and not any(id(session) in owned_sessions for session in app.workspace.sessions.values()))
    cleanup['credential_generation_unchanged']=(app.cloud_client is run['client'] and
        getattr(app.cloud_client,'generation',None)==run['credential_generation'])
    for key in ('original_restored','files_removed','providers_closed','panels_closed',
                'sessions_removed','credential_generation_unchanged'):
        if not cleanup.get(key):
            errors.append('Cleanup did not establish '+key)


async def exercise_notebook_images(app, *, output=None):
    """Required provider workflow; use the already-imported synthetic Secret remote.

    The caller owns the stage deadline. This function never imports credentials
    and propagates failures after publishing partial evidence and owned teardown.
    """
    from copy import deepcopy
    from hashlib import sha256
    from io import BytesIO
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from commonUtils.runtime.resources.local import LocalFiles
    from features.notebooks.notebook import Notebook, MAX_ARCHIVE
    from features.rclone.localcrypt.mobile.resources import CryptFiles
    from services.documents.storage import DocumentResource
    from services.documents.mobile_notebooks import open_notebook,close_notebook,panels
    from .fixtures import capture_window
    import base64
    import traceback
    report=dict(success=False,providers=[],cleanup=dict(errors=[],original_restored=False),error='',
        scope='Native WebView/PDF renderer and actual Local/Secret LocalCrypt; synthetic pointer-handler delivery',
        fixture_sha256=IMAGE_FIXTURE_SHA256)
    app._notebook_image_report=report
    report['phase']='fixture'
    try:
        original=Path(__file__).with_name('notebook-image-fixture.rmdoc').read_bytes()
        assert sha256(original).hexdigest()==IMAGE_FIXTURE_SHA256,'Staged notebook image fixture differs'
        original_book=Notebook.read(original)
        original_pdf=original_book.members[original_book.id+'.pdf']
    except BaseException:
        report['error']=traceback.format_exc()
        report['cleanup']['not_started']=True
        raise
    output=Path(output) if output is not None else Path(app.paths.cache)/'notebook-image-evidence'
    previous=getattr(app,'notebook_panel',None)
    recent=getattr(app,'recent_documents',None)
    run=dict(report=report,temporary=None,root=None,panels={},providers=[],recoveries={},
        original_registry=dict(panels(app)),original_closed={id(panel):getattr(panel,'closed',False) for panel in panels(app).values()},
        original_panels={id(panel) for panel in panels(app).values()} | ({id(previous)} if previous is not None else set()),
        original_sessions=set(app.workspace.sessions),
        previous_panel=previous,previous_active=app.workspace.active,
        previous_destination=app.native_host.state.destination,recent=recent,
        recent_items=deepcopy(recent.items) if recent is not None else None,
        client=app.cloud_client,credential_generation=getattr(app.cloud_client,'generation',None))
    def remember(panel):
        run['panels'][id(panel)]=panel
        document=getattr(panel,'document',None)
        if document is not None and document.recovery is not None:
            run['recoveries'][(id(document.recovery),document.key)]=(document.recovery,document.key)
    run['remember']=remember
    primary=None
    try:
        output.mkdir(parents=True,exist_ok=True)
        temporary=TemporaryDirectory(prefix='notebook-images-',dir=app.private_root)
        root=Path(temporary.name)
        run.update(temporary=temporary,root=root)
        app.set_feature_enabled('notebooks',True,refresh=False)
        app.show_home()
        for label in ('Local','LocalCrypt'):
            report['phase']=label+':open'
            folder=root/label;folder.mkdir()
            provider=LocalFiles(folder) if label=='Local' else CryptFiles(folder,app.cloud_client,'Secret')
            record=dict(label=label,provider=provider,closed=False);run['providers'].append(record)
            provider.create_file('images.rmdoc',BytesIO(original))
            assert await open_notebook(app,resource=DocumentResource(provider,'images.rmdoc',max_bytes=MAX_ARCHIVE))
            panel=app.notebook_panel;remember(panel)
            async def evaluate(code):
                return await panel.web.evaluate_javascript(code)
            async def capture(phase):
                await capture_window(app,output/(label+'-'+phase+'.png'))
                encoded=await evaluate("canvas.toDataURL('image/png')")
                (output/(label+'-'+phase+'-canvas.png')).write_bytes(base64.b64decode(encoded.split(',',1)[1]))
            def readiness(snapshot):
                report['wait_state'] = dict(snapshot, phase=report['phase'],
                    panel_closed=panel.closed, canvas_ready=getattr(panel,'_canvas_ready',False),
                    private_closed=getattr(panel.web,'private_closed',None))
            workflow=ImageWorkflow(evaluate,lambda:panel.editor,capture,progress=readiness,
                diagnostic=lambda snapshot:write_capture_diagnostic(output,label,snapshot))
            await workflow.idle()
            backend=verify_native_image_view(panel,provider)
            report['phase']=label+':capture-transform-arrange'
            await workflow.run()
            expected=signature(panel.editor.notebook)
            assert panel.document.resource.read()==original,'Source changed before Save'
            if label=='Local':
                assert signature(panel.document.recovery.open(panel.document.key))==expected
            else:
                assert panel.document.recovery is None
            await workflow.send(dict(op='save'))
            saved=panel.document.resource.read();book=Notebook.read(saved)
            assert signature(book)==expected
            assert book.members[book.id+'.pdf']==original_pdf
            (output/(label+'-saved.rmdoc')).write_bytes(saved)
            if label=='LocalCrypt':
                ciphertext=provider._physical('images.rmdoc').read_bytes()
                assert b'%PDF' not in ciphertext and b'PNG' not in ciphertext
            assert close_notebook(app,panel.session.id,'discard')
            report['phase']=label+':reopen'
            assert await open_notebook(app,resource=DocumentResource(provider,'images.rmdoc',max_bytes=MAX_ARCHIVE))
            panel=app.notebook_panel;remember(panel)
            reopened=ImageWorkflow(evaluate,lambda:panel.editor,capture,progress=readiness)
            await reopened.idle()
            assert verify_native_image_view(panel,provider)==backend
            await evaluate(HELPERS);await reopened.unlock()
            assert signature(panel.editor.notebook)==expected
            await capture('reopened')
            report['providers'].append(dict(provider=label,backend=backend,cases=workflow.cases,
                saved_sha256=sha256(saved).hexdigest(),password_reprompt=True,pdf_ciphertext_preserved=True,
                recovery_checked=label=='Local',reopened=True))
            assert close_notebook(app,panel.session.id,'discard')
            getattr(provider,'close',lambda:None)();record['closed']=True
        assert [row['provider'] for row in report['providers']]==['Local','LocalCrypt']
    except BaseException as error:
        primary=error
        report['error']=traceback.format_exc()
        raise
    finally:
        try:
            _cleanup_image_run(app,run)
            report['evidence_directory']=output.name
            report['artifact_names']=sorted(p.name for p in output.iterdir() if p.suffix in ('.png','.rmdoc')) if output.is_dir() else []
        except BaseException as cleanup_error:
            report['cleanup']['errors'].append(type(cleanup_error).__name__+': '+str(cleanup_error))
        if report['cleanup']['errors']:
            detail='Notebook image cleanup: '+'; '.join(report['cleanup']['errors'])
            if primary is not None:
                primary.add_note(detail)
            else:
                report['error']=detail
                raise AssertionError(detail)
    report['phase']='complete'
    report['success']=True
    return report
