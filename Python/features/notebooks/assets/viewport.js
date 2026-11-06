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
  panel.innerHTML = '<strong>Current page template</strong><p id="templateDescription" class="hint"></p><label>Page template <select id="pageTemplate" aria-label="Page template"></select></label>' +
    '<label id="templateFormatControl">Template format <select id="templateFormat" aria-label="Template format"><option value="pro">Paper Pro</option><option value="move">Paper Pro Move</option></select></label>' +
    '<label><input id="templateVisible" type="checkbox"> Show template</label>' +
    '<label>Paper view <select id="paperView" aria-label="Paper view"><option value="pro">Paper Pro</option><option value="move">Paper Pro Move</option></select></label>' +
    '<p id="templateCompatibility" class="hint"></p>' +
    '<p id="templateExportHint" class="hint" hidden>Save keeps editable template settings. Export Copy uses fixed PDF backgrounds for reMarkable; handwriting stays editable.</p>';
  const apply = () => {
    if (active !== null || busy) { render(); return }
    send({op: 'template', name: $('pageTemplate').value,
      format: $('templateFormat').value, visible: $('templateVisible').checked})
  };
  for (const id of ['pageTemplate', 'templateFormat', 'templateVisible']) $(id).onchange = apply;
  $('paperView').value = paperView;
  $('paperView').onchange = () => {
    if (active !== null) { $('paperView').value = paperView; return }
    defaultViewportZoom = false;
    resetViewportPosition = true;
    documentPaperView = paperView = $('paperView').value;
    resize();
  }
}

function paperBounds() {
  // Automatic phone framing magnifies the centered Move-width region without
  // cropping the rest of the native page. Stroke-dependent crop edges cannot
  // then clamp scrolling before that region reaches the viewport center.
  if (documentPaperView === null && defaultViewportZoom && mobileViewport() && paperView === 'move')
    return {x: 0, y: 0, width: state.width, height: state.height};
  if (state.pdf_paper) {
    const b = state.pdf_paper;
    return {x: Math.max(0, b.x), y: 0, width: Math.min(state.width, b.width), height: b.height}
  }
  if (paperView !== 'move' || !state.template_editable) return {x: 0, y: 0, width: state.width, height: state.height};
  const box = state.move_paper || {x: 291.5, y: 0, width: 821, height: 1460};
  let left = box.x, right = box.x + box.width, bottom = box.height;
  for (const image of state.images || []) for (const p of image.corners) { left=Math.min(left,p[0]);right=Math.max(right,p[0]);bottom=Math.max(bottom,p[1]) }
  for (const stroke of state.strokes) for (const p of stroke.points) {
    const radius = Math.max(0, p[3] || 0) / 2 + 2;
    left = Math.min(left, p[0] - radius); right = Math.max(right, p[0] + radius);
    bottom = Math.max(bottom, p[1] + radius)
  }
  left = Math.max(0, left); right = Math.min(state.width, right);
  return {x: left, y: 0, width: right - left, height: Math.min(state.height, bottom)}
}

function render() {
  if (typeof imageRender === 'function') imageRender();
  templateControls();
  if ($('pageTemplate')) {
    const name = state.template_name || state.template || 'Blank';
    $('templateCompatibility').textContent = state.template_notice || '';
    $('templateDescription').textContent = state.template_description || '';
    const catalog = new Map(Object.entries(state.templates || {Blank: 'Blank'}));
    if (!catalog.has(name)) catalog.set(name, name + ' (preserved)');
    options('pageTemplate', [...catalog].map(([value, label]) => [label, value]));
    $('pageTemplate').value = name;
    $('templateFormat').value = name.startsWith('Logistics ') ? (state.template_settings?.format || 'pro') : paperView;
    $('templateVisible').checked = state.template_settings?.visible !== false;
    const disabled = state.read_only || !state.template_editable || !Object.prototype.hasOwnProperty.call(state.templates || {}, name) || state.template_available === false;
    $('pageTemplate').disabled = state.read_only || !state.template_editable;
    const hasFormats = (state.template_formats || []).includes(name);
    $('templateFormatControl').hidden = !hasFormats || !state.template_editable || state.template_available === false;
    $('templateFormat').disabled = disabled || !hasFormats;
    $('templateVisible').disabled = disabled;
    $('templateExportHint').hidden = !state.template_editable || !(name.startsWith('Logistics ') || (name !== 'Blank' && !$('templateVisible').checked));
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
  $('templateNotice').textContent = state.template && state.template !== 'Blank' && state.templates &&
    (!Object.prototype.hasOwnProperty.call(state.templates, state.template_name) || state.template_available === false) ?
    'Template ' + state.template + ' is preserved; its artwork is unavailable here.' : '';
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
  if (render.pageIndex !== state.index) {
    resetViewportZoom(false);
    render.pageIndex = state.index
  }
  resize();
}

function resize() {
  const previousZoom = prepareViewportZoom();
  let viewport = $('viewport'),
    style = getComputedStyle(viewport);
  const bounds = paperBounds();
  displayedPaperBounds = bounds;
  const fitWidth = documentPaperView === null && defaultViewportZoom && mobileViewport() && paperView === 'move' ?
    (state.move_paper || {width: 821}).width : bounds.width;
  let fit = Math.max(.1, (viewport.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)) / fitWidth);
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
  } else scale = zoom === 'fit' ? Math.min(fit, mobileViewport() ? maxZoom : 1) : Number(zoom);
  canvas.style.width = (state.width * scale) + 'px';
  canvas.style.height = (state.height * scale) + 'px';
  const wrap = $('paperWrap'), layers = $('inkLayers'), background = $('pdfBackground');
  wrap.style.width = (bounds.width * scale) + 'px';
  wrap.style.height = (bounds.height * scale) + 'px';
  wrap.style.margin = paperView === 'move' ? '0 auto auto' : 'auto';
  layers.style.left = (-bounds.x * scale) + 'px';
  layers.style.width = (state.width * scale) + 'px';
  const imageBounds = state.pdf_paper || {x: 0, width: state.width, height: state.height};
  for (const [key, value] of Object.entries({left: (imageBounds.x - bounds.x) * scale, top: 0,
    width: imageBounds.width * scale, height: imageBounds.height * scale})) background.style[key] = value + 'px';
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
  finishViewportZoom(previousZoom);
  draw()
}

function previewErase(samples, radius = eraserRadius) {
  // Image pixels are immutable under the ink eraser; reconcile on acknowledgement.
  if (state.images?.length) return;
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

function paintBackground(target, image = $('pdfBackground')) {
  if (!state.background || !image.complete || !image.naturalWidth) return;
  const bounds = state.pdf_paper || {x: 0, y: 0, width: state.width, height: state.height};
  const scale = Math.min(bounds.width / image.naturalWidth, bounds.height / image.naturalHeight);
  const width = image.naturalWidth * scale, height = image.naturalHeight * scale;
  target.drawImage(image, bounds.x + (bounds.width - width) / 2,
    bounds.y + (bounds.height - height) / 2, width, height);
}

$('pdfBackground').addEventListener('load', () => draw());

function draw(highlight = mode === 'ink' ? activeHighlight() : null, region = null) {
  if (typeof imageRender === 'function') imageRender();
  clearDraft();
  ctx.clearRect(0, 0, state.width, state.height);
  // Blend ink with the PDF in scene order. The same image behind the canvas
  // stays visible through holes made by the temporary eraser preview.
  if (state.background) {
    ctx.fillStyle = 'white';
    ctx.fillRect(0, 0, state.width, state.height);
    paintBackground(ctx);
  }
  let visible = new Set(state.layers.filter(x => x[2]).map(x => x[0]));
  const items = sceneItems().filter(s => visible.has(s.layer));
  if (continuousInk)
    for (let action of queue)
      if (action.op === 'stroke') items.push({
        tool: action.tool,
        ...nativeColor(action.tool, action.color),
        points: strokePoints(action.points, action.tool, action.width)
      });
  if (pendingInk) items.push(pendingInk);
  if (highlight) items.push(highlight);
  paintOrderedInk(items, ctx, true, region);
  if (mode === 'capture' && points.length && !imageGesture) {
    ctx.save(); ctx.strokeStyle='#2877cb'; ctx.lineWidth=3; ctx.setLineDash([8,6]); ctx.beginPath(); ctx.moveTo(points[0][0],points[0][1]); for(const p of points.slice(1))ctx.lineTo(p[0],p[1]); ctx.stroke(); ctx.restore()
  }
  if (pendingErase) previewErase(pendingErase.points, pendingErase.radius);
  if (points.length && mode === 'erase' && eraserKind === 'partial') previewErase(points);
  if (points.length && mode === 'ink') {
    if (!highlight) preview(points);
    previewCount = points.length
  }
  if (typeof paintSelection === 'function') paintSelection();
}
