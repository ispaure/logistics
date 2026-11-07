const fallbackPressure = .5;
let constantPenPressure = false;
// Bounded content-free input diagnostics: no coordinates, labels or stroke data.
const inputTraceCounts = Object.create(null), inputTraceRing = [];
const inputTraceViewId = (()=>{
  try {
    if (state.native_pen && /^[0-9a-f]{32}$/.test(state.native_pen_nonce || '')) return state.native_pen_nonce;
    const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);
    return [...bytes].map(value=>value.toString(16).padStart(2,'0')).join('');
  } catch (_) { return null } // Unknown lifetime must never look like a stable ID.
})();
function inputTrace(kind, event) {
  try {
    const type = event?.pointerType || 'host', key = kind + ':' + type;
    inputTraceCounts[key] = (inputTraceCounts[key] || 0) + 1;
    inputTraceRing.push({kind,type,trusted:!!event?.isTrusted,active:active!==null,
      busy,queued:queue.length,ink:mode==='ink',ms:Math.round(performance.now())});
    if(inputTraceRing.length>96)inputTraceRing.shift();
  } catch (_) { /* Diagnostics must never change input dispatch. */ }
}
window.logisticsInputTrace = () => ({view_id:inputTraceViewId,counts:{...inputTraceCounts},recent:inputTraceRing.slice(-24)});
for(const kind of ['pointerdown','pointerup','pointercancel','lostpointercapture'])
  canvas.addEventListener(kind,event=>inputTrace('delivered-'+kind,event),{capture:true,passive:true});

let erasePreviewCount = 0, pendingErase = null;
const wholeErasePreview = new Set();
let wholeEraseCandidates = [];

function sweepHitsSegment(a, b, c, d) {
  const reach = eraserRadius + Math.max(a[3], b[3]) / 2;
  if (Math.max(a[0], b[0]) + reach < Math.min(c[0], d[0]) ||
      Math.min(a[0], b[0]) - reach > Math.max(c[0], d[0]) ||
      Math.max(a[1], b[1]) + reach < Math.min(c[1], d[1]) ||
      Math.min(a[1], b[1]) - reach > Math.max(c[1], d[1])) return false;
  // Match the host's tapered-segment/capsule test. Split where the closest
  // point on the sweep changes between an endpoint and its interior.
  const vx = b[0] - a[0], vy = b[1] - a[1];
  const dx = d[0] - c[0], dy = d[1] - c[1], length = dx * dx + dy * dy;
  const projection = length ? ((a[0] - c[0]) * dx + (a[1] - c[1]) * dy) / length : 0;
  const slope = length ? (vx * dx + vy * dy) / length : 0;
  const cuts = slope ? [-projection / slope, (1 - projection) / slope]
    .filter(t => t > 0 && t < 1).sort((a, b) => a - b) : [];
  const boundaries = [0, ...cuts, 1];
  const radius = eraserRadius + a[3] / 2, dr = (b[3] - a[3]) / 2;
  for (let i = 1; i < boundaries.length; i++) {
    const lo = boundaries[i - 1], hi = boundaries[i];
    const u = projection + slope * (lo + hi) / 2;
    const interior = length && u > 0 && u < 1;
    const end = u >= 1 ? d : c;
    const x = interior ? a[0] - c[0] - projection * dx : a[0] - end[0];
    const y = interior ? a[1] - c[1] - projection * dy : a[1] - end[1];
    const sx = interior ? vx - slope * dx : vx, sy = interior ? vy - slope * dy : vy;
    const aa = sx * sx + sy * sy - dr * dr;
    const bb = 2 * (x * sx + y * sy - radius * dr);
    const cc = x * x + y * y - radius * radius;
    const t = aa > 0 ? Math.max(lo, Math.min(hi, -bb / (2 * aa)))
      : (aa * (lo + hi) + bb > 0 ? lo : hi);
    if ((aa * t + bb) * t + cc < 0 || (aa === 0 && bb === 0 && cc === 0)) return true
  }
  return false
}

function previewWholeErase(from, to) {
  const left = Math.min(from[0], to[0]) - eraserRadius;
  const top = Math.min(from[1], to[1]) - eraserRadius;
  const right = Math.max(from[0], to[0]) + eraserRadius;
  const bottom = Math.max(from[1], to[1]) + eraserRadius;
  for (const {stroke, bounds: [l, t, r, b]} of wholeEraseCandidates) {
    if (wholeErasePreview.has(stroke.id) || l > right || t > bottom || r < left || b < top) continue;
    const samples = stroke.points;
    const hit = samples.length === 1 ? sweepHitsSegment(samples[0], samples[0], from, to)
      : samples.some((point, i) => i > 0 && sweepHitsSegment(samples[i - 1], point, from, to));
    if (hit) wholeErasePreview.add(stroke.id)
  }
}
function sample(event, bounds) {
  let point = coord(event, bounds);
  last = point;
  if (points.length >= 100000) return;
  let previous = points[points.length - 1];
  if (previous && point.every((v, i) => v === previous[i])) return;
  points.push(point);
  if (mode === 'erase' && eraserKind === 'whole')
    previewWholeErase(previous || point, point)
}

function coord(e, r = canvas.getBoundingClientRect()) {
  const pressure = e.pointerType === 'pen' && !constantPenPressure
    ? Math.max(0, Math.min(1, e.pressure)) : fallbackPressure;
  return [Math.max(0, Math.min(state.width, (e.clientX - r.left) / r.width * state.width)), Math.max(0, Math.min(state.height, (e.clientY - r.top) / r.height * state.height)), pressure]
}

function distance(p, a, b) {
  let dx = b[0] - a[0],
    dy = b[1] - a[1],
    v = dx * dx + dy * dy,
    t = v ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / v)) : 0;
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)
}

function hits(p) {
  let visible = new Set(state.layers.filter(x => x[2]).map(x => x[0]));
  return state.strokes.filter(s => visible.has(s.layer) && s.points.some((v, i) => distance(p, i ? s.points[i - 1] : v, v) < Math.max(12, v[3] / 2))).map(s => s.id)
}
function beginPan(e, capture = canvas) {
  if (e.pointerType === 'touch' && penTouchBlocked()) return;
  if (pan) {
    pan.cancelled = true;
    return
  }
  pan = {
    id: e.pointerId, x: e.clientX, y: e.clientY,
    startX: e.clientX, startY: e.clientY, time: performance.now(),
    paging: pageSwipe && canvas.getBoundingClientRect().width <= $('viewport').clientWidth + 1
  };
  capture.setPointerCapture(e.pointerId);
  e.preventDefault()
}
canvas.onpointerdown = e => {
  // A second contact (often the resting palm) must not fall through to the
  // browser's default selection even while a Pencil stroke owns the canvas.
  e.preventDefault();
  if (e.pointerType === 'touch' && penTouchBlocked()) {inputTrace('reject-palm',e);return}
  if (e.pointerType === 'pen' && state.native_pen && e.isTrusted && !e.nativePen) {
    inputTrace('reject-native-duplicate',e);
    e.preventDefault();
    return
  }
  // Prefer the stylus when a finger/palm started an unfinished ink gesture.
  if (e.pointerType === 'pen' && touchContacts.has(active)) cancelTouchZoom();
  if (active !== null) {inputTrace('reject-active',e);return}
  if (e.pointerType === 'touch' && !$('finger').checked) {
    beginPan(e);
    return
  }
  if ((busy && !(continuousInk && mode === 'ink' && queue.length < 64 && queue.every(a => a.op === 'stroke' || (e.nativePen && ['save', 'save-as', 'export', 'library'].includes(a.op))))) || state.warning || state.read_only || state.password_required) {inputTrace('reject-locked-or-busy',e);return}
  if (e.pointerType === 'pen') {
    notePenContact(true);
    pan = null;
    cancelTouchZoom()
  }
  canvas.style.touchAction = 'none';
  e.preventDefault();
  active = e.pointerId;
  inputTrace('accepted-down',e);
  if (!e.nativePen) canvas.setPointerCapture(active);
  inkSettings = chosenInk();
  start = last = coord(e);
  points = [start];
  previewCount = 0;
  erasePreviewCount = 0;
  if (mode === 'erase') {
    if (eraserKind === 'whole') {
      const visible = new Set(state.layers.filter(layer => layer[2]).map(layer => layer[0]));
      wholeEraseCandidates = state.strokes.filter(stroke => visible.has(stroke.layer) && stroke.points.length)
        .map(stroke => ({stroke, bounds: strokeBounds(stroke.points, 0)}));
      previewWholeErase(start, start);
      if (wholeErasePreview.size) draw()
    } else previewErase(points)
  } else if (mode === 'select') {
    let ids = hits(start);
    selected = new Set(ids.slice(-1));
    draw()
  } else flushPreview()
  if (mode === 'erase') erasePreviewCount = points.length;
};
canvas.onpointermove = e => {
  if (pan && pan.id === e.pointerId) {
    if (pan.cancelled) return;
    e.preventDefault();
    if (!pan.paging) $('viewport').scrollLeft += pan.x - e.clientX;
    $('viewport').scrollTop += pan.y - e.clientY;
    pan.x = e.clientX;
    pan.y = e.clientY;
    return
  }
  if (e.pointerId !== active || (state.native_pen && e.isTrusted && !e.nativePen)) return;
  e.preventDefault();
  let events = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
  // Sampling changes ink data, not layout. Reuse one geometry read for this
  // delivered batch, and refresh it on the next event after scroll/resize.
  const bounds = canvas.getBoundingClientRect();
  const previousEraseHits = wholeErasePreview.size;
  for (let event of events) sample(event, bounds);
  sample(e, bounds);
  // Mobile paints the delivered batch immediately. Desktop coalesces batches
  // to display frames, avoiding redundant canvas work during mouse bursts.
  if (mode === 'ink') {
    if (frameBatchedInk) schedulePreview();
    else flushPreview()
  }
  else if (mode === 'erase' && eraserKind === 'partial') {
    previewErase(points.slice(Math.max(0, erasePreviewCount - 1)));
    erasePreviewCount = points.length
  } else if (mode !== 'erase' || wholeErasePreview.size !== previousEraseHits) draw()
};

function finish(e, cancelled = false) {
  if (mode === 'select') return selectionFinish(e, cancelled);
  if (mode === 'capture') return finishImage(e, cancelled);
  if (pan && pan.id === e.pointerId) {
    let gesture = pan,
      dx = e.clientX - gesture.startX,
      dy = e.clientY - gesture.startY;
    pan = null;
    if (!cancelled && !gesture.cancelled && gesture.paging && !busy &&
        performance.now() - gesture.time < 900 && Math.abs(dx) >= 48 && Math.abs(dx) > Math.abs(dy) * 1.5) {
      let index = state.index + (dx < 0 ? 1 : -1);
      if (index >= 0 && index < state.count) send({op: 'page', index})
    }
    return
  }
  if (e.pointerId !== active || (state.native_pen && e.isTrusted && !e.nativePen)) return;
  if (e.pointerType === 'pen' || penContactActive) notePenContact(false);
  inputTrace(cancelled?'cancelled-contact':'completed-contact',e);
  active = null;
  if (cancelled) {
    cancelPreview();
    wholeErasePreview.clear();
    wholeEraseCandidates = [];
    points = [];
    // Applying a deferred viewport size redraws the page itself. Avoid
    // replaying all stored ink immediately before that same redraw.
    if (!viewportResizePending) draw();
    flushUpdate();
    return
  }
  let end = coord(e);
  if (!last || end[0] !== last[0] || end[1] !== last[1]) sample(e);
  flushPreview();
  let captured = points;
  points = [];
  if (mode === 'erase') {
    wholeEraseCandidates = [];
    if (eraserKind === 'partial') pendingErase = {points: captured, radius: eraserRadius};
    send({
      op: 'erase',
      points: captured,
      radius: eraserRadius,
      kind: eraserKind
    })
  } else if (mode === 'select' && selected.size) {
    send({
      op: 'transform',
      ids: [...selected],
      dx: last[0] - start[0],
      dy: last[1] - start[1]
    })
  } else if (mode === 'ink' && captured.length) {
    if (continuousInk) {
      if (!['fineliner', 'ballpoint', 'highlighter'].includes(brushFor(inkSettings.tool).family)) commitDraft(inkSettings.tool);
      pendingInk = null
    } else pendingInk = {
      tool: inkSettings.tool,
      ...nativeColor(inkSettings.tool, inkSettings.color),
      points: strokePoints(captured, inkSettings.tool, inkSettings.width)
    };
    send({
      op: 'stroke',
      points: captured,
      ...inkSettings
    })
  }
  if ((mode !== 'ink' || !busy) && !(mode === 'erase' && eraserKind === 'partial' && busy)) draw();
  flushUpdate()
}

function flushUpdate() {
  if (deferredUpdate) {
    let update = deferredUpdate;
    deferredUpdate = null;
    update()
  }
  if (viewportResizePending && active === null) {
    viewportResizePending = false;
    resize()
  }
}
canvas.onpointerup = e => finish(e);
canvas.onpointercancel = e => finish(e, true);
canvas.onlostpointercapture = e => finish(e, true);
// Android supplies every MotionEvent history point, even when WebView omits
// getCoalescedEvents(). Coordinates are relative to the current native WebView.
let nativePenContact = null;
window.logisticsNativePenReset = () => {
  if (nativePenContact && active === nativePenContact.pointerId) finish(nativePenContact, true);
  nativePenContact = null
};
window.logisticsNativePen = (action, id, samples, width, height) => {
  if (!state.native_pen || !width || !height || !samples.length) return;
  const event = sample => ({pointerId: id + 100000, pointerType: 'pen', nativePen: true,
    clientX: sample[0] * innerWidth / width, clientY: sample[1] * innerHeight / height,
    pressure: sample[2], preventDefault() {}});
  let lastEvent = event(samples[samples.length - 1]);
  if (action === 'down') {
    if (document.elementFromPoint(lastEvent.clientX, lastEvent.clientY) !== canvas) return;
    canvas.onpointerdown(lastEvent);
    if (active === lastEvent.pointerId) nativePenContact = lastEvent
  } else if (action === 'cancel') {
    finish(lastEvent, true);
    if (nativePenContact?.pointerId === lastEvent.pointerId) nativePenContact = null
  }
  else {
    if (action === 'up') {
      if (samples.length > 1) {
        let historical = event(samples[samples.length - 2]);
        historical.getCoalescedEvents = () => samples.slice(0, -2).map(event);
        canvas.onpointermove(historical)
      }
      finish(lastEvent);
      if (nativePenContact?.pointerId === lastEvent.pointerId) nativePenContact = null
    } else {
      lastEvent.getCoalescedEvents = () => samples.slice(0, -1).map(event);
      canvas.onpointermove(lastEvent);
      if (active === lastEvent.pointerId) nativePenContact = lastEvent
    }
  }
};
let eraserKind = state.eraser_kind === 'whole' ? 'whole' : 'partial', eraserRadius = 16;
let onEraserKindChanged = () => {};
const eraserDialog = document.createElement('dialog');
eraserDialog.id = 'eraserDialog';
eraserDialog.setAttribute('aria-labelledby', 'eraserTitle');
eraserDialog.innerHTML = '<h2 id="eraserTitle">Eraser</h2><div class="eraser-types" role="group" aria-label="Eraser type"><button id="eraserPartial" type="button" aria-label="Erase parts of strokes" aria-pressed="true"></button><button id="eraserWhole" type="button" aria-label="Erase whole strokes" aria-pressed="false"></button></div><label>Size <select id="eraserSize" aria-label="Eraser size"><option value="8">Small</option><option value="16" selected>Medium</option><option value="32">Large</option></select></label><button id="closeEraser" type="button">Done</button>';
document.body.append(eraserDialog);
function renderEraserChoices() {
  $('eraserPartial').innerHTML = icon(glyphs.erase) + '<span>Partial</span>';
  $('eraserWhole').innerHTML = icon(glyphs.eraseWhole) + '<span>Whole stroke</span>'
}
for (const [kind, id, caption] of [
  ['partial', 'eraserPartial', 'Partial'],
  ['whole', 'eraserWhole', 'Whole stroke']
]) {
  const button = $(id);
  button.textContent = caption;
  button.onclick = () => {
    if (eraserKind === kind) return;
    eraserKind = kind;
    syncEraserKind();
    onEraserKindChanged(kind);
    selected.clear();
    draw();
    if (typeof syncChrome === 'function') syncChrome()
  }
}
function syncEraserKind() {
  $('eraserPartial').setAttribute('aria-pressed', String(eraserKind === 'partial'));
  $('eraserWhole').setAttribute('aria-pressed', String(eraserKind === 'whole'));
}
syncEraserKind();
$('eraserSize').onchange = () => eraserRadius = Number($('eraserSize').value);
$('closeEraser').onclick = () => eraserDialog.close();
eraserDialog.onclick = e => {if (e.target === eraserDialog) {
  let r = eraserDialog.getBoundingClientRect();
  if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) eraserDialog.close()
}};
let showEraserSettings = () => eraserDialog.showModal();
$('erase').setAttribute('aria-haspopup', 'dialog');
function selectEraser() {
  mode = 'erase';
  $('erase').classList.add('active');
  $('select').classList.remove('active');
  selected.clear();
  draw();
}
$('erase').onclick = () => {
  if (active !== null) return;
  selectEraser();
  if (!eraserDialog.open) showEraserSettings()
};
$('select').onclick = () => {
  if (active !== null) return;
  mode = mode === 'select' ? 'ink' : 'select';
  $('select').classList.toggle('active', mode === 'select');
  $('erase').classList.remove('active');
  selected.clear();
  draw()
};
$('tool').onchange = () => {
  if (active !== null) return;
  brushOptions();
  mode = 'ink';
  $('erase').classList.remove('active');
  $('select').classList.remove('active')
};
