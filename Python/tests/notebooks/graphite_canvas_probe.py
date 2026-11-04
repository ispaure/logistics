"""Original synthetic graphite appearance and display/export boundary checks.

Optional real-browser probe. Timings are functional observations, not physical
pen latency or a benchmark conducted on an otherwise idle machine.
"""
import argparse
import base64
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import traceback

from commonUtils.ui import pyside as qt
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from features.notebooks.canvas import editor_html
from features.notebooks.editor import Editor
from features.notebooks.mobile.surface import mobile_editor_html
from logistics_build.build_retention import scratch
from tests.notebooks.graphite_fixtures import archive_members, graphite_notebook, snapshot_export
from tests.notebooks.webengine_driver import javascript, wait_until


CHECKS = r'''(()=>{try{
const check=(ok,message)=>{if(!ok)throw Error(message)},originalGrain=grain;
const stateBefore=JSON.stringify(state),grayBefore=$('grayscale').checked;
const cold=[];grainCache.clear();graphiteMasks.clear();
for(const mechanical of [false,true]){const start=performance.now();grain(ctx,[0,0,0],mechanical);cold.push({mechanical,ms:performance.now()-start})}
const make=(scale=1)=>{const c=document.createElement('canvas');c.width=360*scale;c.height=160*scale;
 const g=c.getContext('2d',{willReadFrequently:true});g.setTransform(scale,0,0,scale,0,0);return {c,g}};
const stroke=(tool,points,color=0)=>({tool,...nativeColor(tool,color),points});
const image=(tool,points,scale=1,color=0)=>{const {c,g}=make(scale);line(stroke(tool,points,color),g);return c};
const pixels=c=>c.getContext('2d',{willReadFrequently:true}).getImageData(0,0,c.width,c.height).data;
const digest=c=>c.toDataURL();
const compare=(a,b)=>{let sum=0,ink=0,max=0;
 for(let i=3;i<a.length;i+=4){sum+=Math.abs(a[i]-b[i]);ink+=b[i];max=Math.max(max,Math.abs(a[i]-b[i]))}
 return {normalized:sum/Math.max(1,ink),max}};
const constant=[[20,80,.5,8],[320,80,.5,8]],dense=Array.from({length:151},(_,i)=>[20+i*2,80,.5,8]);
let metrics=[];
for(const tool of [14,13]){
 const frozen=constant.map(p=>Object.freeze([...p]));Object.freeze(frozen);
 const first=image(tool,frozen),again=image(tool,frozen);
 check(digest(first)===digest(again),'Redrawing changed fixed graphite pixels '+tool);
 const sparse=pixels(first),densified=compare(pixels(image(tool,dense)),sparse);
 check(densified.normalized<.02,'History sample density changed graphite opacity '+JSON.stringify({tool,densified}));
 const retrace=compare(pixels(image(tool,[...constant,...constant.slice().reverse()])),sparse);
 check(retrace.normalized<.02,'Retracing inside one stroke darkened graphite '+JSON.stringify({tool,retrace}));
 const row=first.getContext('2d').getImageData(30,80,272,1).data;
 let repeat8=0;for(let x=0;x<264;x++)repeat8+=Math.abs(row[x*4+3]-row[(x+8)*4+3]);
 repeat8/=264;
 check(repeat8>.5,'Graphite still has the old repeating eight-unit lattice '+tool);
 check(new Set(Array.from(row).filter((_,i)=>i%4===3)).size>3,'Graphite lost its interior paper tooth '+tool);
 let scales=[];
 for(const scale of [.5,1,2,4]){
  const one=image(tool,constant,scale),two=image(tool,constant,scale);
  check(digest(one)===digest(two),'Graphite changes across identical zoom/DPR redraws');
  scales.push({scale,width:one.width,height:one.height});
 }
 $('grayscale').checked=true;
 const gray=pixels(image(tool,constant,1,7));
 check(Array.from({length:gray.length/4},(_,i)=>i*4).every(i=>!gray[i+3]||(gray[i]===gray[i+1]&&gray[i+1]===gray[i+2])),
  'Colored graphite ignores grayscale '+tool);
 $('grayscale').checked=false;
 const red=pixels(image(tool,constant,1,7));
 check(Array.from({length:red.length/4},(_,i)=>i*4).some(i=>red[i+3]>100&&red[i]>red[i+1]),'Graphite lost writing hue '+tool);
 metrics.push({tool,densified,retrace,repeat8,scales});
}
check(digest(image(14,constant))!==digest(image(13,constant)),'Pencil and Mechanical Pencil look identical');

// Compare old and new app code with original, non-handwritten fixture paths.
const sheet=document.createElement('canvas');sheet.width=2400;sheet.height=1710;const g=sheet.getContext('2d');
g.fillStyle='#e9ece7';g.fillRect(0,0,sheet.width,sheet.height);g.fillStyle='#20251e';g.font='26px sans-serif';
const headings=['Pencil - previous','Pencil - original graphite','Mechanical - previous','Mechanical - original graphite'];
headings.forEach((text,i)=>g.fillText(text,i*600+20,40));
const wave=p=>Array.from({length:91},(_,i)=>[20+i*3,55+Math.sin(i/8)*18,p]);
const rows=[
 {name:'Thin / light pressure - white paper',color:0,width:1,samples:wave(.15),paper:'#fff'},
 {name:'Thick / firm pressure - white paper',color:0,width:3,samples:wave(.9),paper:'#fff'},
 {name:'Variable pressure / diagonal - warm paper',color:0,width:3,samples:Array.from({length:91},(_,i)=>[20+i*3,25+i*.65,.08+i/100]),paper:'#f4ead5'},
 {name:'Crosshatch - white paper',color:0,width:2,samples:wave(.65),paper:'#fff',hatch:true},
 {name:'Two overlapping strokes - warm paper',color:0,width:3,samples:wave(.65),paper:'#f4ead5',overlap:true},
 {name:'Red graphite / native color',color:7,width:3,samples:wave(.65),paper:'#fff'}
];
try{
 for(let row=0;row<rows.length;row++)for(let col=0;col<4;col++){
  const spec=rows[row],tool=col<2?14:13,left=col*600,top=60+row*270;
  g.fillStyle=spec.paper;g.fillRect(left+8,top,584,256);g.fillStyle='#31382f';g.font='17px sans-serif';g.fillText(spec.name,left+20,top+26);
  grain=col%2===0?oldGraphiteGrain:originalGrain;
  g.save();g.translate(left+16,top+58);g.scale(1.8,1.8);
  line(stroke(tool,strokePoints(spec.samples,tool,spec.width),spec.color),g);
  if(spec.overlap){g.translate(0,5);line(stroke(tool,strokePoints(spec.samples,tool,spec.width),spec.color),g)}
  if(spec.hatch)for(let i=0;i<8;i++)line(stroke(tool,strokePoints([[35+i*30,15,.65],[65+i*30,100,.65]],tool,spec.width),spec.color),g);
  g.restore();
 }
}finally{grain=originalGrain}

// Native-scale live draft, pen-up compositing, and bounded work remain real.
let previewChecks=[];
setZoom(1);
const uiWarming=[];
for(const [tool,color,gray] of [[14,0,false],[14,7,false],[13,7,false],[13,7,true]]){
 $('tool').value=String(tool);$('tool').onchange();$('color').value=String(color);
 $('color').dispatchEvent(new Event('change',{bubbles:true}));
 $('grayscale').checked=gray;$('grayscale').dispatchEvent(new Event('change',{bubbles:true}));
 const create=document.createElement,upload=CanvasRenderingContext2D.prototype.putImageData;
 let canvases=0,uploads=0;
 document.createElement=function(name,...args){if(name==='canvas')canvases++;return create.call(this,name,...args)};
 CanvasRenderingContext2D.prototype.putImageData=function(...args){uploads++;return upload.apply(this,args)};
 try{
  clearDraft();points=[[30,60,.6],[50,70,.6]];inkSettings={tool,color,width:2,layer:state.layers[0][0]};preview(points);
 }finally{document.createElement=create;CanvasRenderingContext2D.prototype.putImageData=upload;points=[];clearDraft();inkSettings=null}
 check(canvases===0&&uploads===0,'Selected graphite was not warm before first contact '+JSON.stringify({tool,color,gray,canvases,uploads}));
 uiWarming.push({tool,color,gray,canvases,uploads});
}
$('grayscale').checked=false;
const oldActive=active;active=123456;
const cacheBefore=[...grainCache.keys()],masksBefore=graphiteMasks.size,oldColor=$('color').value;
$('color').value='10';$('color').dispatchEvent(new Event('change',{bubbles:true}));
active=oldActive;$('color').value=oldColor;
check(JSON.stringify([...grainCache.keys()])===JSON.stringify(cacheBefore)&&graphiteMasks.size===masksBefore,
 'UI warming did cold work during active ink');
for(const tool of [14,13]){
 const samples=wave(.65);inkSettings={tool,color:0,width:3,layer:state.layers[0][0]};
 points=[];clearDraft();ctx.clearRect(0,0,state.width,state.height);
 for(const sample of samples){points.push(sample);preview(points.slice(-2))}
 const width=Math.ceil(360*canvas.width/state.width),height=Math.ceil(160*canvas.height/state.height);
 const before=document.createElement('canvas');before.width=width;before.height=height;
 const live=before.getContext('2d');live.drawImage(canvas,0,0);live.drawImage(draft,0,0);
 const expected=document.createElement('canvas');expected.width=width;expected.height=height;
 const target=expected.getContext('2d');target.setTransform(canvas.width/state.width,0,0,canvas.height/state.height,0,0);
 line(stroke(tool,strokePoints(samples,tool,3)),target);
 const agreement=compare(pixels(before),pixels(expected));
 check(agreement.normalized<.18,'Live/completed graphite mismatch '+JSON.stringify({tool,agreement}));
 let originalGeometry=geometry,replayed=0;geometry=(...args)=>{replayed++;return originalGeometry(...args)};
 const commitStart=performance.now();try{commitDraft(tool)}finally{geometry=originalGeometry}
 const commitMs=performance.now()-commitStart,committed=document.createElement('canvas');committed.width=width;committed.height=height;
 committed.getContext('2d').drawImage(canvas,0,0);
 const after=pixels(committed),previous=pixels(before);let maxDifference=0;
 for(let i=0;i<after.length;i++)maxDifference=Math.max(maxDifference,Math.abs(after[i]-previous[i]));
 check(maxDifference<=1&&replayed===0,'Pen-up changed graphite pixels or replayed geometry '+JSON.stringify({tool,maxDifference,replayed}));
 points=Array.from({length:2000},(_,i)=>[30+i*.08,60+Math.sin(i/20)*10,.6]);clearDraft();preview(points);
 let touched=0;originalGeometry=geometry;geometry=(target,p,...args)=>{touched+=p.length;return originalGeometry(target,p,...args)};
 const moveStart=performance.now();try{points.push([190,65,.6]);preview(points.slice(-2))}finally{geometry=originalGeometry}
 const warmMoveMs=performance.now()-moveStart;
 check(touched<=2,'Graphite move reprocessed stroke history '+tool);
 previewChecks.push({tool,agreement,maxDifference,replayed,touched,commitMs,warmMoveMs});
 points=[];clearDraft();
}
inkSettings=null;
const warmStart=performance.now();for(let i=0;i<1000;i++)grain(ctx,[0,0,0],i%2===0);
const warm1000Ms=performance.now()-warmStart;
for(let i=0;i<80;i++)grain(ctx,[i,90,140],i%2===0);
check(grainCache.size<=24&&graphiteMasks.size<=2,'Graphite cache grows without its bounded resource budget');
$('grayscale').checked=grayBefore;
check(JSON.stringify(state)===stateBefore,'Graphite rendering mutated native stroke state');
return JSON.stringify({success:true,metrics,previewChecks,uiWarming,cold,warm1000Ms,cacheEntries:grainCache.size,alphaMaskEntries:graphiteMasks.size,
 display_only:true,physical_stylus:false,sheet:sheet.toDataURL()});
}catch(error){return JSON.stringify({success:false,error:String(error),stack:error.stack})}})()'''


def main(output, baseline='HEAD'):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    old = subprocess.check_output(['git', 'show', baseline + ':Python/features/notebooks/assets/drawing.js'], text=True)
    old = old[old.index('const grainCache = new Map();'):old.index('// Stored point arrays')]
    baseline_function = 'const oldGraphiteGrain=(()=>{' + old + ';return grain})();'
    app = qt.QApplication.instance() or qt.QApplication([])
    book = graphite_notebook()
    original = archive_members(book.to_bytes())
    exported = archive_members(snapshot_export(book))
    report = dict(success=False, presentations={}, baseline_revision=baseline,
                  drawing_sha256=sha256(Path('Python/features/notebooks/assets/drawing.js').read_bytes()).hexdigest())
    with scratch() as workspace:
        report['workspace'] = str(workspace)
        try:
            for name, desktop, batched in [('desktop', True, True), ('mobile', False, False), ('mobile-ios', False, True)]:
                view = QWebEngineView()
                profile = QWebEngineProfile(view)  # Off-the-record; no shared disk profile.
                page = QWebEnginePage(profile, view)
                view.setPage(page)
                view.resize(1200, 900)
                view.show()
                try:
                    loaded = []
                    view.loadFinished.connect(loaded.append)
                    state = dict(Editor(book).state(), frame_batched_ink=batched)
                    html = (editor_html(state, 'logistics-notebook://graphite/', console_bridge=True, desktop=True)
                            if desktop else mobile_editor_html(state, 'logistics-notebook://graphite/', console_bridge=True))
                    view.setHtml(html)
                    wait_until(lambda: bool(loaded), 'graphite HTML load')
                    assert loaded[-1]
                    result = json.loads(javascript(view, baseline_function + CHECKS))
                    assert result['success'], result
                    (output / (name + '-before-after.png')).write_bytes(base64.b64decode(result.pop('sheet').split(',', 1)[1]))
                    report['presentations'][name] = result
                finally:
                    view.close()
                    view.deleteLater()
                    qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            assert archive_members(book.to_bytes()) == original
            assert archive_members(snapshot_export(book)) == exported
            report['native_and_export_members_unchanged'] = True
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
            raise
        finally:
            (output / 'graphite-result.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', default='HEAD')
    arguments = parser.parse_args()
    main(arguments.output, arguments.baseline)
