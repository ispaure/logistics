continuousInk = true;
// Desktop bounds work to display frames; mobile paints delivered pen batches immediately.
frameBatchedInk = true;
document.querySelectorAll('[data-icon]').forEach(el => el.insertAdjacentHTML('afterbegin', icon(glyphs[el.dataset.icon])));

function choice(parent, label, value, content, callback) {
  let b = document.createElement('button');
  b.type = 'button';
  b.title = label;
  b.setAttribute('aria-label', label);
  b.dataset.value = value;
  b.innerHTML = content;
  b.onclick = callback;
  $(parent).append(b);
  return b
}
for (let [name, value] of Object.entries(state.tools)) {
  let b = choice('brushes', name, value, icon(nibs[name] || glyphs.pen) + '<span></span>', () => {
    $('tool').value = value;
    $('tool').onchange();
    syncChrome()
  });
  b.className = 'brush';
  b.querySelector('span').textContent = name;
  b.title = name + ' (' + ($('brushes').children.length) + ')';
}
let swatchKey = '';

function syncSwatches() {
  let key = $('tool').value + ':' + $('grayscale').checked;
  if (key === swatchKey) return;
  swatchKey = key;
  $('swatches').replaceChildren();
  for (let option of $('color').options) {
    let name = option.textContent,
      value = Number(option.value),
      tool = Number($('tool').value);
    let rgb = swatchColor(tool, value);
    let b = choice('swatches', name, value, '', () => {
      $('color').value = value;
      syncChrome()
    });
    b.className = 'swatch';
    b.style.setProperty('--swatch', colorCss(rgb));
    b.style.setProperty('--check', rgb.reduce((a, b) => a + b, 0) < 350 ? '#fff' : '#203529');
  }
}
for (let [label, value] of Object.entries(state.widths)) {
  let b = choice('widths', label, value, '<i style="--weight:' + value + 'px"></i>', () => {
    $('width').value = value;
    syncChrome()
  });
  b.setAttribute('aria-label', label + ' stroke width');
}

function syncChrome() {
  syncSwatches();
  for (let [group, id] of [
      ['brushes', 'tool'],
      ['swatches', 'color'],
      ['widths', 'width']
    ])
    for (let b of $(group).children) b.setAttribute('aria-pressed', String(Number(b.dataset.value) === Number($(id).value) && (group !== 'brushes' || mode === 'ink')));
  for (let id of ['ink', 'erase', 'select']) {
    $(id).classList.toggle('active', mode === id);
    $(id).setAttribute('aria-pressed', String(mode === id))
  }
  $('toolHint').textContent = mode === 'erase' ? (eraserKind === 'whole' ? 'Erase whole strokes' : 'Erase parts of strokes') : mode === 'select' ? 'Select one stroke, then drag' : $('tool').selectedOptions[0]?.textContent || 'Choose your instrument';
  canvas.style.cursor = mode === 'select' ? 'move' : mode === 'erase' ? 'cell' : 'crosshair';
}
$('ink').onclick = () => {
  mode = 'ink';
  selected.clear();
  draw();
  syncChrome()
};
for (let id of ['erase', 'select', 'tool']) {
  let handler = $(id)[id === 'tool' ? 'onchange' : 'onclick'];
  $(id)[id === 'tool' ? 'onchange' : 'onclick'] = () => {
    handler();
    syncChrome()
  }
}
$('color').onchange = syncChrome;
$('width').onchange = syncChrome;
const grayChange = $('grayscale').onchange;
$('grayscale').onchange = () => {
  grayChange();
  syncChrome()
};
$('focus').onclick = () => document.body.classList.toggle('hide-toolbar');
let previewStart = 0;
function requestPagePreviews() {
  if (busy) return;
  $('morePages').disabled = true;
  $('overviewStatus').textContent = 'Loading thumbnails…';
  send({op: 'page-previews', start: previewStart})
}
$('pagesOverview').onclick = () => {
  if (busy || active !== null || $('pagesDialog').open) return;
  previewStart = 0;
  $('pagePreviews').replaceChildren();
  $('overviewCurrent').textContent = 'Current page: ' + (state.index + 1) + ' of ' + state.count;
  $('morePages').hidden = false;
  $('pagesDialog').showModal();
  requestPagePreviews()
};
$('closePages').onclick = () => $('pagesDialog').close();
$('morePages').onclick = requestPagePreviews;
$('overviewAdd').onclick = () => {
  if (busy) return;
  $('pagesDialog').close();
  send({op: 'add-page'})
};
window.notebookPagePreviews = rows => {
  if (!$('pagesDialog').open) return;
  for (let row of rows) {
    let card = document.createElement('button'), image = document.createElement('img'), caption = document.createElement('span');
    card.type = 'button';
    card.dataset.page = row.index;
    card.setAttribute('aria-label', 'Page ' + (row.index + 1) + (row.warning ? ': preview unavailable' : ''));
    card.setAttribute('aria-current', String(row.index === state.index));
    image.src = row.image;
    image.alt = '';
    caption.textContent = 'Page ' + (row.index + 1);
    card.append(image, caption);
    card.onclick = () => {
      if (busy) return;
      $('pagesDialog').close();
      send({op: 'page', index: row.index})
    };
    $('pagePreviews').append(card)
  }
  previewStart = rows.length ? rows.at(-1).index + 1 : previewStart;
  $('morePages').hidden = previewStart >= state.count;
  $('overviewStatus').textContent = ''
};
// Zoom the ink surface rather than the browser chrome. Preserve the page point
// under the wheel cursor, or the viewport center for keys and menu commands.
function setZoom(value, anchor = null) {
  if (active !== null) return;
  let numeric = Number(value);
  if (!['page', 'fit'].includes(value)) {
    if (!Number.isFinite(numeric) || numeric <= 0) return;
    value = String(Math.round(Math.min(4, Math.max(.1, numeric)) * 10000) / 10000);
    if (![...$('zoom').options].some(option => option.value === value)) {
      let custom = $('customZoom');
      if (!custom) {
        custom = document.createElement('option');
        custom.id = 'customZoom';
        $('zoom').append(custom)
      }
      custom.value = value;
      custom.textContent = Math.round(Number(value) * 100) + '%';
    }
  }
  let viewport = $('viewport'),
    box = viewport.getBoundingClientRect(),
    before = canvas.getBoundingClientRect();
  let x = anchor?.x ?? box.left + viewport.clientWidth / 2,
    y = anchor?.y ?? box.top + viewport.clientHeight / 2;
  let px = Math.max(0, Math.min(1, (x - before.left) / before.width)),
    py = Math.max(0, Math.min(1, (y - before.top) / before.height));
  $('zoom').value = value;
  resize();
  let after = canvas.getBoundingClientRect();
  viewport.scrollLeft += after.left + px * after.width - x;
  viewport.scrollTop += after.top + py * after.height - y;
}

function zoomBy(factor, anchor = null) {
  setZoom(canvas.getBoundingClientRect().width / state.width * factor, anchor)
}
$('zoom').onchange = () => setZoom($('zoom').value);
$('viewport').addEventListener('wheel', event => {
  if (!(event.ctrlKey || event.metaKey) || !event.deltaY) return;
  event.preventDefault();
  let delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? $('viewport').clientHeight : 1);
  zoomBy(Math.exp(Math.max(-1, Math.min(1, -delta * .002))), {
    x: event.clientX,
    y: event.clientY
  });
}, {
  passive: false
});
window.notebookViewState = () => ({
  toolbar: !document.body.classList.contains('hide-toolbar'),
  grayscale: $('grayscale').checked,
  finger: $('finger').checked
});
window.notebookUI = (name, value) => {
  if (active !== null) return;
  if (name === 'toolbar') {
    $('focus').click();
    return
  }
  if (name === 'zoom') {
    setZoom(value);
    return
  }
  if (name === 'zoom-in' || name === 'zoom-out') {
    zoomBy(name === 'zoom-in' ? 1.2 : 1 / 1.2);
    return
  }
  if (['grayscale', 'finger'].includes(name)) {
    $(name).checked = !$(name).checked;
    $(name).dispatchEvent(new Event('change'));
    return
  }
  $(name)?.click();
};
window.notebookCommand = action => {
  if (active !== null) return;
  if (['undo', 'redo'].includes(action.op) && document.activeElement?.matches('input,textarea,[contenteditable=true]')) {
    document.execCommand(action.op);
    return
  }
  send(action);
};
// Shared rendering updates the model controls; keep visual choices in step.
const baseUpdate = window.notebookUpdate;
window.notebookUpdate = (next, error) => {
  baseUpdate(next, error);
  $('morePages').disabled = false;
  if (error && $('pagesDialog').open) $('overviewStatus').textContent = error;
  syncChrome()
};
document.addEventListener('pointerdown', e => {
  for (let panel of document.querySelectorAll('details'))
    if (panel.open && !panel.contains(e.target)) panel.open = false
});
document.addEventListener('keydown', e => {
  if ($('pagesDialog').open || eraserDialog.open) return;
  let key = e.key.toLowerCase(),
    command = e.metaKey || e.ctrlKey;
  if (command && !e.altKey && ['+', '=', '-', '0'].includes(key)) {
    e.preventDefault();
    if (key === '0') setZoom('page');
    else zoomBy(key === '-' ? 1 / 1.2 : 1.2);
    return
  }
  if (e.target.closest?.('input,select,textarea,[contenteditable=true]')) {
    if (command && key === 's') {
      e.preventDefault();
      window.notebookCommand({
        op: e.shiftKey ? 'save-as' : 'save'
      })
    }
    return
  }
  if (key === 'escape') {
    document.querySelectorAll('details').forEach(panel => panel.open = false);
    selected.clear();
    $('ink').click();
    return
  }
  // WebEngine can retain editing shortcuts; delegate keys it receives to the
  // same queue as native menu actions. Qt-consumed shortcuts never reach here.
  if (command && !e.altKey && ['s', 'z', 'y'].includes(key)) {
    e.preventDefault();
    let op = key === 's' ? (e.shiftKey ? 'save-as' : 'save') : key === 'y' || e.shiftKey ? 'redo' : 'undo';
    window.notebookCommand({
      op
    });
    return
  }
  if (command || e.altKey || e.shiftKey || e.repeat) return;
  if (/^[1-9]$/.test(key)) {
    e.preventDefault();
    $('brushes').children[Number(key) - 1]?.click();
    return
  }
  let target = {
    b: 'ink',
    e: 'erase',
    v: 'select'
  } [key];
  if (target) {
    e.preventDefault();
    $(target).click()
  }
});
syncChrome();
