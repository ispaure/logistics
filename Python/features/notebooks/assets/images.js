// Capture uses a private editor clipboard, retained across page changes. PNGs
// and native image quads travel through the same durable command queue as ink.
let imageClipboard = null, imageSelection = null, imageGesture = null, forceImageLasso = false;
const imageCache = new Map();
const captureTools = document.createElement('div');
captureTools.className = 'capture-tools';
captureTools.innerHTML = '<button id="newCutout" type="button">New cutout</button><button id="pasteImage" type="button">Paste</button><label class="image-import">Add image<input id="imageFile" type="file" accept="image/png,image/jpeg" hidden></label><span id="imageActions" hidden><button id="copyImage" type="button">Copy</button><button id="cutImage" type="button">Cut</button><button id="imageSmaller" type="button" aria-label="Scale image down">− Size</button><button id="imageLarger" type="button" aria-label="Scale image up">+ Size</button><button id="imageRotate" type="button">Rotate 15°</button><select id="imageArrange" aria-label="Arrange selected image"><option value="">Arrange…</option><option value="forward">Bring forward</option><option value="backward">Send backward</option><option value="front">Bring to front</option><option value="back">Send to back</option></select><button id="deleteImage" type="button">Delete image</button></span>';
const captureToggle = document.createElement('button');
captureToggle.id = 'capture'; captureToggle.type = 'button'; captureToggle.textContent = 'Capture';
captureToggle.setAttribute('aria-label', 'Capture cutouts and arrange images');
captureToggle.setAttribute('aria-pressed', 'false');
document.querySelector('header').append(captureToggle);
document.body.append(captureTools);
const pdfUnlock = document.createElement('form');
pdfUnlock.id = 'pdfUnlock';
pdfUnlock.innerHTML = '<label>PDF password <input id="pdfPassword" type="password" autocomplete="off" maxlength="1024" required></label><button type="submit">Unlock PDF</button>';
document.body.insertBefore(pdfUnlock, $('viewport'));
pdfUnlock.onsubmit = e => {
  e.preventDefault();
  if (!busy) { const password = $('pdfPassword').value; $('pdfPassword').value = ''; send({op:'unlock-pdf', password}) }
};
function imagePageIdentity() { return state.page_id || 'index:' + state.index }
function imageVisible(p) { return state.layers.some(row => row[0] === p.layer && row[2]) }
function selectedPicture() { return (state.images || []).find(p => p.id === imageSelection && imageVisible(p)) }
function imageRender() {
  captureTools.hidden = mode !== 'capture' || !!state.password_required;
  pdfUnlock.hidden = !state.password_required;
  $('viewport').style.visibility = state.password_required ? 'hidden' : '';
  if (imageRender.page !== state.index) { imageSelection = null; imageGesture = null; imageRender.page = state.index }
  const pictures = state.images || [], sources = new Set(pictures.map(p => p.src));
  for (const key of imageCache.keys()) if (!sources.has(key)) imageCache.delete(key);
  for (const p of pictures) if (!imageCache.has(p.src)) {
    const img = new Image(); imageCache.set(p.src, img);
    img.onload = () => { if (imageCache.get(p.src) === img && active === null) draw() };
    img.onerror = () => $('status').textContent = 'Unable to decode a notebook image.';
    img.src = p.src
  }
  $('capture').classList.toggle('active', mode === 'capture');
  $('capture').setAttribute('aria-pressed', String(mode === 'capture'));
  $('pasteImage').disabled = !imageClipboard || busy || state.read_only || !!state.warning || state.password_required;
  $('imageActions').hidden = !selectedPicture() || mode !== 'capture';
}
function paintPicture(p, target = ctx, outline = true) {
  const img = imageCache.get(p.src), [a,b,,d] = p.corners;
  if (!img || !img.complete || !img.naturalWidth) return;
  target.save();
  target.transform(b[0]-a[0], b[1]-a[1], d[0]-a[0], d[1]-a[1], a[0], a[1]);
  target.drawImage(img, 0, 0, 1, 1);
  target.restore();
  if (outline && p.id === imageSelection && mode === 'capture') {
    target.save(); target.strokeStyle = '#2877cb'; target.fillStyle = 'white'; target.lineWidth = 3;
    target.beginPath(); target.moveTo(...a); for (const q of p.corners.slice(1)) target.lineTo(...q); target.closePath(); target.stroke();
    for (const q of imageHandles(p)) { target.beginPath(); target.arc(q[0],q[1],8*state.width/canvas.getBoundingClientRect().width,0,Math.PI*2); target.fill(); target.stroke() }
    target.restore()
  }
}
function imageHandles(p) {
  const [a,b,c,d] = p.corners, mid = [(a[0]+b[0])/2,(a[1]+b[1])/2], length = Math.hypot(d[0]-a[0],d[1]-a[1]) || 1;
  const offset = 36*state.width/canvas.getBoundingClientRect().width;
  return [c, [mid[0] - (d[0]-a[0])/length*offset, mid[1] - (d[1]-a[1])/length*offset]]
}
function sceneItems() {
  const rows = [...state.strokes, ...(state.images || [])], map = new Map(rows.map(p => [p.id,p]));
  const order = state.scene_order || [], known = new Set(order);
  // Layers always retain their own stacking; Arrange only affects one layer.
  return state.layers.flatMap(layer => [...order.map(id => map.get(id)).filter(Boolean), ...rows.filter(p => !known.has(p.id))].filter(p => p.layer === layer[0]))
}
function imageContains(p, q) {
  const [a,b,,d] = p.corners, ux=b[0]-a[0],uy=b[1]-a[1],vx=d[0]-a[0],vy=d[1]-a[1],det=ux*vy-uy*vx;
  if (!det) return false;
  const x=q[0]-a[0],y=q[1]-a[1],u=(x*vy-y*vx)/det,v=(ux*y-uy*x)/det;
  return u>=0 && u<=1 && v>=0 && v<=1
}
function changeImage(scale = 1, angle = 0) {
  const p = selectedPicture(); if (!p || busy) return;
  const center = p.corners.reduce((a,q) => [a[0]+q[0]/4,a[1]+q[1]/4],[0,0]);
  send({op:'image-transform', id:p.id, corners:p.corners.map(q => {
    const x=(q[0]-center[0])*scale,y=(q[1]-center[1])*scale;
    return [center[0]+x*Math.cos(angle)-y*Math.sin(angle),center[1]+x*Math.sin(angle)+y*Math.cos(angle)]
  })})
}
$('capture').onclick = () => {
  if (active !== null || busy) return;
  mode = mode === 'capture' ? 'ink' : 'capture'; selected.clear(); imageSelection=null;
  $('erase').classList.remove('active'); $('select').classList.remove('active');
  if (typeof syncChrome === 'function') syncChrome(); imageRender(); draw();
  $('status').textContent = mode === 'capture' ? 'Lasso to copy a cutout. Tap an image to move it; drag its corner to scale or upper handle to rotate.' : state.save_status
};
$('newCutout').onclick = () => { if(active!==null || busy) return; forceImageLasso=true; imageSelection=null; draw(); $('status').textContent='Lasso any area, including inside an image, to copy a new cutout.' };
$('pasteImage').onclick = () => {
  if (!imageClipboard || busy || state.read_only || state.warning || state.password_required) return;
  mode='capture'; imageSelection=null;
  const {src, width, height} = imageClipboard, x=(state.width-width)/2, y=Math.max(0,(Math.min(state.height,1872)-height)/2);
  const crossPage = imageClipboard.sourcePageId && imageClipboard.sourcePageId !== imagePageIdentity();
  const corners = crossPage && imageClipboard.sourceCorners ? imageClipboard.sourceCorners.map(p => [...p]) : imageClipboard.offsets ? imageClipboard.offsets.map(p => [state.width/2+p[0],Math.min(state.height,1872)/2+p[1]]) : [[x,y],[x+width,y],[x+width,y+height],[x,y+height]];
  send({op:'paste-image', src, corners, layer:$('layer').value})
};
$('copyImage').onclick = () => {
  const p=selectedPicture(); if (!p) return;
  const center=p.corners.reduce((a,q)=>[a[0]+q[0]/4,a[1]+q[1]/4],[0,0]);
  imageClipboard={src:p.src,sourcePageId:imagePageIdentity(),sourceCorners:p.corners.map(q=>[...q]),offsets:p.corners.map(q=>[q[0]-center[0],q[1]-center[1]]),width:Math.hypot(p.corners[1][0]-p.corners[0][0],p.corners[1][1]-p.corners[0][1]),height:Math.hypot(p.corners[3][0]-p.corners[0][0],p.corners[3][1]-p.corners[0][1])}; imageRender()
};
$('cutImage').onclick = () => {
  const p=selectedPicture();
  if(!p || busy || state.read_only || state.warning) return;
  $('copyImage').onclick();
  send({op:'delete-image',id:p.id})
};
$('imageSmaller').onclick = () => changeImage(.9);
$('imageLarger').onclick = () => changeImage(1.1);
$('imageRotate').onclick = () => changeImage(1,Math.PI/12);
$('imageArrange').onchange = () => { const p=selectedPicture(), direction=$('imageArrange').value; if(p && direction && !busy) send({op:'arrange-image',id:p.id,direction}); $('imageArrange').value='' };
$('deleteImage').onclick = () => { const p=selectedPicture(); if(p && !busy) send({op:'delete-image',id:p.id}) };
function boundedPNG(surface) {
  let src = surface.toDataURL('image/png');
  while(src.length > 3*1024*1024 && surface.width > 32 && surface.height > 32) {
    const smaller=document.createElement('canvas'); smaller.width=Math.floor(surface.width*.75); smaller.height=Math.floor(surface.height*.75); smaller.getContext('2d').drawImage(surface,0,0,smaller.width,smaller.height); surface=smaller; src=surface.toDataURL('image/png')
  }
  return src
}
$('imageFile').onchange = async () => {
  const file=$('imageFile').files[0]; $('imageFile').value=''; if(!file || busy || state.read_only) return;
  try {
    if(file.size>12*1024*1024) throw Error('Choose an image smaller than 12 MiB.');
    const src=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file)});
    const img=new Image(); img.src=src; await img.decode();
    const ratio=Math.min(1, Math.sqrt(4*1024*1024/(img.width*img.height)),1000/img.width,1400/img.height);
    const surface=document.createElement('canvas'); surface.width=Math.max(1,Math.round(img.width*ratio));surface.height=Math.max(1,Math.round(img.height*ratio));surface.getContext('2d').drawImage(img,0,0,surface.width,surface.height);
    imageClipboard={src:boundedPNG(surface),width:surface.width,height:surface.height}; $('pasteImage').onclick()
  } catch(error) { $('status').textContent=error.message || 'Unable to open image.' }
};
function captureCutout(path) {
  if(path.length<3) return;
  const left=Math.max(0,Math.floor(Math.min(...path.map(p=>p[0])))),top=Math.max(0,Math.floor(Math.min(...path.map(p=>p[1]))));
  const width=Math.min(state.width,Math.ceil(Math.max(...path.map(p=>p[0]))))-left,height=Math.min(state.height,Math.ceil(Math.max(...path.map(p=>p[1]))))-top;
  if(width<2 || height<2) return;
  if((state.images||[]).some(p=>imageVisible(p) && !imageCache.get(p.src)?.complete)) { $('status').textContent='Wait for images to load before capturing.'; return }
  const surface=document.createElement('canvas'),ratio=Math.min(1,Math.sqrt(4*1024*1024/(width*height)));
  surface.width=Math.max(1,Math.ceil(width*ratio)); surface.height=Math.max(1,Math.ceil(height*ratio));
  const g=surface.getContext('2d');g.scale(ratio,ratio);g.translate(-left,-top);g.beginPath();g.moveTo(...path[0].slice(0,2));for(const p of path.slice(1))g.lineTo(p[0],p[1]);g.closePath();g.clip();g.fillStyle='white';g.fillRect(left,top,width,height);
  const bg=$('pdfBackground'); if(state.background) { if(!bg.complete || !bg.naturalWidth) { $('status').textContent='Wait for the background to load before capturing.'; return } const b=state.pdf_paper || {x:0,y:0,width:state.width,height:state.height};g.drawImage(bg,b.x,b.y,b.width,b.height) }
  const selection=imageSelection; imageSelection=null;const previous=selected;selected=new Set();
  try { for(const p of sceneItems()) if(imageVisible(p)) { if(p.corners) paintPicture(p,g,false);else line(p,g) } } finally { imageSelection=selection;selected=previous }
  imageClipboard={src:boundedPNG(surface),width,height,sourcePageId:imagePageIdentity(),sourceCorners:[[left,top],[left+width,top],[left+width,top+height],[left,top+height]]}; imageRender(); $('status').textContent='Cutout copied. Paste on this page or another page.'
}
const imageDown=canvas.onpointerdown,imageMove=canvas.onpointermove,imageUp=canvas.onpointerup,imageCancel=canvas.onpointercancel;
canvas.onpointerdown = e => {
  if(mode!=='capture') return imageDown(e);
  e.preventDefault(); if(active!==null || busy || state.warning || state.read_only || state.password_required || (e.pointerType==='touch' && penTouchBlocked()) || (e.pointerType==='pen' && state.native_pen && e.isTrusted && !e.nativePen)) return;
  const q=coord(e),current=selectedPicture(),radius=16*state.width/canvas.getBoundingClientRect().width;
  let kind='move',hit=null;
  if(current && !forceImageLasso) { const handles=imageHandles(current);const i=handles.findIndex(p=>Math.hypot(p[0]-q[0],p[1]-q[1])<radius);if(i>=0) { hit=current;kind=i===0?'scale':'rotate' } }
  hit=hit || (!forceImageLasso && [...sceneItems()].reverse().find(p=>p.corners && imageVisible(p) && imageContains(p,q)));
  imageSelection=hit?.id || null;active=e.pointerId; start=last=q;points=[q];
  if(e.pointerType==='pen')notePenContact(true);
  if(!e.nativePen)canvas.setPointerCapture(active);
  imageGesture=hit?{kind,original:hit,corners:hit.corners.map(p=>[...p])}:null;imageRender();draw()
};
canvas.onpointermove = e => {
  if(mode!=='capture')return imageMove(e);
  if(e.pointerId!==active)return;e.preventDefault();last=coord(e);
  if(imageGesture) {
    const {original,corners,kind}=imageGesture,center=corners.reduce((a,p)=>[a[0]+p[0]/4,a[1]+p[1]/4],[0,0]);
    let transformed;
    if(kind==='move') transformed=corners.map(p=>[p[0]+last[0]-start[0],p[1]+last[1]-start[1]]);
    else {const angle=kind==='rotate'?Math.atan2(last[1]-center[1],last[0]-center[0])-Math.atan2(start[1]-center[1],start[0]-center[0]):0,scale=kind==='scale'?Math.max(.05,Math.min(20,Math.hypot(last[0]-center[0],last[1]-center[1])/Math.max(1,Math.hypot(start[0]-center[0],start[1]-center[1])))):1;transformed=corners.map(p=>{const x=(p[0]-center[0])*scale,y=(p[1]-center[1])*scale;return [center[0]+x*Math.cos(angle)-y*Math.sin(angle),center[1]+x*Math.sin(angle)+y*Math.cos(angle)]})}
    state.images=state.images.map(p=>p.id===original.id?{...p,corners:transformed}:p)
  } else if(points.length<10000) points.push(last);
  draw()
};
function finishImage(e,cancelled=false) {
  if(mode!=='capture')return cancelled?imageCancel(e):imageUp(e);
  if(e.pointerId!==active)return;
  if(!cancelled)canvas.onpointermove(e);
  const gesture=imageGesture,path=points,p=selectedPicture();active=null;points=[];imageGesture=null;forceImageLasso=false;
  if(e.pointerType==='pen')notePenContact(false);
  if(gesture) {
    const corners=p?.corners;state.images=state.images.map(p=>p.id===gesture.original.id?gesture.original:p);
    if(!cancelled && corners && JSON.stringify(corners)!==JSON.stringify(gesture.corners))send({op:'image-transform',id:p.id,corners})
  } else if(!cancelled)captureCutout(path);
  draw();flushUpdate()
}
canvas.onpointerup=e=>finishImage(e);
canvas.onpointercancel=e=>finishImage(e,true);
canvas.onlostpointercapture=e=>finishImage(e,true);
document.addEventListener('keydown',e=>{
  if(mode!=='capture') return;
  if(/INPUT|SELECT|TEXTAREA/.test(e.target.tagName) || active!==null || busy)return;
  if((e.ctrlKey||e.metaKey) && e.key.toLowerCase()==='v' && imageClipboard) { e.preventDefault();$('pasteImage').onclick() }
  if((e.ctrlKey||e.metaKey) && e.key.toLowerCase()==='c' && selectedPicture()) {e.preventDefault();$('copyImage').onclick()}
});

for (const id of ['erase', 'select', 'tool']) $(id).addEventListener(id === 'tool' ? 'change' : 'click', imageRender);
