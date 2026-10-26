function options(id, values) {
  let el = $(id),
    old = el.value;
  el.replaceChildren();
  for (let [name, value] of values) {
    let o = document.createElement('option');
    o.textContent = name;
    o.value = value;
    el.append(o)
  }
  if ([...el.options].some(o => o.value === old)) el.value = old
}

function render() {
  const background = $('pdfBackground');
  background.hidden = !state.background;
  if (state.background) {
    if (background.getAttribute('src') !== state.background) background.src = state.background;
  } else background.removeAttribute('src');
  $('title').textContent = state.name;
  if (document.activeElement !== $('notebookName')) $('notebookName').value = state.name;
  $('pageinfo').textContent = (state.index + 1) + ' / ' + state.count;
  $('warning').textContent = state.warning || '';
  $('templateNotice').textContent = state.template && state.template !== 'Blank' ? 'Template ' + state.template + ' is preserved in export; this view shows ink only.' : '';
  $('undo').disabled = !state.undo;
  $('redo').disabled = !state.redo;
  $('prev').disabled = !state.index;
  $('next').disabled = state.index + 1 === state.count;
  options('layerVisibility', state.layers.map(x => [(x[2] ? 'Visible: ' : 'Hidden: ') + x[1], x[0]]));
  options('tool', Object.entries(state.tools));
  brushOptions();
  options('layer', state.layers.filter(x => x[2]).map(x => [x[1], x[0]]));
  $('prev').onclick = () => send({
    op: 'page',
    index: state.index - 1
  });
  $('next').onclick = () => send({
    op: 'page',
    index: state.index + 1
  });
  resize();
}

function resize() {
  let viewport = $('viewport'),
    style = getComputedStyle(viewport);
  let fit = Math.max(.1, (viewport.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)) / state.width);
  let zoom = $('zoom').value,
    scale;
  if (zoom === 'page') {
    let available = viewport.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
    for (let id of ['warning', 'templateNotice']) {
      let notice = $(id),
        css = getComputedStyle(notice);
      available -= notice.getBoundingClientRect().height + (parseFloat(css.marginTop) || 0) + (parseFloat(css.marginBottom) || 0)
    }
    scale = Math.min(Math.max(1, viewport.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)) / state.width, Math.max(1, available) / state.height, 1);
  } else scale = zoom === 'fit' ? Math.min(fit, 1) : Number(zoom);
  canvas.style.width = (state.width * scale) + 'px';
  canvas.style.height = (state.height * scale) + 'px';
  let ratio = Math.min(devicePixelRatio || 1, 2);
  let backingScale = Math.min(scale * ratio, Math.sqrt(canvasPixelLimit / (state.width * state.height))),
    width = Math.max(1, Math.floor(state.width * backingScale)),
    height = Math.max(1, Math.floor(state.height * backingScale));
  // Assigning unchanged dimensions also reallocates canvas storage. A page
  // change needs a redraw, not three replacement GPU-backed bitmaps.
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
    ctx.setTransform(canvas.width / state.width, 0, 0, canvas.height / state.height, 0, 0);
    sizeDraft()
  }
  draw()
}

function previewErase(samples, radius = eraserRadius) {
  if (!samples.length) return;
  ctx.save();
  ctx.globalCompositeOperation = 'destination-out';
  ctx.lineWidth = radius * 2;
  ctx.lineCap = ctx.lineJoin = 'round';
  ctx.beginPath();
  ctx.moveTo(samples[0][0], samples[0][1]);
  for (let p of samples) ctx.lineTo(p[0], p[1]);
  ctx.stroke();
  const end = samples[samples.length - 1];
  ctx.beginPath();
  ctx.arc(end[0], end[1], radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore()
}

function draw() {
  clearDraft();
  ctx.clearRect(0, 0, state.width, state.height);
  let visible = new Set(state.layers.filter(x => x[2]).map(x => x[0]));
  for (let s of state.strokes)
    if (visible.has(s.layer)) line(s);
  if (continuousInk)
    for (let action of queue)
      if (action.op === 'stroke') line({
        tool: action.tool,
        ...nativeColor(action.tool, action.color),
        points: strokePoints(action.points, action.tool, action.width)
      });
  if (pendingInk) line(pendingInk);
  if (pendingErase) previewErase(pendingErase.points, pendingErase.radius);
  if (points.length && mode === 'erase' && eraserKind === 'partial') previewErase(points);
  if (points.length && mode === 'ink') {
    preview(points);
    previewCount = points.length
  }
}
