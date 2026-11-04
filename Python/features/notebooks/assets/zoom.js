// All zoom paths resize the paper, never the toolbar or the document geometry.
const minZoom = .1, maxZoom = 4;
let appliedZoom = $('zoom').value;
let defaultViewportZoom = true, viewportZoomMemory = null, resetViewportPosition = true;
function mobileViewport() {
  return document.body.classList.contains('notebook-mobile')
}
function viewportLayoutKey() {
  const viewport = $('viewport');
  return [viewport.clientWidth, viewport.clientHeight, innerWidth, innerHeight,
    document.body.classList.contains('notebook-laptop')].join(':')
}
function defaultViewportChoice() {
  if (!mobileViewport()) return {view: paperView, zoom: 'fit'};
  if (document.body.classList.contains('notebook-laptop')) return {view: 'pro', zoom: 'fit'};
  if (innerWidth > innerHeight) return {view: 'pro', zoom: 'fit'};
  return state.tablet === true || innerWidth >= 700 ? {view: 'pro', zoom: 'page'} : {view: 'move', zoom: 'fit'}
}
function assignZoomValue(value) {
  value = String(value);
  if (![...$('zoom').options].some(option => option.value === value)) {
    let custom = $('customZoom');
    if (!custom) {
      custom = document.createElement('option');
      custom.id = 'customZoom';
      $('zoom').append(custom)
    }
    custom.value = value;
    custom.textContent = Number.isFinite(Number(value)) ? Math.round(Number(value) * 100) + '%' : 'Fit page'
  }
  $('zoom').value = value
}
function rememberViewportZoom() {
  const viewport = $('viewport'), box = viewport.getBoundingClientRect(), rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  viewportZoomMemory = {layout: viewportLayoutKey(), scale: rect.width / state.width,
    point: [(box.left + viewport.clientWidth / 2 - rect.left) / rect.width,
      (box.top + viewport.clientHeight / 2 - rect.top) / rect.height]}
}
function captureViewportZoom() {
  if (!viewportZoomMemory || viewportZoomMemory.layout === viewportLayoutKey()) rememberViewportZoom();
  return {manual: !defaultViewportZoom, memory: viewportZoomMemory}
}
function prepareViewportZoom() {
  const changed = viewportZoomMemory && viewportZoomMemory.layout !== viewportLayoutKey();
  // Explicit fit selections remain fits. Numeric zoom is the user's magnified
  // page scale, which should survive a new window/posture without snapping out.
  const previous = changed && !defaultViewportZoom && !['page', 'fit'].includes($('zoom').value) ? viewportZoomMemory : null;
  if (defaultViewportZoom) {
    const choice = defaultViewportChoice();
    if (paperView !== choice.view || changed) resetViewportPosition = true;
    paperView = choice.view;
    if ($('paperView')) $('paperView').value = paperView;
    assignZoomValue(choice.zoom)
  } else if (previous) assignZoomValue(previous.scale);
  return previous
}
function finishViewportZoom(previous) {
  const viewport = $('viewport'), rect = canvas.getBoundingClientRect(), box = viewport.getBoundingClientRect();
  if (previous) {
    viewport.scrollLeft += rect.left + previous.point[0] * rect.width - box.left - viewport.clientWidth / 2;
    viewport.scrollTop += rect.top + previous.point[1] * rect.height - box.top - viewport.clientHeight / 2
  } else if (resetViewportPosition) {
    // Center the canonical Move strip independently of existing ink and the
    // full native page which remains reachable by panning.
    const move = state.move_paper || {x: 291.5, width: 821};
    viewport.scrollLeft += rect.left + (paperView === 'move' ? move.x + move.width / 2 : state.width / 2) * rect.width / state.width - box.left - viewport.clientWidth / 2;
    viewport.scrollTop = 0
  }
  resetViewportPosition = false;
  rememberViewportZoom()
}
function resetViewportZoom(resizeNow = true) {
  if (active !== null) return;
  defaultViewportZoom = true;
  viewportZoomMemory = null;
  resetViewportPosition = true;
  if (resizeNow) resize()
}
function restoreViewportZoom(snapshot) {
  defaultViewportZoom = !snapshot.manual;
  viewportZoomMemory = snapshot.memory;
  resize()
}
function updateZoomChrome() {
  appliedZoom = $('zoom').value;
  const scale = canvas.getBoundingClientRect().width / state.width;
  const label = Math.round(scale * 100) + '%';
  if ($('zoomLevel') && $('zoomLevel').textContent !== label) $('zoomLevel').textContent = label;
  if ($('zoomOut')) $('zoomOut').disabled = scale <= minZoom + .0001;
  if ($('zoomIn')) $('zoomIn').disabled = scale >= maxZoom - .0001
}
function setZoom(value, anchor = null, paperPoint = null) {
  if (active !== null) {
    $('zoom').value = appliedZoom;
    return
  }
  let numeric = Number(value);
  if (!['page', 'fit'].includes(value)) {
    if (!Number.isFinite(numeric) || numeric <= 0) return;
    value = String(Math.round(Math.min(maxZoom, Math.max(minZoom, numeric)) * 10000) / 10000);
  }
  const viewport = $('viewport'), box = viewport.getBoundingClientRect(), before = canvas.getBoundingClientRect();
  const x = anchor?.x ?? box.left + viewport.clientWidth / 2,
    y = anchor?.y ?? box.top + viewport.clientHeight / 2;
  const px = paperPoint?.[0] ?? Math.max(0, Math.min(1, (x - before.left) / before.width)),
    py = paperPoint?.[1] ?? Math.max(0, Math.min(1, (y - before.top) / before.height));
  // Move is the default phone framing, not a permanent crop. Once the user
  // magnifies that framing, make the full native paper available for panning;
  // the old paper anchor below keeps the viewed area in the same place.
  if (defaultViewportZoom && mobileViewport() && !['page', 'fit'].includes(value)) {
    paperView = 'pro';
    if ($('paperView')) $('paperView').value = paperView
  }
  defaultViewportZoom = false;
  resetViewportPosition = false;
  assignZoomValue(value);
  // This explicit zoom has its own anchor; it must not restore a stale layout
  // snapshot if the user pinches just after an orientation change.
  viewportZoomMemory = null;
  resize();
  const after = canvas.getBoundingClientRect();
  viewport.scrollLeft += after.left + px * after.width - x;
  viewport.scrollTop += after.top + py * after.height - y;
  rememberViewportZoom()
}
function zoomBy(factor, anchor = null) {
  setZoom(canvas.getBoundingClientRect().width / state.width * factor, anchor)
}
window.notebookNativeZoom = (factor, x, y) => {
  if (document.elementFromPoint(x, y)?.closest('#viewport')) zoomBy(factor, {x, y})
};
function createZoomControls(container) {
  container.id = 'zoomControls';
  container.className = 'zoom-controls';
  container.setAttribute('role', 'group');
  container.setAttribute('aria-label', 'Page zoom');
  container.innerHTML = '<button id="zoomOut" type="button" aria-label="Zoom out" title="Zoom out">−</button><output id="zoomLevel" aria-label="Current zoom"></output><button id="zoomIn" type="button" aria-label="Zoom in" title="Zoom in">+</button><button id="zoomFit" type="button" title="Reset zoom" aria-label="Reset zoom">Reset</button>';
  $('zoomOut').onclick = () => zoomBy(1 / 1.2);
  $('zoomIn').onclick = () => zoomBy(1.2);
  $('zoomFit').onclick = () => resetViewportZoom();
  updateZoomChrome()
}
$('zoom').onchange = () => setZoom($('zoom').value);
const zoomViewport = $('viewport');
zoomViewport.addEventListener('scroll', () => {
  if (!viewportZoomMemory || viewportZoomMemory.layout === viewportLayoutKey()) rememberViewportZoom()
}, {passive: true});
let trackpadGesture = null;
zoomViewport.addEventListener('wheel', event => {
  if (!(event.ctrlKey || event.metaKey) || !event.deltaY) return;
  event.preventDefault();
  if (trackpadGesture) return;
  const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? zoomViewport.clientHeight : 1);
  zoomBy(Math.exp(Math.max(-1, Math.min(1, -delta * .002))), {x: event.clientX, y: event.clientY})
}, {passive: false});
// Safari reports trackpad pinches as GestureEvents; Chromium uses Ctrl+wheel.
zoomViewport.addEventListener('gesturestart', event => {
  event.preventDefault();
  if (active !== null || touchContacts.size) return;
  const rect = canvas.getBoundingClientRect();
  trackpadGesture = {scale: rect.width / state.width,
    point: [(event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height]}
}, {passive: false});
zoomViewport.addEventListener('gesturechange', event => {
  event.preventDefault();
  if (trackpadGesture) setZoom(trackpadGesture.scale * event.scale,
    {x: event.clientX, y: event.clientY}, trackpadGesture.point)
}, {passive: false});
zoomViewport.addEventListener('gestureend', event => {
  event.preventDefault();
  trackpadGesture = null
}, {passive: false});

const touchContacts = new Map();
let touchPinch = null, pinchFrame = null, touchZoomBlocked = false;
function cancelTouchZoom() {
  if (touchContacts.has(active)) finish({pointerId: active}, true);
  if (pan && touchContacts.has(pan.id)) pan = null;
  if (pinchFrame !== null) cancelAnimationFrame(pinchFrame);
  pinchFrame = null;
  touchPinch = null;
  touchContacts.clear();
  touchZoomBlocked = false;
  trackpadGesture = null
}
function touchPair() {
  const pair = touchPinch.ids.map(id => touchContacts.get(id));
  if (pair.some(point => !point)) return null;
  return {x: (pair[0].x + pair[1].x) / 2, y: (pair[0].y + pair[1].y) / 2,
    distance: Math.hypot(pair[0].x - pair[1].x, pair[0].y - pair[1].y)}
}
function applyTouchPinch() {
  pinchFrame = null;
  if (!touchPinch) return;
  const pair = touchPair();
  if (pair) setZoom(touchPinch.scale * pair.distance / touchPinch.distance, pair, touchPinch.point)
}
zoomViewport.addEventListener('pointerdown', event => {
  if (event.pointerType !== 'touch') return;
  // Ignore palms while a pen or mouse stroke owns the page.
  if (active !== null && !touchContacts.has(active)) return;
  event.preventDefault();
  touchContacts.set(event.pointerId, {x: event.clientX, y: event.clientY});
  if (touchContacts.size >= 2 && !touchPinch) {
    // A second finger changes a finger-drawn preview into a zoom, without saving ink.
    if (active !== null) finish({pointerId: active}, true);
    pan = null;
    touchZoomBlocked = true;
    touchPinch = {ids: [...touchContacts.keys()].slice(0, 2)};
    const pair = touchPair(), rect = canvas.getBoundingClientRect();
    Object.assign(touchPinch, {distance: Math.max(1, pair.distance), scale: rect.width / state.width,
      point: [(pair.x - rect.left) / rect.width, (pair.y - rect.top) / rect.height]})
  }
  if (touchZoomBlocked) {
    event.preventDefault();
    event.stopImmediatePropagation();
    if (event.isTrusted) zoomViewport.setPointerCapture(event.pointerId)
  } else if (event.target !== canvas && active === null) {
    beginPan(event, zoomViewport)
  }
}, {capture: true, passive: false});
zoomViewport.addEventListener('pointermove', event => {
  if (!touchContacts.has(event.pointerId)) return;
  touchContacts.set(event.pointerId, {x: event.clientX, y: event.clientY});
  if (!touchZoomBlocked) {
    if (event.target !== canvas && pan?.id === event.pointerId) canvas.onpointermove(event);
    return
  }
  event.preventDefault();
  event.stopImmediatePropagation();
  if (touchPinch && pinchFrame === null) pinchFrame = requestAnimationFrame(applyTouchPinch)
}, {capture: true, passive: false});
function finishTouchZoom(event) {
  if (!touchContacts.has(event.pointerId)) return;
  if (touchZoomBlocked) {
    if (pinchFrame !== null) {
      cancelAnimationFrame(pinchFrame);
      applyTouchPinch()
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    if (touchPinch?.ids.includes(event.pointerId)) touchPinch = null
  } else if (event.target !== canvas && pan?.id === event.pointerId) {
    finish(event, event.type !== 'pointerup')
  }
  touchContacts.delete(event.pointerId);
  if (!touchContacts.size) touchZoomBlocked = false
}
for (const name of ['pointerup', 'pointercancel', 'lostpointercapture'])
  zoomViewport.addEventListener(name, finishTouchZoom, {capture: true, passive: false});
window.addEventListener('blur', cancelTouchZoom);

// Native desktop palette changes recolor chrome without reloading unsaved ink.
window.notebookAppearance = stylesheet => {
  let style = $('notebookAppearance');
  if (!style) {
    style = document.createElement('style');
    style.id = 'notebookAppearance';
    document.head.append(style)
  }
  style.textContent = stylesheet
};
