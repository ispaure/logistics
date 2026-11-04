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

let paperView = document.body.classList.contains('notebook-mobile') && Math.min(innerWidth, innerHeight) < 700 ? 'move' : 'pro';
let displayedPaperBounds = null;
function strokeExpandsPaper(stroke) {
  if (paperView !== 'move' || !displayedPaperBounds || !state.template_editable) return false;
  const b = displayedPaperBounds;
  return stroke.points.some(p => {
    const radius = Math.max(0, p[3] || 0) / 2 + 2;
    return Math.max(0, p[0] - radius) < b.x || Math.min(state.width, p[0] + radius) > b.x + b.width ||
      Math.min(state.height, p[1] + radius) > b.height
  })
}
function templateControls() {
  const panel = $('templateControls');
  if (!panel || $('pageTemplate')) return;
  panel.innerHTML = '<label>Page template <select id="pageTemplate" aria-label="Page template"></select></label>' +
    '<label>Template format <select id="templateFormat" aria-label="Template format"><option value="pro">Paper Pro</option><option value="move">Paper Pro Move</option></select></label>' +
    '<label><input id="templateVisible" type="checkbox"> Show template</label>' +
    '<label>Paper view <select id="paperView" aria-label="Paper view"><option value="pro">Paper Pro</option><option value="move">Paper Pro Move</option></select></label>';
  const apply = () => {
    if (active !== null || busy) { render(); return }
    send({op: 'template', name: $('pageTemplate').value,
      format: $('templateFormat').value, visible: $('templateVisible').checked})
  };
  for (const id of ['pageTemplate', 'templateFormat', 'templateVisible']) $(id).onchange = apply;
  $('templateFormat').onchange = () => {
    if (active !== null || busy) { render(); return }
    paperView = $('templateFormat').value;
    $('paperView').value = paperView;
    apply()
  };
  $('paperView').value = paperView;
  $('paperView').onchange = () => {
    if (active !== null) { $('paperView').value = paperView; return }
    paperView = $('paperView').value;
    resize();
    $('viewport').scrollTop = 0;
    $('viewport').scrollLeft = 0
  }
}

function paperBounds() {
  if (paperView !== 'move' || !state.template_editable) return {x: 0, y: 0, width: state.width, height: state.height};
  const box = state.move_paper || {x: 291.5, y: 0, width: 821, height: 1460};
  let left = box.x, right = box.x + box.width, bottom = box.height;
  for (const stroke of state.strokes) for (const p of stroke.points) {
    const radius = Math.max(0, p[3] || 0) / 2 + 2;
    left = Math.min(left, p[0] - radius); right = Math.max(right, p[0] + radius);
    bottom = Math.max(bottom, p[1] + radius)
  }
  left = Math.max(0, left); right = Math.min(state.width, right);
  return {x: left, y: 0, width: right - left, height: Math.min(state.height, bottom)}
}

function render() {
  templateControls();
  if ($('pageTemplate')) {
    const name = state.template_name || state.template || 'Blank';
    const catalog = {...(state.templates || {Blank: 'Blank'})};
    if (!(name in catalog)) catalog[name] = name + ' (preserved)';
    options('pageTemplate', Object.entries(catalog).map(([value, label]) => [label, value]));
    $('pageTemplate').value = name;
    $('templateFormat').value = name.startsWith('Logistics ') ? (state.template_settings?.format || 'pro') : paperView;
    $('templateVisible').checked = state.template_settings?.visible !== false;
    const disabled = state.read_only || !state.template_editable || !(name in (state.templates || {}));
    $('pageTemplate').disabled = state.read_only || !state.template_editable;
    $('templateFormat').disabled = disabled || !name.startsWith('Logistics ');
    $('templateVisible').disabled = disabled;
  }
  const background = $('pdfBackground');
  background.hidden = !state.background;
  if (state.background) {
    if (background.getAttribute('src') !== state.background) background.src = state.background;
  } else background.removeAttribute('src');
  $('title').textContent = state.name;
  if (document.activeElement !== $('notebookName')) $('notebookName').value = state.name;
  $('pageinfo').textContent = (state.index + 1) + ' / ' + state.count;
  $('warning').textContent = state.warning || '';
  $('templateNotice').textContent = state.template && state.template !== 'Blank' && state.templates && !(state.template_name in state.templates) ? 'Template ' + state.template + ' is preserved; its artwork is unavailable here.' : '';
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
  if (render.pageIndex !== state.index) {
    $('viewport').scrollTop = 0;
    $('viewport').scrollLeft = 0;
    render.pageIndex = state.index
  }
}

function resize() {
  let viewport = $('viewport'),
    style = getComputedStyle(viewport);
  const bounds = paperBounds();
  displayedPaperBounds = bounds;
  let fit = Math.max(.1, (viewport.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)) / bounds.width);
  let zoom = $('zoom').value,
    scale;
  if (zoom === 'page') {
    let available = viewport.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
    for (let id of ['warning', 'templateNotice']) {
      let notice = $(id),
        css = getComputedStyle(notice);
      available -= notice.getBoundingClientRect().height + (parseFloat(css.marginTop) || 0) + (parseFloat(css.marginBottom) || 0)
    }
    scale = Math.min(Math.max(1, viewport.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)) / bounds.width, Math.max(1, available) / bounds.height, 1);
  } else scale = zoom === 'fit' ? Math.min(fit, 1) : Number(zoom);
  canvas.style.width = (state.width * scale) + 'px';
  canvas.style.height = (state.height * scale) + 'px';
  const wrap = $('paperWrap'), layers = $('inkLayers'), background = $('pdfBackground');
  wrap.style.width = (bounds.width * scale) + 'px';
  wrap.style.height = (bounds.height * scale) + 'px';
  wrap.style.margin = paperView === 'move' ? '0 auto auto' : 'auto';
  layers.style.left = (-bounds.x * scale) + 'px';
  layers.style.width = (state.width * scale) + 'px';
  for (const [key, value] of Object.entries({left: -bounds.x * scale, top: 0,
    width: state.width * scale, height: state.height * scale})) background.style[key] = value + 'px';
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
  if (typeof updateZoomChrome === 'function') updateZoomChrome();
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
