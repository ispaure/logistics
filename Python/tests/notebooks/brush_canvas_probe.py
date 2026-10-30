"""Real WebEngine checks for both notebook presentations and brush pixels."""
import argparse
import base64
import json
from pathlib import Path

from commonUtils.ui import pyside as qt
from commonUtils.runtime.diagnostics import Severity, log
from features.notebooks.brushes import BRUSHES, stroke_points
from features.notebooks.canvas import editor_html
from features.notebooks.notebook import Notebook
from features.notebooks.editor import Editor
from features.notebooks.mobile.surface import mobile_editor_html
from features.notebooks.ui.workspace import QWebEngineView


CHECKS = r'''
(()=>{try{
const check=(value,message)=>{if(!value)throw Error(message)};
check(frameBatchedInk===expectedFrameBatching,'Wrong desktop/mobile paint scheduling');
check(!state.native_pen||!ctx.getContextAttributes().desynchronized,'Native preview must not share a desynchronized canvas front buffer');
check(eraserKind==='partial'&&eraserRadius===16,'Partial eraser must be the default');
$('erase').click();check(mode==='erase'&&eraserDialog.open,'Eraser button must show settings');
check($('eraserSize').options.length===3,'Expected three eraser sizes');
$('eraserKind').value='whole';$('eraserKind').dispatchEvent(new Event('change'));
$('eraserSize').value='32';$('eraserSize').dispatchEvent(new Event('change'));
check(eraserKind==='whole'&&eraserRadius===32,'Eraser controls did not change settings');
$('closeEraser').click();
$('erase').click();check(eraserDialog.open&&eraserKind==='whole','Pressing active eraser must reopen settings');
$('eraserKind').value='partial';$('eraserKind').dispatchEvent(new Event('change'));
$('eraserSize').value='16';$('eraserSize').dispatchEvent(new Event('change'));
$('closeEraser').click();
// Exercise the actual shared pointer path, inspecting the queued command without sending it.
let originalSend=send,erased=null;send=action=>{erased=action};
let bounds=canvas.getBoundingClientRect(),event=(x,y)=>({pointerId:12345,pointerType:'pen',nativePen:true,
clientX:bounds.left+x/state.width*bounds.width,clientY:bounds.top+y/state.height*bounds.height,
pressure:.5,preventDefault(){}});
canvas.onpointerdown(event(100,100));canvas.onpointermove(event(200,200));finish(event(300,300));
send=originalSend;
check(erased?.op==='erase'&&erased.kind==='partial'&&erased.radius===16&&erased.points.length===3,'Pointer gesture lost eraser path, kind or size');
$('tool').onchange();
const before=JSON.stringify(state),samples=[[30,60,.15],[85,60,.85],[130,110,.85],[185,60,.4],[240,60,.7]];
const surface=document.createElement('canvas');surface.width=280;surface.height=150;const target=surface.getContext('2d');
const reset=()=>{target.clearRect(0,0,280,150);target.fillStyle='white';target.fillRect(0,0,280,150)};
const pixel=(x,y)=>Array.from(target.getImageData(x,y,1,1).data);
let signatures=[],controls=[];
const choose=tool=>{let button=document.querySelector('#brushes [data-value="'+tool+'"]')||document.querySelector('.brush-card[data-tool="'+tool+'"]');check(button,'Missing visual brush choice');button.click()};
for(let tool of Object.values(state.tools)){
choose(tool);
check($('width').options.length===3,'Expected three widths');
check(JSON.stringify(Array.from($('color').options,o=>Number(o.value)))===JSON.stringify(brushes[tool].colors),'Wrong brush palette '+tool);
check(document.querySelectorAll('.swatch').length===brushes[tool].colors.length,'Visual swatches out of sync '+tool);
for(let b of document.querySelectorAll('.swatch')){let choice=Number(b.dataset.value??b.dataset.color),dot=b.querySelector('circle')||b.querySelector('span')||b;let shown=(dot.tagName.toLowerCase()==='circle'?getComputedStyle(dot).fill:getComputedStyle(dot).backgroundColor).match(/\d+/g).slice(0,3).map(Number);check(shown.join(',')===swatchColor(tool,choice).join(','),'Swatch ignores brush RGBA '+tool+'/'+choice)}
if(tool===18)check(!$('color').querySelector('option[value="0"]'),'Black must not be a highlighter choice');
for(let width=1;width<=3;width++)check(JSON.stringify(strokePoints(samples,tool,width))===JSON.stringify(expected[tool][width]),'Preview/model widths differ '+tool+'/'+width);
controls.push({tool,colors:$('color').options.length,widths:$('width').options.length});
reset();let color=tool===18?13:tool===23?1:0;
line({tool,...nativeColor(tool,color),points:strokePoints(samples,tool,2)},target);
signatures.push(surface.toDataURL());
}
check(new Set(signatures).size===9,'Brush renderings must be distinct');
// Bounded filtered ink must preserve the established full-surface raster,
// including transformed and edge-clipped strokes. Readback forces completion.
const boundedPaintbrush=clipPaintbrush;
try{
  for(const scale of [.5,1,2]){
    const ink={tool:12,color:0,points:strokePoints(samples,12,3)};
    reset();target.save();target.scale(scale,scale);clipPaintbrush=()=>{};
    line(ink,target);target.restore();const reference=surface.toDataURL();
    reset();target.save();target.scale(scale,scale);clipPaintbrush=boundedPaintbrush;
    line(ink,target);target.restore();
    check(surface.toDataURL()===reference,'Bounded paintbrush changed pixels at scale '+scale);
  }
}finally{clipPaintbrush=boundedPaintbrush}

reset();const red={tool:17,color:7,scale:9,points:[[30,60,.5,4],[240,60,.5,4]]};
line(red,target);let colorPixel=pixel(80,60);check(colorPixel[0]>colorPixel[1],'Color preview lost red');
check(pixel(80,66)[0]===255,'Point width was multiplied by thickness scale');
reset();line({tool:17,color:0,points:[[30,60,.5,4],[240,60,.5,20]]},target);check(pixel(225,66)[0]<80,'Imported variable point widths were discarded');
reset();line({tool:17,color:0,points:[[30,60,.5,0],[240,60,.5,0]]},target);check(pixel(80,60)[0]===255,'Zero-width imported ink acquired a default canvas width');
$('grayscale').checked=true;$('grayscale').dispatchEvent(new Event('change'));reset();line(red,target);let gray=pixel(80,60);
check(gray[0]===gray[1]&&gray[1]===gray[2]&&gray[0]<255,'Grayscale preview not gray');
check(JSON.stringify(state)===before,'Preview changed notebook state');
check(red.color===7,'Preview changed native red');
let orange=nativeColor(18,-1);check(orange.color===9&&orange.color_rgba.join(',')==='255,195,140,255','Lost native highlight RGBA');
reset();line({tool:17,color:9,color_rgba:[255,0,0,255],points:[[30,60,.5,4],[240,60,.5,4]]},target);
check(pixel(80,60)[0]===pixel(80,60)[1],'RGBA bypassed grayscale');
$('grayscale').checked=false;$('grayscale').dispatchEvent(new Event('change'));reset();
let shader={tool:23,...nativeColor(23,1),points:[[30,60,.5,30],[130,60,.5,30],[240,60,.5,30]]};line(shader,target);
let middle=pixel(130,60)[0],edge=pixel(80,60)[0];check(Math.abs(middle-edge)<=1,'Shader joins accumulate opacity');
line(shader,target);check(pixel(80,60)[0]<edge,'Separate shader strokes must build up');
check(brushes[23].colors.length===8&&!brushes[23].colors.includes(0)&&!brushes[23].colors.includes(2),'Shader must not offer black/white pen colors');
check(nativeColor(23,-1).color_rgba.join(',')==='254,178,0,115','Shader orange must use native color-specific alpha');
// Exercise streaming drawing, rather than only the final renderer. In
// particular, calligraphy widths must keep their incoming travel direction.
// Compare geometry at native resolution: fit-to-phone makes pencil grain
// subpixel-sized and magnifies rasterization differences between masks.
$('zoom').value='1';resize();
// All fixture ink fits in this rectangle. Full-page comparison canvases at
// high DPI waste hundreds of MiB and can make emulated Windows swap mid-test.
const pw=Math.ceil(280*canvas.width/state.width),ph=Math.ceil(150*canvas.height/state.height);
let previewErrors=[],previewWork=[],committedBrushes=[];
for(let tool of Object.values(state.tools)){
let color=tool===18?13:tool===23?1:0;
inkSettings={tool,color,width:3,layer:state.layers[0][0]};points=[];clearDraft();ctx.clearRect(0,0,state.width,state.height);
for(let sample of samples){let before=points.at(-1);points.push(sample);preview(before?[before,sample]:[sample])}
let composed=document.createElement('canvas');composed.width=pw;composed.height=ph;let actual=composed.getContext('2d',{willReadFrequently:true});actual.fillStyle='white';actual.fillRect(0,0,pw,ph);actual.drawImage(canvas,0,0);actual.globalCompositeOperation=draft.style.mixBlendMode||'source-over';actual.drawImage(draft,0,0);
let expectedCanvas=document.createElement('canvas');expectedCanvas.width=pw;expectedCanvas.height=ph;let final=expectedCanvas.getContext('2d',{willReadFrequently:true});final.fillStyle='white';final.fillRect(0,0,pw,ph);final.setTransform(canvas.width/state.width,0,0,canvas.height/state.height,0,0);line({tool,...nativeColor(tool,color),points:strokePoints(samples,tool,3)},final);
let a=actual.getImageData(0,0,pw,ph).data,b=final.getImageData(0,0,pw,ph).data,inkPixels=0,badPixels=0,totalError=0,totalInk=0;
for(let i=0;i<a.length;i+=4){if(a[i]<250||a[i+1]<250||a[i+2]<250||b[i]<250||b[i+1]<250||b[i+2]<250){inkPixels++;for(let c=0;c<3;c++){totalError+=Math.abs(a[i+c]-b[i+c]);totalInk+=255-b[i+c]}if(Math.max(Math.abs(a[i]-b[i]),Math.abs(a[i+1]-b[i+1]),Math.abs(a[i+2]-b[i+2]))>25)badPixels++}}
let error=totalError/Math.max(1,totalInk);previewErrors.push({tool,error,edgeDifferences:badPixels/Math.max(1,inkPixels)});check(error<.18,'Streaming/saved brush mismatch '+tool+': '+error);
if(!['fineliner','ballpoint'].includes(brushFor(tool).family)){
ctx.fillStyle='#789abc';ctx.fillRect(20,40,160,50);
let reference=document.createElement('canvas');reference.width=pw;reference.height=ph;let overlay=reference.getContext('2d',{willReadFrequently:true});overlay.fillStyle='white';overlay.fillRect(0,0,pw,ph);overlay.drawImage(canvas,0,0);overlay.globalCompositeOperation=draft.style.mixBlendMode||'source-over';overlay.drawImage(draft,0,0);
let painted=overlay.getImageData(0,0,pw,ph).data;
let original=geometry,replayed=0;geometry=(...args)=>{replayed++;return original(...args)};
try{commitDraft(tool)}finally{geometry=original}
check(replayed===0,'Pen-up rebuilt completed geometry '+tool);
let committed=document.createElement('canvas');committed.width=pw;committed.height=ph;let result=committed.getContext('2d',{willReadFrequently:true});result.fillStyle='white';result.fillRect(0,0,pw,ph);result.drawImage(canvas,0,0);
let pixels=result.getImageData(0,0,pw,ph).data;
let changed=false;for(let i=0;i<painted.length;i++)if(Math.abs(painted[i]-pixels[i])>1){changed=true;break}
check(!changed,'Pen-up changed painted brush pixels '+tool);
check(draftCount===0&&draftBounds===null,'Pen-up retained draft geometry '+tool);committedBrushes.push(tool);
}
// Instrument geometry work after 2,000 samples. A move must touch only the
// trailing segment, not replay the entire active stroke or saved scene.
points=Array.from({length:2000},(_,i)=>[30+i/20,60+Math.sin(i/20)*10,.6]);clearDraft();preview(points);
let original=geometry,touched=0;geometry=(target,p,family)=>{touched+=p.length;original(target,p,family)};
try{let previous=points.at(-1);points.push([131,65,.6]);preview([previous,points.at(-1)])}finally{geometry=original}
check(touched<=2,'Preview work grows with stroke length '+tool);previewWork.push({tool,touched});
}
// A burst keeps every pressure sample but paints once, including a forced
// final flush when pen-up precedes the scheduled animation frame.
points=[];inkSettings={tool:17,color:0,width:2,layer:state.layers[0][0]};cancelPreview();
let paint=preview,paints=0;preview=(...args)=>{paints++;return paint(...args)};
try{let box=canvas.getBoundingClientRect();for(let i=0;i<100;i++)sample({clientX:box.left+(30+i)*box.width/state.width,clientY:box.top+60*box.height/state.height,pointerType:'pen',pressure:i/100});check(paints===0&&points.length===100,'Input burst painted eagerly or discarded samples');flushPreview();check(paints===1&&previewFrame===null&&previewCount===100,'Pen-up failed to flush all samples');flushPreview();check(paints===1,'Final preview painted twice');check(points[99][2]===.99,'Frame batching lost pressure')}finally{preview=paint;cancelPreview()}
points=[];inkSettings=null;pendingInk={tool:23,...nativeColor(23,7),points:[[30,60,.6,20],[240,60,.6,20]]};draw();
let x=Math.round(80*canvas.width/state.width),y=Math.round(60*canvas.height/state.height);
let pendingColor=ctx.getImageData(x,y,1,1).data;check(pendingColor[0]>pendingColor[1],'Pending completed stroke lost on redraw');
$('grayscale').checked=true;$('grayscale').dispatchEvent(new Event('change'));let pendingGray=ctx.getImageData(x,y,1,1).data;
check(pendingGray[0]===pendingGray[1]&&pendingGray[1]===pendingGray[2]&&pendingGray[3]>0,'Pending stroke lost when switching preview');
$('grayscale').checked=false;$('grayscale').dispatchEvent(new Event('change'));window.notebookUpdate(state);
check(pendingInk===null&&ctx.getImageData(x,y,1,1).data[3]===0,'Acknowledgement did not retire pending preview');
// Eraser patches retain overlapping colors, translucent/blurred nibs and order
// while omitting the unchanged stroke payload from the acknowledgement.
const eraseState=state.strokes,eraseLayer=state.layers[0][0];
for(const tool of Object.values(state.tools)){
  const color=tool===18?13:tool===23?1:7;
  const old={id:'cut',layer:eraseLayer,tool,...nativeColor(tool,color),points:[[30,60,.5,12.25],[240,60,.5,12.25]]};
  const under={id:'under',layer:eraseLayer,tool:17,color:6,points:[[30,65,.5,4],[240,65,.5,4]]};
  const left={...old,points:[[30,60,.5,12.25],[90,60,.5,12.25]]};
  const right={...old,id:'right',points:[[170,60,.5,12.25],[240,60,.5,12.25]]};
  state.strokes=[under,old];draw();
  pendingErase={points:[[130.1,30.2,.5],[130.1,90.2,.5]],radius:32};previewErase(pendingErase.points,32);
  window.notebookInkUpdate({order:['under','cut','right'],strokes:[left,right],undo:true,redo:false,save_status:'Saved'});
  const patched=ctx.getImageData(0,0,pw,ph).data;draw();const full=ctx.getImageData(0,0,pw,ph).data;
  let differences=0,maxDifference=0,firstDifference=null;
  patched.forEach((v,i)=>{if(v!==full[i]){differences++;maxDifference=Math.max(maxDifference,Math.abs(v-full[i]));firstDifference??=[(i/4|0)%pw,(i/4/pw|0),v,full[i]]}});
  check(!differences,'Eraser patch differs from full redraw '+JSON.stringify({tool,differences,maxDifference,firstDifference}));
  check(state.strokes[0]===under,'Eraser patch replaced unchanged ink '+tool)
}
state.strokes=eraseState;draw();
// Contact sheet generated by the real renderer, at native canvas coordinates.
let sheet=document.createElement('canvas');sheet.width=1100;sheet.height=9*180+90;let g=sheet.getContext('2d');
g.fillStyle='#f7f7f2';g.fillRect(0,0,sheet.width,sheet.height);g.fillStyle='#222';g.font='24px sans-serif';g.fillText('Paper Pro / Move · Thin / Medium / Thick',20,40);
let row=0;for(let [name,tool] of Object.entries(state.tools)){
let y=70+row*180;g.fillStyle='#fff';g.fillRect(10,y,1080,170);g.fillStyle='#222';g.font='18px sans-serif';g.fillText(name,24,y+28);
for(let width=1;width<=3;width++){g.save();g.translate(195+(width-1)*290,y+30);line({tool,...nativeColor(tool,tool===18?13:tool===23?1:0),points:strokePoints(samples,tool,width)},g);g.restore()}
row++}
choose(17);$('zoom').value='fit';resize();
return JSON.stringify({success:true,controls,distinct:signatures.length,grayscale:true,native_rgba:true,width_parity:true,eraser_controls:true,eraser_pointer_path:true,shader_blending:true,bounded_filter_raster:true,previewErrors,previewWork,committedBrushes,frame_batching:true,sheet:sheet.toDataURL()});
}catch(error){return JSON.stringify({success:false,error:String(error),stack:error.stack})}})()
'''


def main(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    samples = [[30, 60, .15], [85, 60, .85], [130, 110, .85], [185, 60, .4], [240, 60, .7]]
    expected = {tool: {width: stroke_points(samples, tool, width) for width in (1, 2, 3)} for tool in BRUSHES}
    results, failed = {}, []
    views = []

    def run(desktop, batched=False):
        name = 'desktop' if desktop else 'mobile-ios' if batched else 'mobile'
        view = QWebEngineView()
        view.resize(1200, 900)
        views.append(view)
        view.show()

        def checked(encoded):
            try:
                result = json.loads(encoded)
                if not result['success']:
                    raise AssertionError(result)
                image = result.pop('sheet').split(',', 1)[1]
                (output / (name + '-brushes.png')).write_bytes(base64.b64decode(image))
                view.grab().save(str(output / (name + '-controls.png')))
                results[name] = result
                view.close()
                if desktop:
                    run(False)
                elif not batched:
                    run(False, True)
                else:
                    app.quit()
            except Exception as error:
                failed.append(str(error))
                app.quit()

        def loaded(ok):
            if not ok:
                failed.append('WebEngine load failed')
                app.quit()
                return
            view.page().runJavaScript('const expectedFrameBatching=' + json.dumps(desktop or batched) + ';const expected=' + json.dumps(expected) + ';' + CHECKS, checked)

        view.loadFinished.connect(loaded)
        state = Editor(Notebook.new('Brush compatibility')).state()
        state['frame_batched_ink'] = batched
        state['native_pen'] = not desktop and not batched
        if desktop:
            html = editor_html(state, 'logistics-notebook://brush-probe/', console_bridge=True, desktop=True)
        else:
            html = mobile_editor_html(state, 'logistics-notebook://brush-probe/', console_bridge=True)
        view.setHtml(html)

    run(True)
    qt.QTimer.singleShot(60000, lambda: (failed.append('Probe timed out'), app.quit()))
    app.exec()
    for view in views:
        view.close()
    if failed:
        raise RuntimeError('; '.join(failed))
    (output / 'brush-checks.json').write_text(json.dumps(results, indent=2) + '\n')
    log(Severity.INFO, 'Notebook brush acceptance', 'Desktop and both mobile scheduling modes passed palettes, widths, model/preview parity, bounded-filter raster, distinct pixels, grayscale and native RGBA checks.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    main(parser.parse_args().output)
