"""Shared real-WebView page/zoom memory and raster checks for Apple and desktop."""
INSTALL = r'''(()=>{
window.memoryProbe={writes:0,done:true,error:null};
for(let name of ['width','height']){
  const property=Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype,name);
  Object.defineProperty(HTMLCanvasElement.prototype,name,{...property,set(value){
    if(this===canvas||this===draft||this===mask)memoryProbe.writes++;
    property.set.call(this,value);
  }});
}
memoryProbe.surface=()=>({width:canvas.width,height:canvas.height,limit:canvasPixelLimit,
  cssWidth:canvas.getBoundingClientRect().width,writes:memoryProbe.writes});
memoryProbe.zoom=value=>{
  if(!$('zoom').querySelector('option[value="'+value+'"]')){
    let option=document.createElement('option');option.value=value;option.textContent=value;$('zoom').append(option);
  }
  if(window.notebookUI)window.notebookUI('zoom',value);
  else{$('zoom').value=value;resize();$('viewport').scrollTop=$('viewport').scrollLeft=0}
  return memoryProbe.surface();
};
memoryProbe.stroke=(tool,width)=>{
  if(busy||active!==null)throw Error('Stroke started while busy');
  $('tool').value=String(tool);$('tool').onchange();
  $('width').value=String(width);
  $('color').value=$('color').options[Math.min(3,$('color').options.length-1)].value;
  let r=canvas.getBoundingClientRect(),v=$('viewport').getBoundingClientRect();
  let left=Math.max(r.left,v.left)+20,top=Math.max(r.top,v.top)+100;
  let span=Math.max(12,Math.min(120,Math.min(r.right,v.right)-left-20));
  const event=i=>({pointerId:60001,pointerType:'pen',nativePen:true,
    clientX:left+i*span/12,clientY:top+Math.sin(i/2)*15,
    pressure:.2+.6*i/12,preventDefault(){}});
  memoryProbe.done=false;memoryProbe.error=null;
  canvas.onpointerdown(event(0));
  let i=0;
  function frame(){
    try{
      canvas.onpointermove(event(++i));
      if(i<12)requestAnimationFrame(frame);
      else{canvas.onpointerup(event(i));memoryProbe.done=true}
    }catch(error){memoryProbe.error=String(error);memoryProbe.done=true}
  }
  requestAnimationFrame(frame);
  return true;
};
memoryProbe.raster=()=>{
  // Compare settled pixels before/after a zoom round trip using the same
  // native rendering backend. An offscreen software canvas has different
  // antialiasing from WebKit/Chromium's displayed accelerated surface.
  resize();draw();
  const actual=ctx.getImageData(0,0,canvas.width,canvas.height).data;
  const zoom=$('zoom').value,width=canvas.width,height=canvas.height;
  memoryProbe.rasterDone=false;memoryProbe.rasterError=null;
  const settled=callback=>requestAnimationFrame(()=>requestAnimationFrame(callback));
  memoryProbe.zoom(zoom==='1'?'fit':'1');
  settled(()=>{
    memoryProbe.zoom(zoom);
    settled(()=>{try{
  // Scrollbar changes affect Fit Page's available height on desktop; compare
  // after layout settles, as the production ResizeObserver does.
  resize();draw();
  if(width!==canvas.width||height!==canvas.height)throw Error('Zoom round trip changed resolution');
  let expected=ctx.getImageData(0,0,canvas.width,canvas.height).data,bad=0,ink=0;
  for(let i=0;i<actual.length;i+=4){
    if(actual[i+3]||expected[i+3]){
      ink++;
      if(Math.max(...[0,1,2,3].map(c=>Math.abs(actual[i+c]-expected[i+c])))>3)bad++;
    }
  }
  memoryProbe.rasterResult={inkPixels:ink,differentPixels:bad};
    }catch(error){memoryProbe.rasterError=String(error)}finally{memoryProbe.rasterDone=true}});
  });
  return true;
};
return memoryProbe.surface();
})()'''


def ink_signature(book):
    """Compare native-encoded dynamics, colors, layers, IDs and page order.

    Unsaved scenes receive a fresh author UUID on encoding; that transport
    metadata is not ink. Decode first so native pressure/width quantization is
    checked exactly without comparing unrelated generated author UUIDs.
    """
    from hashlib import sha256
    import json
    from features.notebooks.ink import InkPage
    result = []
    for i, page in enumerate(book.pages):
        ink = InkPage.read(book.page(i).to_bytes())
        value = dict(strokes=[stroke.payload() for stroke in ink.strokes], layers=ink.layers)
        result.append(dict(id=page.id, ink=sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()))
    return result


def recovery_history_stats(editor):
    """Count retained native ink across live pages and both history stacks."""
    from features.notebooks._vendor.rmscene.scene_stream import SceneLineItemBlock
    pages = list(editor.notebook.pages)
    for snapshot in [*editor.undo, *editor.redo]:
        pages.extend(snapshot[0])
    strokes, blocks = set(), set()
    for page in pages:
        if page.ink is None:
            continue
        strokes.update(id(stroke) for stroke in page.ink.strokes)
        blocks.update(id(block) for block in page.ink._blocks
                      if isinstance(block, SceneLineItemBlock) and not block.item.deleted_length)
    visible = sum(len(editor.notebook.page(i).strokes) for i in range(len(editor.notebook.pages)))
    return dict(visible_strokes=visible, retained_strokes=len(strokes), retained_native_blocks=len(blocks),
                undo_depth=len(editor.undo), redo_depth=len(editor.redo))
