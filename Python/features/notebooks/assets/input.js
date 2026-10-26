function sample(event) {
  let point = coord(event);
  last = point;
  if (points.length >= 100000) return;
  let previous = points[points.length - 1];
  if (previous && point.every((v, i) => v === previous[i])) return;
  points.push(point);
  if (mode === 'ink') preview(previous ? [previous, point] : [point]);
  else if (mode === 'erase')
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
  return state.strokes.filter(s => visible.has(s.layer) && s.points.some((v, i) => distance(p, i ? s.points[i - 1] : v, v) < Math.max(12, v[3] / 2))).map(s => s.id)
}
canvas.onpointerdown = e => {
  if ((busy && !(continuousInk && mode === 'ink' && queue.length < 64 && queue.every(a => a.op === 'stroke'))) || state.warning || state.read_only || active !== null) return;
  if (e.pointerType === 'touch' && !$('finger').checked) {
    pan = {
      id: e.pointerId,
      x: e.clientX,
      y: e.clientY
    };
    canvas.setPointerCapture(e.pointerId);
    return
  }
  if (e.pointerType === 'pen') pan = null;
  canvas.style.touchAction = 'none';
  e.preventDefault();
  active = e.pointerId;
  canvas.setPointerCapture(active);
  inkSettings = chosenInk();
  start = last = coord(e);
  points = [start];
  if (mode === 'erase') {
    selected = new Set(hits(start));
    draw()
  } else if (mode === 'select') {
    let ids = hits(start);
    selected = new Set(ids.slice(-1));
    draw()
  } else preview(points)
};
canvas.onpointermove = e => {
  if (pan && pan.id === e.pointerId) {
    $('viewport').scrollLeft += pan.x - e.clientX;
    $('viewport').scrollTop += pan.y - e.clientY;
    pan.x = e.clientX;
    pan.y = e.clientY;
    return
  }
  if (e.pointerId !== active) return;
  e.preventDefault();
  let events = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
  for (let event of events) sample(event);
  sample(e);
  if (mode !== 'ink') draw()
};

function finish(e, cancelled = false) {
  if (pan && pan.id === e.pointerId) {
    pan = null;
    return
  }
  if (e.pointerId !== active) return;
  active = null;
  if (cancelled) {
    points = [];
    draw();
    flushUpdate();
    return
  }
  let end = coord(e);
  if (!last || end[0] !== last[0] || end[1] !== last[1]) sample(e);
  let captured = points;
  points = [];
  if (mode === 'erase') send({
    op: 'erase',
    ids: [...selected]
  });
  else if (mode === 'select' && selected.size) {
    send({
      op: 'transform',
      ids: [...selected],
      dx: last[0] - start[0],
      dy: last[1] - start[1]
    })
  } else if (mode === 'ink' && captured.length) {
    pendingInk = {
      tool: inkSettings.tool,
      ...nativeColor(inkSettings.tool, inkSettings.color),
      points: strokePoints(captured, inkSettings.tool, inkSettings.width)
    };
    if (continuousInk) {
      if (!['fineliner', 'ballpoint'].includes(brushFor(inkSettings.tool).family)) {
        clearDraft();
        line(pendingInk)
      }
      pendingInk = null
    }
    send({
      op: 'stroke',
      points: captured,
      ...inkSettings
    })
  }
  if (mode !== 'ink' || !busy) draw();
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
$('erase').onclick = () => {
  mode = mode === 'erase' ? 'ink' : 'erase';
  $('erase').classList.toggle('active', mode === 'erase');
  $('select').classList.remove('active');
  selected.clear();
  draw()
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
