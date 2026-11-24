// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

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
  panel.innerHTML = `<p id="templateDescription" class="hint"></p>
    <button type="button" id="changeTemplate">Change Template…</button>
    <label>Paper view <select id="paperView" aria-label="Paper view"><option value="pro">Paper Pro</option><option value="move">Paper Pro Move</option></select></label>
    <p id="templateExportHint" class="hint" hidden>Save keeps editable template settings. Export Copy uses fixed PDF backgrounds for reMarkable; handwriting stays editable.</p>`;
  const dialog = document.createElement('dialog');
  dialog.id = 'templatePicker';
  dialog.setAttribute('aria-labelledby', 'templatePickerTitle');
  dialog.innerHTML = `<form>
    <h2 id="templatePickerTitle">Change Template</h2>
    <div class="template-settings">
      <label class="template-dropdown">Page template <span class="template-select"><select id="pageTemplate"></select></span></label>
      <fieldset class="template-list"><legend>Page template</legend><div id="templateChoices"></div></fieldset>
      <label>Template size <select id="templateFormat"><option value="pro">Paper Pro</option><option value="move">Paper Pro Move</option></select></label>
      <label><input id="templateVisible" type="checkbox"> Show template</label>
    </div>
    <div class="template-preview-pane">
      <figure id="templatePreview" role="img" aria-label="Template preview"><img alt="" decoding="async" hidden></figure>
      <p id="templatePreviewStatus" class="hint" role="status"></p>
    </div>
    <p id="templateCompatibility" class="hint"></p>
    <div class="template-actions"><button type="button" id="cancelTemplate">Cancel</button>
      <button type="submit" id="applyTemplate">Apply</button></div>
    </form>`;
  document.body.append(dialog);
  $('changeTemplate').onclick = openTemplatePicker;
  $('cancelTemplate').onclick = () => dialog.close();
  dialog.querySelector('form').onsubmit = event => {
    event.preventDefault();
    if (active !== null || busy || !state.template_editable || state.read_only ||
        dialog.dataset.page !== state.page_id || $('applyTemplate').disabled) return;
    dialog.close();
    send({op: 'template', name: $('pageTemplate').value,
      format: $('templateFormat').value, visible: $('templateVisible').checked, fixed_size: true});
  };
  for (const id of ['pageTemplate', 'templateFormat', 'templateVisible'])
    $(id).onchange = updateTemplatePreview;
  $('paperView').value = paperView;
  $('paperView').onchange = () => {
    if (active !== null) { $('paperView').value = paperView; return }
    defaultViewportZoom = false;
    resetViewportPosition = true;
    documentPaperView = paperView = $('paperView').value;
    if ($('zoom').value === 'compact-height') assignZoomValue('fit');
    resize();
  }
}

function openTemplatePicker() {
  const dialog = $('templatePicker');
  if (dialog.open || active !== null || !state.template_editable || state.read_only) return;
  const name = state.template_name || state.template || 'Blank';
  const catalog = Object.entries(state.templates);
  const known = Object.hasOwn(state.templates, name);
  const unavailable = state.template_available === false || !known;
  if (unavailable) catalog.unshift(['', (known ? state.templates[name] : name) + ' (preserved)']);
  options('pageTemplate', catalog.map(([value, label]) => [label, value]));
  const choices = $('templateChoices');
  choices.replaceChildren(...catalog.map(([value, label]) => {
    const row = document.createElement('label');
    const radio = document.createElement('input');
    const caption = document.createElement('span');
    radio.type = 'radio';
    radio.name = 'template-choice';
    radio.value = value;
    radio.onchange = () => {
      $('pageTemplate').value = value;
      updateTemplatePreview();
    };
    caption.textContent = label;
    row.append(radio, caption);
    return row;
  }));
  $('pageTemplate').value = unavailable ? '' : name;
  $('templateFormat').value = state.template_fixed_size ? state.template_settings.format : paperView;
  $('templateVisible').checked = state.template_settings?.visible !== false;
  $('templateCompatibility').textContent = state.template_notice || '';
  dialog.dataset.page = state.page_id;
  dialog.showModal();
  updateTemplatePreview();
  const initial = $('pageTemplate').getClientRects().length ? $('pageTemplate') : choices.querySelector(':checked');
  initial?.focus();
}

function updateTemplatePreview() {
  const name = $('pageTemplate').value;
  for (const choice of $('templateChoices').querySelectorAll('input')) choice.checked = choice.value === name;
  const move = $('templateFormat').value === 'move';
  const preview = $('templatePreview');
  const image = preview.querySelector('img');
  const bounds = move ? state.move_paper : state.template_bounds;
  const candidates = Object.hasOwn(templateArtwork, name) ? templateArtwork[name] : null;
  $('applyTemplate').disabled = $('templateVisible').disabled = $('templateFormat').disabled = !candidates;
  $('templatePreviewStatus').textContent = candidates ? '' : 'Template artwork unavailable.';
  preview.style.aspectRatio = bounds.width + ' / ' + bounds.height;
  const source = $('templateVisible').checked && (candidates?.[move ? 1 : 0] || candidates?.[0]);
  image.hidden = !source;
  if (!source) {
    image.removeAttribute('src');
    return;
  }
  image.style.width = (state.template_bounds.width / bounds.width * 100) + '%';
  image.style.left = (-bounds.x / bounds.width * 100) + '%';
  if (image.getAttribute('src') !== source) image.src = source;
}

function paperBounds() {
  // Automatic phone framing magnifies the centered Move-width region without
  // cropping the rest of the native page. Stroke-dependent crop edges cannot
  // then clamp scrolling before that region reaches the viewport center.
  const phoneStrip = documentPaperView === null && defaultViewportZoom && mobileViewport() &&
    paperView === 'move' && $('zoom').value === 'fit';
  if (phoneStrip && !state.pdf_paper)
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

function confirmLayerDeletion(key, name) {
  let dialog = $('deleteLayerDialog');
  if (!dialog) {
    dialog = document.createElement('dialog');
    dialog.id = 'deleteLayerDialog';
    dialog.setAttribute('aria-labelledby', 'deleteLayerTitle');
    dialog.innerHTML = '<form method="dialog"><h2 id="deleteLayerTitle">Delete layer?</h2>' +
      '<p id="deleteLayerMessage"></p><div class="template-actions">' +
      '<button value="cancel" autofocus>Cancel</button><button value="delete" class="layer-remove">Delete layer</button></div></form>';
    document.body.append(dialog);
  }
  if (dialog.open) return;
  $('deleteLayerMessage').textContent = `Delete “${name}” and its contents? You can undo this change.`;
  const page = state.page_id;
  const confirmDelete = event => {
    if (event.submitter?.value === 'delete' && !busy && page === state.page_id)
      send({op: 'delete-layer', layer: key});
  };
  dialog.querySelector('form').onsubmit = confirmDelete;
  dialog.showModal();
}

function bindLayerReorder(handle, row) {
  let hold, drag, drop, after;
  function clear() {
    clearTimeout(hold);
    row.classList.remove('layer-dragging');
    drop?.classList.remove('layer-drop-before', 'layer-drop-after');
    drag = drop = null;
  }
  function move(target, after) {
    if (!target || target === row || busy || active !== null ||
        target === (after ? row.previousElementSibling : row.nextElementSibling)) return;
    send({op: 'move-layer', layer: row.dataset.layer, target: target.dataset.layer, after});
  }
  handle.onpointerdown = event => {
    if (event.button !== 0 || busy || active !== null) return;
    drag = {id: event.pointerId, x: event.clientX, y: event.clientY, page: state.page_id};
    handle.setPointerCapture(event.pointerId);
    hold = setTimeout(() => row.classList.add('layer-dragging'), 350);
  };
  handle.onpointermove = event => {
    if (drag?.id !== event.pointerId) return;
    if (!row.classList.contains('layer-dragging')) {
      if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 8) clear();
      return;
    }
    drop?.classList.remove('layer-drop-before', 'layer-drop-after');
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('.layer-row');
    drop = target && target !== row && target.parentElement === row.parentElement ? target : null;
    if (drop) {
      const bounds = drop.getBoundingClientRect();
      after = event.clientY > bounds.top + bounds.height / 2;
      drop.classList.add(after ? 'layer-drop-after' : 'layer-drop-before');
    }
  };
  handle.onpointerup = event => {
    if (drag?.id === event.pointerId && drag.page === state.page_id) move(drop, after);
    clear();
  };
  handle.onpointercancel = handle.onlostpointercapture = clear;
  handle.oncontextmenu = event => event.preventDefault();
  handle.onkeydown = event => {
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
    event.preventDefault();
    const down = event.key === 'ArrowDown';
    move(down ? row.nextElementSibling : row.previousElementSibling, down);
  };
}

function renderLayerRows() {
  const rows = $('layerRows'), activeLayer = $('layer');
  if (!rows) return;
  const focused = document.activeElement;
  const previous = new Map([...rows.children].map(row => [row.dataset.layer, row]));
  const visibilityLocked = !!(state.read_only || state.warning || state.password_required);
  for (const [index, [key, name, visible]] of state.layers.entries()) {
    let row = previous.get(key);
    if (!row) {
      row = document.createElement('div');
      row.className = 'layer-row';
      row.dataset.layer = key;
      for (const className of ['layer-grip', 'layer-choice', 'layer-eye', 'layer-remove']) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = className;
        row.append(button);
      }
      bindLayerReorder(row.firstChild, row);
    }
    const current = rows.children[index];
    if (current !== row) rows.insertBefore(row, current || null);
    previous.delete(key);
    const [grip, choose, eye, remove] = row.children;
    grip.textContent = '⠿';
    grip.title = 'Hold and drag to move ' + name;
    grip.setAttribute('aria-label', 'Move ' + name + ' with the Up or Down arrow');
    grip.disabled = visibilityLocked || state.layers.length < 2;
    remove.textContent = '−';
    remove.title = 'Delete ' + name;
    remove.setAttribute('aria-label', remove.title);
    remove.disabled = grip.disabled;
    remove.onclick = () => confirmLayerDeletion(key, name);
    const selected = activeLayer.value === key;
    choose.textContent = name;
    choose.setAttribute('aria-pressed', String(selected));
    choose.disabled = !visible;
    choose.onclick = () => {
      activeLayer.value = key;
      renderLayerRows();
    };
    eye.innerHTML = icon(visible ? glyphs.eye : glyphs.eyeOff);
    eye.title = (visible ? 'Hide ' : 'Show ') + name;
    eye.setAttribute('aria-label', eye.title);
    eye.disabled = visibilityLocked;
    eye.onclick = () => {
      if (!queue.some(action => action.op === 'layer-visible' && action.layer === key))
        send({op: 'layer-visible', layer: key, visible: !visible});
    };
  }
  for (const row of previous.values()) row.remove();
  if (focused?.isConnected && rows.contains(focused) && !focused.disabled) focused.focus();
}

function render() {
  if (typeof imageRender === 'function') imageRender();
  templateControls();
  if ($('templatePicker')) {
    const editable = state.template_editable && !state.read_only;
    $('changeTemplate').hidden = !editable;
    $('templateDescription').textContent = state.template_description || '';
    const dialog = $('templatePicker');
    if (dialog.open && (!editable || dialog.dataset.page !== state.page_id)) dialog.close();
    const name = state.template_name || state.template || 'Blank';
    $('templateExportHint').hidden = !state.template_editable ||
      !(name.startsWith('Logistics ') || (name !== 'Blank' && state.template_settings?.visible === false));
  }
  const background = $('pdfBackground');
  background.hidden = !state.background;
  if (state.background) {
    if (background.getAttribute('src') !== state.background) background.src = state.background;
  } else background.removeAttribute('src');
  $('title').textContent = state.display_name ?? state.name;
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
  options('tool', Object.entries(state.tools));
  brushOptions();
  options('layer', state.layers.filter(x => x[2]).map(x => [x[1], x[0]]));
  renderLayerRows();
  $('prev').onclick = () => send({
    op: 'page',
    index: state.index - 1
  });
  $('next').onclick = () => send({
    op: 'page',
    index: state.index + 1
  });
  if (render.pageIndex !== state.index) {
    if (explicitPageFraming()) resetViewportPosition = true;
    else resetViewportZoom(false);
    render.pageIndex = state.index
  }
  resize();
}

function pageViewportSpace() {
  const viewport = $('viewport'), style = getComputedStyle(viewport);
  const availableWidth = Math.max(1, viewport.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight));
  let availableHeight = viewport.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
  for (const id of ['warning', 'templateNotice']) {
    const notice = $(id), css = getComputedStyle(notice);
    availableHeight -= notice.getBoundingClientRect().height + (parseFloat(css.marginTop) || 0) + (parseFloat(css.marginBottom) || 0)
  }
  return {width: availableWidth, height: Math.max(1, availableHeight)}
}

function resize() {
  const previousZoom = prepareViewportZoom();
  const bounds = paperBounds();
  displayedPaperBounds = bounds;
  const zoom = $('zoom').value;
  const {width: availableWidth, height: availableHeight} = pageViewportSpace();
  let heightFit = availableHeight / bounds.height;
  let fitWidth = bounds.width;
  if (documentPaperView === null && defaultViewportZoom && mobileViewport()) {
    if (paperView === 'move' && zoom === 'fit') fitWidth = compactPaper().width;
    else if (fitLandscapePdf()) fitWidth = backgroundContentBounds()?.width ?? bounds.width;
  }
  let scale;
  if (zoom === 'page' || zoom === 'fill') scale = pageZoomScale(zoom, availableWidth / bounds.width, heightFit);
  else if (zoom === 'compact-height') scale = Math.min(availableHeight / compactPaper().height, maxZoom);
  else if (zoom === 'fit') scale = Math.min(availableWidth / fitWidth, mobileViewport() ? maxZoom : 1);
  else scale = Number(zoom);
  const wrap = $('paperWrap'), layers = $('inkLayers'), background = $('pdfBackground');
  wrap.style.margin = mobileViewport() || paperView === 'move' ? '0 auto auto' : 'auto';
  function sizePaper() {
    wrap.style.width = (bounds.width * scale) + 'px';
    wrap.style.height = (bounds.height * scale) + 'px';
  }
  sizePaper();
  if (explicitPageFraming()) {
    // Desktop scrollbars can appear for Fill and disappear for Fit. Measure
    // the resulting viewport before sizing or repainting the backing canvases.
    const space = pageViewportSpace();
    if (space.width !== availableWidth || space.height !== availableHeight) {
      heightFit = space.height / bounds.height;
      scale = pageZoomScale(zoom, space.width / bounds.width, heightFit);
      sizePaper();
    }
  }
  canvas.style.width = (state.width * scale) + 'px';
  canvas.style.height = (state.height * scale) + 'px';
  layers.style.left = (-bounds.x * scale) + 'px';
  layers.style.width = (state.width * scale) + 'px';
  const imageBounds = backgroundPaperBounds();
  for (const [key, value] of Object.entries({left: (imageBounds.x - bounds.x) * scale, top: imageBounds.y * scale,
    width: imageBounds.width * scale, height: imageBounds.height * scale})) background.style[key] = value + 'px';
  let ratio = Math.min(devicePixelRatio || 1, 2);
  let backingScale = Math.min(scale * ratio, Math.sqrt(canvasPixelLimit / (state.width * state.height))),
    width = Math.max(1, Math.floor(state.width * backingScale)),
    height = Math.max(1, Math.floor(state.height * backingScale));
  // Assigning unchanged dimensions also reallocates canvas storage. A page
  // change needs a redraw, not three replacement GPU-backed bitmaps.
  const backingChanged = canvas.width !== width || canvas.height !== height;
  if (backingChanged) {
    canvas.width = width;
    canvas.height = height
  }
  if (backingChanged || resize.nativeWidth !== state.width || resize.nativeHeight !== state.height) {
    ctx.setTransform(canvas.width / state.width, 0, 0, canvas.height / state.height, 0, 0);
    sizeDraft();
    resize.nativeWidth = state.width;
    resize.nativeHeight = state.height
  }
  if (typeof updateZoomChrome === 'function') updateZoomChrome(heightFit);
  finishViewportZoom(previousZoom);
  draw()
}

function previewErase(samples, radius = pageEraserRadius()) {
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

function backgroundContentBounds(image = $('pdfBackground')) {
  if (!state.background || !image.complete || !image.naturalWidth) return null;
  return containedBackgroundBounds(image, backgroundPaperBounds());
}

function backgroundPaperBounds() {
  return state.pdf_paper || state.template_bounds || {x: 0, y: 0, width: state.width, height: state.height};
}

function containedBackgroundBounds(image, bounds) {
  const scale = Math.min(bounds.width / image.naturalWidth, bounds.height / image.naturalHeight);
  const width = image.naturalWidth * scale, height = image.naturalHeight * scale;
  return {x: bounds.x + (bounds.width - width) / 2, y: bounds.y + (bounds.height - height) / 2,
    width, height};
}

function paintBackground(target, image = $('pdfBackground')) {
  const bounds = backgroundContentBounds(image);
  if (bounds) target.drawImage(image, bounds.x, bounds.y, bounds.width, bounds.height);
}

function invertPaper(target, width, height) {
  target.save();
  target.globalCompositeOperation = 'difference';
  target.fillStyle = 'white';
  target.fillRect(0, 0, width, height);
  target.restore();
}

function fitLandscapePdf() {
  return $('zoom').value === 'fit' && !state.template_editable && !!state.background && innerWidth > innerHeight &&
    !document.body.classList.contains('notebook-laptop');
}

$('pdfBackground').addEventListener('load', () => {
  if (mobileViewport() && documentPaperView === null && defaultViewportZoom && fitLandscapePdf()) {
    resetViewportPosition = true;
    scheduleViewportResize();
  } else draw();
});

function draw(highlight = mode === 'ink' ? activeHighlight() : null, region = null) {
  if (typeof imageRender === 'function') imageRender();
  clearDraft();
  ctx.clearRect(0, 0, state.width, state.height);
  const dark = darkNotebookPaper();
  // Blend ink with the PDF in scene order. The same image behind the canvas
  // stays visible through holes made by the temporary eraser preview.
  if (state.background) {
    ctx.fillStyle = 'white';
    ctx.fillRect(0, 0, state.width, state.height);
    paintBackground(ctx);
    if (dark) invertPaper(ctx, state.width, state.height);
  }
  let visible = new Set(state.layers.filter(x => x[2]).map(x => x[0]));
  const items = sceneItems(selectionStrokes(), selectionPictures()).filter(s => visible.has(s.layer) && !wholeErasePreview.has(s.id));
  if (continuousInk)
    for (let action of queue)
      if (action.op === 'stroke') items.push({
        tool: action.tool,
        ...nativeColor(action.tool, action.color),
        points: strokePoints(action.points, action.tool, action.width)
      });
  if (pendingInk) items.push(pendingInk);
  if (highlight) items.push(highlight);
  paintOrderedInk(items, ctx, true, region, null, dark);
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
