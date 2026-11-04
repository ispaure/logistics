"""One real WebView workflow shared by native desktop, Android and iOS probes."""
import asyncio
import json
import math

from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION

HELPERS = r'''window.imageQA = {
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
  async clipPixels() {
    const img=new Image();img.src=imageClipboard.src;await img.decode();
    const c=document.createElement('canvas');c.width=img.width;c.height=img.height;
    const g=c.getContext('2d');g.drawImage(img,0,0);
    return {width:c.width,height:c.height,pixels:[[100,150],[250,170],[100,70],[390,310]].map(p=>[...g.getImageData(...p,1,1).data])};
  }
};true'''


def signature(book):
    from features.notebooks.notebook import Notebook
    book = Notebook.read(book.to_bytes())
    return [dict(images=[p.payload() for p in book.page(i).images],
                 strokes=[s.payload() for s in book.page(i).strokes], order=book.page(i).order)
            for i in range(len(book.pages))]


class ImageWorkflow:
    def __init__(self, evaluate, editor, capture):
        self.evaluate, self.editor, self.capture = evaluate, editor, capture
        self.cases = []

    async def js(self, expression):
        # A JSON result has the same shape in Qt, Android WebView and WKWebView.
        encoded = await self.evaluate('JSON.stringify((()=>{' + expression + '})())')
        return json.loads(encoded) if isinstance(encoded, str) else encoded

    async def wait(self, expression, message):
        for _ in range(400):
            if await self.js('return Boolean(' + expression + ')'):
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

    async def run(self):
        await self.idle()
        await self.evaluate(HELPERS)
        await self.unlock()
        assert len(self.editor().notebook.page(0).images) == 1
        await self.action("$('capture').click();$('newCutout').click();imageQA.gesture([[100,100],[500,100],[500,350],[350,420],[100,420],[100,100]])")
        await self.evaluate("window.qaClip=null;imageQA.clipPixels().then(p=>window.qaClip=p);true")
        await self.wait('window.qaClip!==null', 'Clipboard PNG did not decode')
        clip = await self.js('return window.qaClip')
        assert (clip['width'],clip['height']) == (400,320), clip
        red, green, ink, outside = clip['pixels']
        assert red[0]>180 and red[1]<120 and red[3]==255, clip
        assert green[1]>140 and green[0]<100 and green[3]==255, clip
        assert ink[0]<red[0]-40 and ink[3]==255 and outside[3]==0, clip
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
        await self.send(dict(op='stroke',tool=17,width=3,color=0,points=[[center[0]-30,center[1],1],[center[0]+30,center[1],1]]))
        above = await self.js('return imageQA.pixel(imageQA.center())')
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
