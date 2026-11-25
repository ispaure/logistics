// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

// The host keeps one cutout for the app. Geometry for same-document paste
// stays in the canvas, while receiving documents get only the cutout size.
let imageClipboard = null, imageSelection = null, imageGesture = null, forceImageLasso = false, cutoutArmed = false;
const imageCache = new Map();
let cutoutPending = false;
const captureTools = document.createElement('div');
captureTools.className = 'capture-tools';
captureTools.innerHTML = '<button id="newCutout" type="button">New cutout</button><button id="pasteImage" type="button">Paste</button><button id="clearCutout" type="button" hidden>Clear clipboard</button><label class="image-import">Add image<input id="imageFile" type="file" accept="image/png,image/jpeg" hidden></label><span id="imageActions" hidden><button id="copyImage" type="button">Copy</button><button id="cutImage" type="button">Cut</button><button id="imageSmaller" type="button" aria-label="Scale image down">− Size</button><button id="imageLarger" type="button" aria-label="Scale image up">+ Size</button><button id="imageRotate" type="button">Rotate 15°</button><select id="imageArrange" aria-label="Arrange selected image"><option value="">Arrange…</option><option value="forward">Bring forward</option><option value="backward">Send backward</option><option value="front">Bring to front</option><option value="back">Send to back</option></select><button id="deleteImage" type="button">Delete image</button></span>';
const captureToggle = document.createElement('button');
captureToggle.id = 'capture'; captureToggle.type = 'button'; captureToggle.textContent = 'Capture';
captureToggle.setAttribute('aria-label', 'Capture cutouts and arrange images');
captureToggle.setAttribute('aria-pressed', 'false');
document.querySelector('header').append(captureToggle);
document.body.append(captureTools);
const pdfUnlock = document.createElement('form');
pdfUnlock.id = 'pdfUnlock';
pdfUnlock.innerHTML = '<label>PDF password <input id="pdfPassword" type="password" autocomplete="off" maxlength="1024" required></label><button id="unlockPDF" type="submit">Unlock PDF</button><span id="pdfUnlockStatus" role="status"></span>';
document.body.insertBefore(pdfUnlock, $('viewport'));
pdfUnlock.onsubmit = e => {
  e.preventDefault();
  if (busy) return;
  const password = $('pdfPassword').value;
  $('pdfPassword').value = '';
  $('unlockPDF').disabled = true;
  $('pdfUnlockStatus').textContent = 'Unlocking notebook…';
  send({op:'unlock-pdf', password});
};
function imagePageIdentity() { return state.page_id || 'index:' + state.index }
function imageVisible(p) { return state.layers.some(row => row[0] === p.layer && row[2]) }
function selectedPicture() { return (state.images || []).find(p => p.id === imageSelection && imageVisible(p)) }
function imageRender() {
  captureTools.hidden = mode !== 'capture' || !!state.password_required;
  pdfUnlock.hidden = !state.password_required;
  $('unlockPDF').disabled = busy;
  $('viewport').style.visibility = state.password_required ? 'hidden' : '';
  const page = imagePageIdentity();
  if (imageRender.page !== page) {
    imageSelection = null;
    imageGesture = null;
    forceImageLasso = false;
    imageRender.page = page;
  }
  const pictures = state.images || [];
  if (state.image_sources) {
    for (const picture of pictures) picture.src = state.image_sources[picture.src];
    delete state.image_sources;
  }
  const sources = new Set(state.password_required ? [] : pictures.filter(imageVisible).map(picture => picture.src));
  for (const [src, img] of imageCache) {
    if (sources.has(src)) continue;
    imageCache.delete(src);
    img.onload = img.onerror = null;
    img.removeAttribute('src');
  }
  for (const src of sources) {
    if (imageCache.has(src)) continue;
    const img = new Image();
    imageCache.set(src, img);
    img.onload = () => { if (imageCache.get(src) === img && active === null) draw() };
    img.onerror = () => {
      if (imageCache.get(src) === img) $('status').textContent = 'Unable to decode a notebook image.';
    };
    img.src = src;
  }
  $('capture').classList.toggle('active', mode === 'capture');
  $('capture').setAttribute('aria-pressed', String(mode === 'capture'));
  $('pasteImage').disabled = !state.cutout_clipboard || cutoutPending || busy || state.read_only || !!state.warning || state.password_required;
  $('clearCutout').hidden = !state.cutout_clipboard;
  $('imageActions').hidden = !selectedPicture() || mode !== 'capture';
}
function paintPicture(p, target = ctx, outline = true, img = imageCache.get(p.src)) {
  const [a,b,,d] = p.corners;
  if (!img || !img.complete || !img.naturalWidth) return;
  target.save();
  target.transform(b[0]-a[0], b[1]-a[1], d[0]-a[0], d[1]-a[1], a[0], a[1]);
  target.drawImage(img, 0, 0, 1, 1);
  target.restore();
  if (outline && p.id === imageSelection && mode === 'capture') {
    target.save(); target.strokeStyle = '#2877cb'; target.fillStyle = 'white'; target.lineWidth = 3;
    window.clipNotebookControls?.(target);
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
function sceneItems(strokes = state.strokes, pictures = state.images || []) {
  const rows = [...strokes, ...pictures, ...(state.text_highlights || [])];
  const remaining = new Map(rows.map(item => [item.id, item]));
  const layers = new Map(state.layers.map(([id]) => [id, []]));
  for (const id of state.scene_order || []) {
    const item = remaining.get(id);
    if (item) layers.get(item.layer)?.push(item);
    remaining.delete(id);
  }
  for (const item of remaining.values()) layers.get(item.layer)?.push(item);
  return [...layers.values()].flat();
}
function topPictureAt(point) {
  return sceneItems().reverse().find(item => item.corners && imageVisible(item) && imageContains(item, point));
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
$('newCutout').onclick = () => { if(active!==null || cutoutPending || busy) return; forceImageLasso=true; imageSelection=null; draw(); $('status').textContent='Lasso any area, including inside an image, to copy a new cutout.' };
function centeredCorners(width, height, point, offsets = null) {
  offsets ||= [[-width/2,-height/2],[width/2,-height/2],[width/2,height/2],[-width/2,height/2]];
  if (!point) return offsets.map(([x, y]) => [x + state.width/2, y + Math.min(state.height,1872)/2]);
  const xs = offsets.map(p => p[0]), ys = offsets.map(p => p[1]);
  const ratio = Math.min(1, state.width / (Math.max(...xs) - Math.min(...xs)),
    state.height / (Math.max(...ys) - Math.min(...ys)));
  const x = Math.max(-Math.min(...xs) * ratio, Math.min(point[0], state.width - Math.max(...xs) * ratio));
  const y = Math.max(-Math.min(...ys) * ratio, Math.min(point[1], state.height - Math.max(...ys) * ratio));
  return offsets.map(([left, top]) => [x + left * ratio, y + top * ratio]);
}
function pasteCutout(point = null) {
  if ($('pasteImage').disabled) return false;
  imageSelection = null;
  const [width, height] = state.cutout_clipboard.size;
  const local = state.cutout_clipboard.incoming ? null : imageClipboard;
  const samePosition = !point && local?.sourceCorners && local.sourcePageId !== imagePageIdentity();
  const corners = samePosition ? local.sourceCorners : centeredCorners(width, height, point, local?.offsets);
  send({op:'paste-cutout', corners, layer:$('layer').value, clipboard_id:state.cutout_clipboard.id});
  cutoutArmed = false;
  return true;
}
$('pasteImage').onclick = () => pasteCutout();
$('clearCutout').onclick = () => {
  if (!busy) send({op:'clear-cutout'})
};
function copyCutout(image) {
  imageClipboard = image;
  const {src, width, height} = image;
  send({op:'copy-cutout', src, width, height});
}
window.notebookRefreshCutout = (clipboard, initial = false) => {
  if (active !== null || busy) return false;
  if (!initial && clipboard?.id === state.cutout_clipboard?.id) return true;
  if (!initial) imageClipboard = null;
  state.cutout_clipboard = clipboard;
  cutoutArmed = !!clipboard?.incoming && !state.read_only && !state.warning && !state.password_required;
  if (cutoutArmed) {
    mode = 'capture';
    $('status').textContent = 'Tap the page to paste the copied image.';
  }
  imageRender();
  if (typeof syncChrome === 'function') syncChrome();
  return true;
};
$('copyImage').onclick = () => {
  const p=selectedPicture(); if (!p || busy) return;
  const center=p.corners.reduce((a,q)=>[a[0]+q[0]/4,a[1]+q[1]/4],[0,0]);
  copyCutout({src:p.src,sourcePageId:imagePageIdentity(),sourceCorners:p.corners.map(q=>[...q]),offsets:p.corners.map(q=>[q[0]-center[0],q[1]-center[1]]),width:Math.hypot(p.corners[1][0]-p.corners[0][0],p.corners[1][1]-p.corners[0][1]),height:Math.hypot(p.corners[3][0]-p.corners[0][0],p.corners[3][1]-p.corners[0][1])});
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
    send({op:'paste-image', src:boundedPNG(surface), corners:centeredCorners(surface.width, surface.height), layer:$('layer').value})
  } catch(error) { $('status').textContent=error.message || 'Unable to open image.' }
};
async function captureCutout(path) {
  if(path.length<3 || cutoutPending) return;
  const left=Math.max(0,Math.floor(Math.min(...path.map(p=>p[0])))),top=Math.max(0,Math.floor(Math.min(...path.map(p=>p[1]))));
  const width=Math.min(state.width,Math.ceil(Math.max(...path.map(p=>p[0]))))-left,height=Math.min(state.height,Math.ceil(Math.max(...path.map(p=>p[1]))))-top;
  if(width<2 || height<2) return;
  if((state.images||[]).some(p=>imageVisible(p) && !imageCache.get(p.src)?.complete)) { $('status').textContent='Wait for images to load before capturing.'; return }
  const bg = $('pdfBackground');
  if (state.background) {
    const source = bg.src, page = state;
    cutoutPending = true;
    imageRender();
    try {
      // WebKit can retain complete and naturalWidth after the decoded pixels
      // have been discarded. Wait for real decoded pixels before drawing.
      await bg.decode();
    } catch {
      if (state === page && bg.src === source && mode === 'capture')
        $('status').textContent = 'Unable to load the background for this cutout.';
      return;
    } finally {
      cutoutPending = false;
      imageRender();
    }
    if (state !== page || bg.src !== source || mode !== 'capture' || busy || active !== null ||
        state.password_required || state.read_only || state.warning) return;
  }
  const surface=document.createElement('canvas'),ratio=Math.min(1,Math.sqrt(4*1024*1024/(width*height)));
  surface.width=Math.max(1,Math.ceil(width*ratio)); surface.height=Math.max(1,Math.ceil(height*ratio));
  const g=surface.getContext('2d');g.scale(ratio,ratio);g.translate(-left,-top);g.beginPath();g.moveTo(...path[0].slice(0,2));for(const p of path.slice(1))g.lineTo(p[0],p[1]);g.closePath();g.clip();g.fillStyle='white';g.fillRect(left,top,width,height);
  paintBackground(g, bg);
  const selection=imageSelection; imageSelection=null;const previous=selected;selected=new Set();
  try { paintOrderedInk(sceneItems().filter(imageVisible), g, false) } finally { imageSelection=selection;selected=previous }
  copyCutout({src:boundedPNG(surface),width,height,sourcePageId:imagePageIdentity(),sourceCorners:[[left,top],[left+width,top],[left+width,top+height],[left,top+height]]});
}
const imageDown=canvas.onpointerdown,imageMove=canvas.onpointermove,imageUp=canvas.onpointerup,imageCancel=canvas.onpointercancel;
canvas.onpointerdown = e => {
  if(mode!=='capture') return imageDown(e);
  e.preventDefault(); if(active!==null || cutoutPending || busy || state.warning || state.read_only || state.password_required || (e.pointerType==='touch' && penTouchBlocked()) || (e.pointerType==='pen' && state.native_pen && e.isTrusted && !e.nativePen)) return;
  const q=coord(e),current=selectedPicture(),radius=16*state.width/canvas.getBoundingClientRect().width;
  let kind='move',hit=null;
  if(current && !forceImageLasso) { const handles=imageHandles(current);const i=handles.findIndex(p=>Math.hypot(p[0]-q[0],p[1]-q[1])<radius);if(i>=0) { hit=current;kind=i===0?'scale':'rotate' } }
  hit=hit || (!cutoutArmed && !forceImageLasso && topPictureAt(q));
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
  const gesture=imageGesture,path=points,p=selectedPicture(),newCutout=forceImageLasso;
  active=null;points=[];imageGesture=null;forceImageLasso=false;
  if(e.pointerType==='pen')notePenContact(false);
  if(gesture) {
    const corners=p?.corners;state.images=state.images.map(p=>p.id===gesture.original.id?gesture.original:p);
    if(!cancelled && corners && JSON.stringify(corners)!==JSON.stringify(gesture.corners))send({op:'image-transform',id:p.id,corners})
  } else if (!cancelled) {
    const tapRadius = 6 * state.width / canvas.getBoundingClientRect().width;
    if (path.every(point => Math.hypot(point[0] - start[0], point[1] - start[1]) <= tapRadius)) {
      imageSelection = cutoutArmed ? null : topPictureAt(last)?.id || null;
      if (newCutout || imageSelection || !pasteCutout(last)) imageRender();
    } else captureCutout(path);
  }
  draw();flushUpdate()
}
canvas.onpointerup=e=>finishImage(e);
canvas.onpointercancel=e=>finishImage(e,true);
canvas.onlostpointercapture=e=>finishImage(e,true);
document.addEventListener('keydown',e=>{
  if(mode!=='capture') return;
  if(/INPUT|SELECT|TEXTAREA/.test(e.target.tagName) || active!==null || busy)return;
  if((e.ctrlKey||e.metaKey) && e.key.toLowerCase()==='v' && state.cutout_clipboard) { e.preventDefault();$('pasteImage').onclick() }
  if((e.ctrlKey||e.metaKey) && e.key.toLowerCase()==='c' && selectedPicture()) {e.preventDefault();$('copyImage').onclick()}
});

for (const id of ['erase', 'select', 'tool']) $(id).addEventListener(id === 'tool' ? 'change' : 'click', imageRender);
