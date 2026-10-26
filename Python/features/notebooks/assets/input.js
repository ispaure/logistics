let erasePreviewCount = 0, pendingErase = null;
function sample(event) {
  let point = coord(event);
  last = point;
  if (points.length >= 100000) return;
  let previous = points[points.length - 1];
  if (previous && point.every((v, i) => v === previous[i])) return;
  points.push(point);
  if (mode === 'erase' && eraserKind === 'whole')
    for (let id of hits(point)) selected.add(id)
}

function coord(e) {
  let r = canvas.getBoundingClientRect();
  return [Math.max(0, Math.min(state.width, (e.clientX - r.left) / r.width * state.width)), Math.max(0, Math.min(state.height, (e.clientY - r.top) / r.height * state.height)), e.pointerType === 'pen' ? Math.max(0, Math.min(1, e.pressure)) : .5]
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
  return state.strokes.filter(s => visible.has(s.layer) && s.points.some((v, i) => distance(p, i ? s.points[i - 1] : v, v) < (mode === 'erase' ? eraserRadius + v[3] / 2 : Math.max(12, v[3] / 2)))).map(s => s.id)
}
canvas.onpointerdown = e => {
  if (e.pointerType === 'pen' && state.native_pen && e.isTrusted && !e.nativePen) {
    e.preventDefault();
    return
  }
  if (active !== null) return;
  if (e.pointerType === 'touch' && !$('finger').checked) {
    if (pan) {
      pan.cancelled = true;
      return
    }
    pan = {
      id: e.pointerId,
      x: e.clientX,
      y: e.clientY,
      startX: e.clientX,
      startY: e.clientY,
      time: performance.now(),
      paging: pageSwipe && canvas.getBoundingClientRect().width <= $('viewport').clientWidth + 1
    };
    canvas.setPointerCapture(e.pointerId);
    e.preventDefault();
    return
  }
  if ((busy && !(continuousInk && mode === 'ink' && queue.length < 64 && queue.every(a => a.op === 'stroke'))) || state.warning || state.read_only) return;
  if (e.pointerType === 'pen') pan = null;
  canvas.style.touchAction = 'none';
  e.preventDefault();
  active = e.pointerId;
  if (!e.nativePen) canvas.setPointerCapture(active);
  inkSettings = chosenInk();
  start = last = coord(e);
  points = [start];
  previewCount = 0;
  erasePreviewCount = 0;
  if (mode === 'erase') {
    selected = new Set(eraserKind === 'whole' ? hits(start) : []);
    draw()
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
  for (let event of events) sample(event);
  sample(e);
  // Mobile paints the delivered batch immediately. Desktop coalesces batches
  // to display frames, avoiding redundant canvas work during mouse bursts.
  if (mode === 'ink') {
    if (frameBatchedInk) schedulePreview();
    else flushPreview()
  }
  else if (mode === 'erase' && eraserKind === 'partial') {
    previewErase(points.slice(Math.max(0, erasePreviewCount - 1)));
    erasePreviewCount = points.length
  } else draw()
};

function finish(e, cancelled = false) {
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
  active = null;
  if (cancelled) {
    cancelPreview();
    points = [];
    draw();
    flushUpdate();
    return
  }
  let end = coord(e);
  if (!last || end[0] !== last[0] || end[1] !== last[1]) sample(e);
  flushPreview();
  let captured = points;
  points = [];
  if (mode === 'erase') {
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
      if (!['fineliner', 'ballpoint'].includes(brushFor(inkSettings.tool).family)) commitDraft(inkSettings.tool);
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
}
canvas.onpointerup = e => finish(e);
canvas.onpointercancel = e => finish(e, true);
canvas.onlostpointercapture = e => finish(e, true);
// Android supplies every MotionEvent history point, even when WebView omits
// getCoalescedEvents(). Coordinates are relative to the current native WebView.
window.logisticsNativePen = (action, id, samples, width, height) => {
  if (!state.native_pen || !width || !height || !samples.length) return;
  const event = sample => ({pointerId: id + 100000, pointerType: 'pen', nativePen: true,
    clientX: sample[0] * innerWidth / width, clientY: sample[1] * innerHeight / height,
    pressure: sample[2], preventDefault() {}});
  let lastEvent = event(samples[samples.length - 1]);
  if (action === 'down') {
    if (document.elementFromPoint(lastEvent.clientX, lastEvent.clientY) !== canvas) return;
    canvas.onpointerdown(lastEvent)
  } else if (action === 'cancel') finish(lastEvent, true);
  else {
    if (action === 'up') {
      if (samples.length > 1) {
        let historical = event(samples[samples.length - 2]);
        historical.getCoalescedEvents = () => samples.slice(0, -2).map(event);
        canvas.onpointermove(historical)
      }
      finish(lastEvent)
    } else {
      lastEvent.getCoalescedEvents = () => samples.slice(0, -1).map(event);
      canvas.onpointermove(lastEvent)
    }
  }
};
// The tool button always selects the eraser and exposes its editable settings.
let eraserKind = 'partial', eraserRadius = 16;
const eraserDialog = document.createElement('dialog');
eraserDialog.id = 'eraserDialog';
eraserDialog.setAttribute('aria-labelledby', 'eraserTitle');
eraserDialog.innerHTML = '<h2 id="eraserTitle">Eraser</h2><label>Type <select id="eraserKind" aria-label="Eraser type"><option value="partial">Erase parts of strokes</option><option value="whole">Erase whole strokes</option></select></label><label>Size <select id="eraserSize" aria-label="Eraser size"><option value="8">Small</option><option value="16" selected>Medium</option><option value="32">Large</option></select></label><button id="closeEraser" type="button">Done</button>';
document.body.append(eraserDialog);
$('eraserKind').onchange = () => {
  eraserKind = $('eraserKind').value;
  selected.clear();
  draw();
  if (typeof syncChrome === 'function') syncChrome()
};
$('eraserSize').onchange = () => eraserRadius = Number($('eraserSize').value);
$('closeEraser').onclick = () => eraserDialog.close();
eraserDialog.onclick = e => {if (e.target === eraserDialog) {
  let r = eraserDialog.getBoundingClientRect();
  if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) eraserDialog.close()
}};
let showEraserSettings = () => eraserDialog.showModal();
$('erase').setAttribute('aria-haspopup', 'dialog');
$('erase').onclick = () => {
  if (active !== null) return;
  mode = 'erase';
  $('erase').classList.add('active');
  $('select').classList.remove('active');
  selected.clear();
  draw();
  if (!eraserDialog.open) showEraserSettings()
};
$('select').onclick = () => {
  mode = mode === 'select' ? 'ink' : 'select';
  $('select').classList.toggle('active', mode === 'select');
  $('erase').classList.remove('active');
  selected.clear();
  draw()
};
$('tool').onchange = () => {
  brushOptions();
  mode = 'ink';
  $('erase').classList.remove('active');
  $('select').classList.remove('active')
};
