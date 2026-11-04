// Native ink selection. Gesture previews are discarded before durable commands.
let selectionGesture = null, selectionPage = state.page_id ?? state.index;
const selectionActions = document.createElement('div');
selectionActions.id = 'selectionActions';
selectionActions.style.cssText = 'position:fixed;z-index:1;display:flex;gap:4px;padding:4px;border:1px solid var(--border);border-radius:8px;background:var(--surface,white);color:var(--text,black)';
selectionActions.innerHTML = '<button id="copyStrokes" type="button">Copy</button><button id="cutStrokes" type="button">Cut</button><button id="deleteStrokes" type="button">Delete</button>';
document.body.append(selectionActions);
const pasteStrokes = document.createElement('button');
pasteStrokes.id = 'pasteStrokes'; pasteStrokes.type = 'button'; pasteStrokes.textContent = 'Paste strokes';
pasteStrokes.style.cssText='position:fixed;right:12px;bottom:max(12px,env(safe-area-inset-bottom));z-index:1;min-height:44px';
document.body.append(pasteStrokes);
function selectionLocked() { return busy || state.warning || state.read_only || state.password_required }
function selectionVisible(s) { return state.layers.some(row => row[0] === s.layer && row[2]) }
// The lasso index is shared by every stroke in one selection. A boundary-free
// grid cell is an exact containment certificate, not a raster approximation.
function selectionPrepare(path) {
  if(!Array.isArray(path))return path;
  const edges=path.map((a,i)=>{const b=path[(i+1)%path.length];return {a,b,box:[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])]}});
  function tree(rows) {
    if(!rows.length)return null;
    const box=rows.reduce((v,e)=>[Math.min(v[0],e.box[0]),Math.min(v[1],e.box[1]),Math.max(v[2],e.box[2]),Math.max(v[3],e.box[3])],[Infinity,Infinity,-Infinity,-Infinity]);
    if(rows.length<=8)return {box,edges:rows};
    const axis=box[2]-box[0]>=box[3]-box[1]?0:1;
    rows.sort((a,b)=>a.box[axis]+a.box[axis+2]-b.box[axis]-b.box[axis+2]);
    const middle=rows.length>>1;return {box,left:tree(rows.slice(0,middle)),right:tree(rows.slice(middle))}
  }
  const root=tree(edges);
  return {path,root,box:root?.box||[0,0,0,0],cells:new Map(),work:0,edgeTests:0,limit:8_000_000,exhausted:false}
}
function selectionWork(index) {
  if(++index.work>index.limit)index.exhausted=true;
  return !index.exhausted
}
function selectionCandidates(index,box) {
  const rows=[],stack=index.root?[index.root]:[];
  while(stack.length&&!index.exhausted) {
    if(!selectionWork(index))break;
    const node=stack.pop(),b=node.box;
    if(b[0]>box[2]||b[2]<box[0]||b[1]>box[3]||b[3]<box[1])continue;
    if(node.edges)for(const edge of node.edges) {
      if(!selectionWork(index))break;
      const q=edge.box;
      if(q[0]<=box[2]&&q[2]>=box[0]&&q[1]<=box[3]&&q[3]>=box[1])rows.push(edge)
    } else stack.push(node.left,node.right)
  }
  return rows
}
function selectionInsideExact(p,index) {
  let inside=false;
  for(const {a,b} of selectionCandidates(index,[p[0]-1e-8,p[1]-1e-8,index.box[2]+1e-8,p[1]+1e-8])) {
    index.edgeTests++;
    if(distance(p,a,b)<1e-8)return true;
    if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])inside=!inside
  }
  return !index.exhausted&&inside
}
function selectionCell(index,box) {
  const [left,top,right,bottom]=index.box;
  if(box[0]<left||box[1]<top||box[2]>right||box[3]>bottom)return false;
  const dx=Math.max(1e-9,(right-left)/32),dy=Math.max(1e-9,(bottom-top)/32);
  const x=Math.min(31,Math.floor((box[0]-left)/dx)),y=Math.min(31,Math.floor((box[1]-top)/dy));
  if(x!==Math.min(31,Math.floor((box[2]-left)/dx))||y!==Math.min(31,Math.floor((box[3]-top)/dy)))return null;
  const key=y*32+x;
  if(!index.cells.has(key)) {
    const a=left+x*dx,b=top+y*dy,c=a+dx,d=b+dy;
    const boundary=selectionCandidates(index,[a-1e-8,b-1e-8,c+1e-8,d+1e-8]);
    index.cells.set(key,boundary.length?null:selectionInsideExact([(a+c)/2,(b+d)/2],index))
  }
  return index.cells.get(key)
}
function selectionInside(p,path) {
  const index=selectionPrepare(path),cell=selectionCell(index,[p[0],p[1],p[0],p[1]]);
  if(cell===false&&p[0]>=index.box[0]-1e-8&&p[0]<=index.box[2]+1e-8&&p[1]>=index.box[1]-1e-8&&p[1]<=index.box[3]+1e-8)return selectionInsideExact(p,index);
  return cell===null?selectionInsideExact(p,index):cell
}
function selectionCross(a,b,c,d) {
  const side=(p,q,r)=>(q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0]);
  return side(a,b,c)*side(a,b,d)<0&&side(c,d,a)*side(c,d,b)<0
}
function selectionContains(stroke,path) {
  const index=selectionPrepare(path);
  if(index.path.length<3||!stroke.points.length)return false;
  // Query only edges near each painted segment. Interior cell certificates
  // make dense, short segments independent of the lasso's edge count.
  for(let i=0;i<stroke.points.length;i++) {
    if(!selectionWork(index))return false;
    const b=stroke.points[i],a=stroke.points[Math.max(0,i-1)],radius=Math.max(a[3]||0,b[3]||0)/2;
    const box=[Math.min(a[0],b[0])-radius,Math.min(a[1],b[1])-radius,Math.max(a[0],b[0])+radius,Math.max(a[1],b[1])+radius];
    const cell=selectionCell(index,box);
    if(cell===false)return false;
    if(cell===true)continue;
    if(!selectionInside(b,index))return false;
    for(const {a:c,b:d} of selectionCandidates(index,box)) {
      index.edgeTests++;
      if(selectionCross(a,b,c,d)||Math.min(distance(a,c,d),distance(b,c,d),distance(c,a,b),distance(d,a,b))<radius-1e-8)return false
    }
    if(index.exhausted)return false
  }
  return true
}
function selectionBounds() {
  const rows=state.strokes.filter(s=>selected.has(s.id)&&selectionVisible(s));
  if(!rows.length)return null;
  return rows.flatMap(s=>s.points).reduce((b,p)=>[Math.min(b[0],p[0]-p[3]/2),Math.min(b[1],p[1]-p[3]/2),Math.max(b[2],p[0]+p[3]/2),Math.max(b[3],p[1]+p[3]/2)],[Infinity,Infinity,-Infinity,-Infinity])
}
function selectionUnit() { return state.width/canvas.getBoundingClientRect().width }
function selectionHandles(b) {
  const u=selectionUnit();
  return [[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]],[(b[0]+b[2])/2,Math.max(12*u,b[1]-28*u)]]
}
function selectionRender() {
  const page=state.page_id ?? state.index;
  if(selectionPage!==page) { selected.clear();selectionGesture=null;selectionPage=page }
  const shown=new Set(state.layers.filter(row=>row[2]).map(row=>row[0]));
  const visibleIds=new Set(state.strokes.filter(s=>shown.has(s.layer)).map(s=>s.id));
  selected=new Set([...selected].filter(id=>visibleIds.has(id)));
  const b=mode==='select'?selectionBounds():null;
  // Inline display wins over the hidden attribute in some WebViews.
  selectionActions.style.display=b&&!state.password_required?'flex':'none';
  pasteStrokes.hidden=mode!=='select'||!state.stroke_clipboard;pasteStrokes.disabled=!state.stroke_clipboard||!!selectionLocked();
  const bars=[$('zoomControls'),document.querySelector('footer')].filter(el=>el&&!el.hidden&&el.getClientRects?.().length);
  const floor=Math.min(innerHeight,...bars.map(el=>el.getBoundingClientRect().top));
  pasteStrokes.style.bottom=Math.max(12,innerHeight-floor+12)+'px';
  for(const id of ['copyStrokes','cutStrokes','deleteStrokes']) $(id).disabled=!!selectionLocked()||active!==null;
  if(!b)return;
  const r=canvas.getBoundingClientRect(),u=selectionUnit();
  const panel=selectionActions.getBoundingClientRect();
  selectionActions.style.left=Math.max(4,Math.min(innerWidth-panel.width-4,r.left+(b[0]+b[2])/2/u-panel.width/2))+'px';
  selectionActions.style.top=Math.max(4,Math.min(floor-panel.height-8,r.top+b[3]/u+12))+'px'
  if(!pasteStrokes.hidden) {
    const a=selectionActions.getBoundingClientRect(),p=pasteStrokes.getBoundingClientRect();
    if(a.left<p.right&&p.left<a.right&&a.top<p.bottom&&p.top<a.bottom)
      pasteStrokes.style.bottom=Math.max(12,innerHeight-a.top+8)+'px'
  }
}
function paintSelection() {
  selectionRender();if(mode!=='select')return;
  const u=selectionUnit();ctx.save();ctx.strokeStyle='#2877cb';ctx.fillStyle='white';ctx.lineWidth=1.5*u;ctx.setLineDash([6*u,5*u]);
  if(selectionGesture?.kind==='lasso'&&points.length) {
    ctx.beginPath();ctx.moveTo(points[0][0],points[0][1]);for(const p of points.slice(1))ctx.lineTo(p[0],p[1]);ctx.stroke()
  } else {
    const b=selectionBounds();if(b) {
      ctx.strokeRect(b[0],b[1],b[2]-b[0],b[3]-b[1]);ctx.setLineDash([]);
      const handles=selectionHandles(b);
      ctx.beginPath();ctx.moveTo(handles[4][0],b[1]);ctx.lineTo(...handles[4]);ctx.stroke();
      handles.forEach((p,i)=>{ctx.beginPath();if(i===4)ctx.arc(p[0],p[1],6*u,0,Math.PI*2);else ctx.rect(p[0]-5*u,p[1]-5*u,10*u,10*u);ctx.fill();ctx.stroke()})
    }
  }
  ctx.restore()
}
function selectionCommand(op) {
  if(selectionLocked()||active!==null||!selected.size)return;
  send({op,ids:[...selected]});if(op!=='copy-strokes')selected.clear();draw()
}
$('copyStrokes').onclick=()=>selectionCommand('copy-strokes');
$('cutStrokes').onclick=()=>selectionCommand('cut-strokes');
$('deleteStrokes').onclick=()=>selectionCommand('erase');
pasteStrokes.onclick=()=>{if(!selectionLocked()&&active===null&&state.stroke_clipboard)send({op:'paste-strokes'})};
function selectionDown(e) {
  e.preventDefault();
  if(selectionLocked()||(e.pointerType==='touch'&&penTouchBlocked())||(state.native_pen&&e.pointerType==='pen'&&e.isTrusted&&!e.nativePen))return;
  if(e.pointerType==='pen'&&touchContacts.has(active))cancelTouchZoom();
  if(active!==null)return;
  if(e.pointerType==='pen') {notePenContact(true);pan=null;cancelTouchZoom()}
  const q=coord(e),b=selectionBounds(),u=selectionUnit(),handles=b?selectionHandles(b):[];
  const h=handles.findIndex(p=>Math.hypot(p[0]-q[0],p[1]-q[1])<=14*u);
  let kind=h===4?'rotate':h>=0?'scale':b&&q[0]>=b[0]&&q[0]<=b[2]&&q[1]>=b[1]&&q[1]<=b[3]?'move':'lasso';
  start=last=q;points=[q];
  selectionGesture={kind,rows:state.strokes.filter(s=>selected.has(s.id)),cx:b?(b[0]+b[2])/2:0,cy:b?(b[1]+b[3])/2:0,dx:0,dy:0,scale:1,angle:0,lastAngle:0};
  if(kind==='lasso')selected.clear();
  active=e.pointerId;canvas.style.touchAction='none';if(!e.nativePen)canvas.setPointerCapture(active);draw()
}
function selectionMove(e) {
  if(e.pointerId!==active||!selectionGesture)return;
  e.preventDefault();last=coord(e);const g=selectionGesture;
  if(g.kind==='lasso') {
    const samples=e.getCoalescedEvents?e.getCoalescedEvents():[];
    for(const ev of [...samples,e]) {const p=coord(ev),prev=points.at(-1);if(Math.hypot(p[0]-prev[0],p[1]-prev[1])>=2*selectionUnit()){if(points.length<2048)points.push(p);else g.overflow=true}}
  } else {
    const r=canvas.getBoundingClientRect();last=[(e.clientX-r.left)/r.width*state.width,(e.clientY-r.top)/r.height*state.height,.5];
    if(g.kind==='move') {g.dx=last[0]-start[0];g.dy=last[1]-start[1]}
    if(g.kind==='scale')g.scale=Math.max(.05,Math.min(20,Math.hypot(last[0]-g.cx,last[1]-g.cy)/Math.max(1e-6,Math.hypot(start[0]-g.cx,start[1]-g.cy))));
    if(g.kind==='rotate') {
      // Angular motion naturally gets finer as the pointer moves farther from
      // the centre. Integrate wrapped deltas to avoid a jump across +/- pi.
      const angle=Math.atan2(last[1]-g.cy,last[0]-g.cx)-Math.atan2(start[1]-g.cy,start[0]-g.cx);
      let delta=angle-g.lastAngle;delta=Math.atan2(Math.sin(delta),Math.cos(delta));g.angle+=delta;g.lastAngle=angle
    }
    const c=Math.cos(g.angle),s=Math.sin(g.angle),rows=new Map(g.rows.map(row=>[row.id,{...row,points:row.points.map(p=>{const x=(p[0]-g.cx)*g.scale,y=(p[1]-g.cy)*g.scale;return [g.cx+x*c-y*s+g.dx,g.cy+x*s+y*c+g.dy,p[2],p[3]*g.scale]})}]));
    state.strokes=state.strokes.map(row=>rows.get(row.id)||row)
  }
  draw()
}
function selectionFinish(e,cancelled=false) {
  if(e.pointerId!==active||!selectionGesture)return;
  if(!cancelled)selectionMove(e);
  const g=selectionGesture,path=points;active=null;points=[];selectionGesture=null;
  if(e.pointerType==='pen'||penContactActive)notePenContact(false);
  if(g.kind==='lasso') {
    if(!cancelled&&!g.overflow) {
      const index=selectionPrepare(path),ids=[];
      for(const stroke of state.strokes) {
        if(index.exhausted)break;
        if(selectionVisible(stroke)&&selectionContains(stroke,index))ids.push(stroke.id)
      }
      selected=new Set(index.exhausted?[]:ids);
      if(index.exhausted)$('status').textContent='Selection too complex. Draw a smaller outline.'
    }
    if(g.overflow)$('status').textContent='Lasso too long. Draw a shorter outline.'
  }
  else {
    const originals=new Map(g.rows.map(s=>[s.id,s]));state.strokes=state.strokes.map(s=>originals.get(s.id)||s);
    if(!cancelled&&(g.dx||g.dy||g.angle||g.scale!==1))send({op:'transform',ids:[...selected],dx:g.dx,dy:g.dy,scale:g.scale,angle:g.angle,cx:g.cx,cy:g.cy})
  }
  draw();flushUpdate()
}
const selectionOldDown=canvas.onpointerdown,selectionOldMove=canvas.onpointermove,selectionOldUp=canvas.onpointerup,selectionOldCancel=canvas.onpointercancel;
canvas.onpointerdown=e=>mode==='select'?selectionDown(e):selectionOldDown(e);
canvas.onpointermove=e=>mode==='select'?selectionMove(e):selectionOldMove(e);
canvas.onpointerup=e=>mode==='select'?selectionFinish(e):selectionOldUp(e);
canvas.onpointercancel=e=>mode==='select'?selectionFinish(e,true):selectionOldCancel(e);
canvas.onlostpointercapture=canvas.onpointercancel;
const selectionUpdate=window.notebookUpdate;
window.notebookUpdate=(next,error)=>{
  const operation=queue[0]?.op;
  selectionUpdate(next,error);
  if(!error && ['paste-strokes','transform','copy-strokes','undo','redo','page'].includes(operation)) {selected=new Set(next.selection_ids||[]);draw()}
};
$('viewport').addEventListener('scroll',selectionRender,{passive:true});
window.addEventListener('resize',selectionRender);
for(const id of ['select','erase','tool','capture']) $(id).addEventListener(id==='tool'?'change':'click',selectionRender);
document.addEventListener('keydown',e=>{
  if(document.querySelector('dialog[open],#mobileSheet:not([hidden])'))return;
  if(mode==='select'&&selectionGesture&&e.key==='Escape') {
    e.preventDefault();e.stopImmediatePropagation();selectionFinish({pointerId:active,nativePen:true},true);return
  }
  if(mode!=='select'||/INPUT|SELECT|TEXTAREA/.test(e.target.tagName)||active!==null||selectionLocked())return;
  if(e.key==='Escape'){selected.clear();draw();return}
  if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();selectionCommand('erase')}
  if(e.ctrlKey||e.metaKey) {const op={c:'copy-strokes',x:'cut-strokes'}[e.key.toLowerCase()];if(op){e.preventDefault();selectionCommand(op)}else if(e.key.toLowerCase()==='v'){e.preventDefault();pasteStrokes.onclick()}}
});
