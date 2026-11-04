// Native ink selection. Gesture previews are discarded before durable commands.
let selectionGesture = null, selectionPage = state.page_id ?? state.index;
const selectionActions = document.createElement('div');
selectionActions.id = 'selectionActions';
selectionActions.style.cssText = 'position:fixed;z-index:50;display:flex;gap:4px;padding:4px;border:1px solid var(--border);border-radius:8px;background:var(--surface,white);color:var(--text,black)';
selectionActions.innerHTML = '<button id="copyStrokes" type="button">Copy</button><button id="cutStrokes" type="button">Cut</button><button id="deleteStrokes" type="button">Delete</button>';
document.body.append(selectionActions);
const pasteStrokes = document.createElement('button');
pasteStrokes.id = 'pasteStrokes'; pasteStrokes.type = 'button'; pasteStrokes.textContent = 'Paste strokes';
pasteStrokes.style.cssText='position:fixed;right:12px;bottom:max(12px,env(safe-area-inset-bottom));z-index:40;min-height:44px';
document.body.append(pasteStrokes);
function selectionLocked() { return busy || state.warning || state.read_only || state.password_required }
function selectionVisible(s) { return state.layers.some(row => row[0] === s.layer && row[2]) }
function selectionInside(p, path) {
  let inside = false;
  for (let i=0,j=path.length-1;i<path.length;j=i++) {
    const a=path[i],b=path[j];
    if (distance(p,a,b)<1e-8) return true;
    if ((a[1]>p[1]) !== (b[1]>p[1]) && p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]) inside=!inside
  }
  return inside
}
function selectionCross(a,b,c,d) {
  const side=(p,q,r)=>(q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0]);
  return side(a,b,c)*side(a,b,d)<0 && side(c,d,a)*side(c,d,b)<0
}
function selectionContains(stroke, path) {
  if (path.length<3 || !stroke.points.length) return false;
  const box=path.reduce((b,p)=>[Math.min(b[0],p[0]),Math.min(b[1],p[1]),Math.max(b[2],p[0]),Math.max(b[3],p[1])],[Infinity,Infinity,-Infinity,-Infinity]);
  if(stroke.points.some(p=>p[0]-p[3]/2<box[0]||p[1]-p[3]/2<box[1]||p[0]+p[3]/2>box[2]||p[1]+p[3]/2>box[3]))return false;
  // Check the complete painted segments, including diameter. Endpoints alone
  // would incorrectly include strokes spanning the mouth of a concave lasso.
  for(let i=0;i<stroke.points.length;i++) {
    const b=stroke.points[i],a=stroke.points[Math.max(0,i-1)],radius=Math.max(a[3]||0,b[3]||0)/2;
    if(!selectionInside(b,path))return false;
    for(let j=0;j<path.length;j++) {
      const c=path[j],d=path[(j+1)%path.length];
      if(selectionCross(a,b,c,d) || Math.min(distance(a,c,d),distance(b,c,d),distance(c,a,b),distance(d,a,b))<radius-1e-8)return false
    }
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
  selected=new Set([...selected].filter(id=>state.strokes.some(s=>s.id===id&&selectionVisible(s))));
  const b=mode==='select'?selectionBounds():null;
  // Inline display wins over the hidden attribute in some WebViews.
  selectionActions.style.display=b&&!state.password_required?'flex':'none';
  pasteStrokes.hidden=mode!=='select';pasteStrokes.disabled=!state.stroke_clipboard||!!selectionLocked();
  for(const id of ['copyStrokes','cutStrokes','deleteStrokes']) $(id).disabled=!!selectionLocked()||active!==null;
  if(!b)return;
  const r=canvas.getBoundingClientRect(),u=selectionUnit();
  selectionActions.style.left=Math.max(4,Math.min(innerWidth-220,r.left+(b[0]+b[2])/2/u-100))+'px';
  selectionActions.style.top=Math.max(4,Math.min(innerHeight-52,r.top+b[3]/u+12))+'px'
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
    if(g.kind==='scale')g.scale=Math.max(.05,Math.min(20,Math.hypot(last[0]-g.cx,last[1]-g.cy)/Math.max(1,Math.hypot(start[0]-g.cx,start[1]-g.cy))));
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
  if(g.kind==='lasso') {if(!cancelled&&!g.overflow)selected=new Set(state.strokes.filter(s=>selectionVisible(s)&&selectionContains(s,path)).map(s=>s.id));if(g.overflow)$('status').textContent='Lasso too long. Draw a shorter outline.'}
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
  if(mode==='select'&&selectionGesture&&e.key==='Escape') {
    e.preventDefault();e.stopImmediatePropagation();selectionFinish({pointerId:active,nativePen:true},true);return
  }
  if(mode!=='select'||/INPUT|SELECT|TEXTAREA/.test(e.target.tagName)||active!==null||selectionLocked())return;
  if(e.key==='Escape'){selected.clear();draw();return}
  if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();selectionCommand('erase')}
  if(e.ctrlKey||e.metaKey) {const op={c:'copy-strokes',x:'cut-strokes'}[e.key.toLowerCase()];if(op){e.preventDefault();selectionCommand(op)}else if(e.key.toLowerCase()==='v'){e.preventDefault();pasteStrokes.onclick()}}
});
