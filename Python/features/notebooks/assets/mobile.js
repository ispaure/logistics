(function() {

  continuousInk = true;
  pageSwipe = true;
  const svg = icon,
    brushNib = value => nibs[Object.keys(state.tools).find(name => String(state.tools[name]) === String(value))] || glyphs.pen;
  const icons = {
    ...glyphs,
    back: glyphs.prev,
    pages: glyphs.panel,
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    hide: '<path d="m7 10 5 5 5-5M5 20h14"/>'
  };

  function iconButton(button, key, label, caption) {
    button.className = 'icon';
    button.innerHTML = svg(icons[key] || brushNib(key)) + (caption ? '<small>' + caption + '</small>' : '');
    button.setAttribute('aria-label', label);
    button.title = label;
    return button
  }

  function makeButton(key, label, handler, caption) {
    let b = document.createElement('button');
    b.type = 'button';
    b.onclick = handler;
    return iconButton(b, key, label, caption)
  }
  let header = document.querySelector('header'),
    old = document.createElement('div');
  while (header.firstChild) old.append(header.firstChild);
  let buttons = [...old.querySelectorAll('button')];
  const command = op => buttons.find(b => b.dataset.action === op);
  // Cache controls while detached so each original handler and input value survives.
  const ids = {};
  for (let el of old.querySelectorAll('[id]')) ids[el.id] = el;

  function control(id) {
    return ids[id] || $(id)
  }
  header.className = 'mobile-head';
  if (state.native_close) command('library').hidden = true;
  let more = makeButton('more', 'Notebook actions', e => sheet.hidden ? openSheet('document', e.currentTarget) : closeSheet());
  header.append(iconButton(command('library'), 'close', 'Close document'), more);
  let dock = document.createElement('nav');
  dock.className = 'mobile-dock';
  dock.setAttribute('aria-label', 'Drawing and page tools');
  header.insertBefore(dock, more);
  let tools = document.createElement('div');
  tools.className = 'mobile-tools';
  dock.append(tools);
  let brushToggle = makeButton(17, 'Brush, color and width', () => {
    if (!sheet.hidden && sheet.dataset.panel === 'brush') {
      closeSheet();
      return
    }
    if (mode !== 'ink') {
      control('tool').onchange();
      selected.clear();
      draw();
      sync()
    }
    openSheet('brush', brushToggle)
  }, 'Pen');
  brushToggle.id = 'brushToggle';
  brushToggle.setAttribute('aria-haspopup', 'dialog');
  brushToggle.setAttribute('aria-expanded', 'false');
  tools.append(brushToggle);
  for (let [id, label] of [
      ['erase', 'Erase'],
      ['select', 'Move'],
      ['undo', 'Undo'],
      ['redo', 'Redo']
    ]) tools.append(iconButton(control(id), id, id === 'select' ? 'Select / move' : label, label));
  let hideTools = makeButton('hide', 'Hide tools', () => setToolsHidden(true));
  hideTools.id = 'hideTools';

  let restore = makeButton('pen', 'Show tools', () => setToolsHidden(false));
  restore.id = 'restoreTools';
  restore.hidden = true;
  document.body.append(restore);

  function setToolsHidden(hidden) {
    if (active !== null) return;
    document.body.classList.toggle('tools-hidden', hidden);
    restore.hidden = !hidden;
    (hidden ? restore : more).focus()
  }
  let pages = document.createElement('div');
  pages.className = 'mobile-pages';
  pages.append(iconButton(control('prev'), 'back', 'Previous page'), control('pageinfo'), iconButton(control('next'), 'next', 'Next page'));
  let pagesToggle = makeButton('pages', 'Pages Overview', e => openSheet('pages', e.currentTarget), 'Pages Overview');
  pagesToggle.id = 'pagesToggle';
  let layersToggle = makeButton('layers', 'Layers', e => openSheet('layers', e.currentTarget), 'Layers');
  layersToggle.id = 'layersToggle';
  let backdrop = document.createElement('div');
  backdrop.id = 'mobileBackdrop';
  backdrop.hidden = true;
  document.body.append(backdrop);
  let sheet = document.createElement('section');
  sheet.id = 'mobileSheet';
  sheet.hidden = true;
  sheet.setAttribute('role', 'dialog');
  sheet.setAttribute('aria-modal', 'true');
  sheet.setAttribute('aria-labelledby', 'sheetTitle');
  sheet.innerHTML = '<div class="sheet-heading"><h2 id="sheetTitle"></h2></div><div class="sheet-scroll"></div>';
  document.body.append(sheet);
  let closer = makeButton('close', 'Close panel', closeSheet);
  sheet.firstChild.append(closer);
  let panels = {},
    returnFocus = null;
  const names = {
    brush: 'Writing tools',
    layers: 'Layers',
    pages: 'Pages Overview',
    document: 'Notebook',
    view: 'View and input'
  };
  for (let key of Object.keys(names)) {
    let panel = document.createElement('div');
    panel.className = 'sheet-panel';
    panel.hidden = true;
    sheet.lastChild.append(panel);
    panels[key] = panel
  }

  function heading(panel, text) {
    let h = document.createElement('h3');
    h.textContent = text;
    panel.append(h)
  }

  function field(panel, text, el) {
    let label = document.createElement('label');
    label.className = 'field';
    label.append(document.createTextNode(text), el);
    panel.append(label)
  }

  function actions(panel, ops) {
    let row = document.createElement('div');
    row.className = 'sheet-actions';
    for (let op of ops) {
      let b = command(op);
      if (b) {
        row.append(b);
        if (op === 'delete-page') b.classList.add('danger')
      }
    }
    panel.append(row)
  }
  let bp = panels.brush;
  heading(bp, 'Brush');
  let grid = document.createElement('div');
  grid.className = 'brush-grid';
  bp.append(grid);
  heading(bp, 'Stroke width');
  let widths = document.createElement('div');
  widths.className = 'widths';
  bp.append(widths);
  for (let [label, value] of Object.entries(state.widths)) {
    let b = document.createElement('button');
    b.title = label;
    b.setAttribute('aria-label', label + ' stroke');
    b.dataset.width = value;
    b.innerHTML = svg('<path stroke-width="' + (value * 1.5) + '" d="M3 14q9-12 18 0"/>') + '<small></small>';
    b.lastChild.textContent = label;
    b.onclick = () => {
      control('width').value = value;
      sync()
    };
    widths.append(b)
  }
  heading(bp, 'Ink color');
  let swatches = document.createElement('div');
  swatches.className = 'swatches';
  bp.append(swatches);
  control('width').hidden = true;
  bp.append(control('width'));
  // Native-select backing values remain available to the common pointer engine.
  for (let id of ['tool', 'color']) {
    control(id).hidden = true;
    bp.append(control(id))
  }
  let lp = panels.layers;
  field(lp, 'Draw on layer', control('layer'));
  heading(lp, 'Manage layers');
  field(lp, 'Layer visibility', control('layerVisibility'));
  let vis = command('layer-visible');
  lp.append(vis);
  field(lp, 'New layer name', control('layerName'));
  lp.append(control('addLayer'));
  command('delete-page').setAttribute('onclick', "send({op:'delete-page'})");
  let pp = panels.pages;
  pp.append(pages);
  let go = document.createElement('form');
  go.className = 'page-jump';
  let pageNumber = document.createElement('input');
  pageNumber.type = 'number';
  pageNumber.min = '1';
  pageNumber.required = true;
  pageNumber.setAttribute('aria-label', 'Page number');
  let goButton = document.createElement('button');
  goButton.type = 'submit';
  goButton.textContent = 'Go to page';
  go.append(pageNumber, goButton);
  go.onsubmit = e => {
    e.preventDefault();
    let index = Number(pageNumber.value) - 1;
    if (Number.isInteger(index) && index >= 0 && index < state.count && !busy) {
      closeSheet();
      send({op: 'page', index})
    }
  };
  pp.append(go);
  let previews = document.createElement('div');
  previews.className = 'page-previews';
  previews.setAttribute('aria-label', 'Page thumbnails');
  pp.append(previews);
  let morePages = document.createElement('button'), previewStart = 0;
  morePages.textContent = 'More pages';
  morePages.onclick = () => {
    morePages.disabled = true;
    send({op: 'page-previews', start: previewStart})
  };
  pp.append(morePages);
  let previewHint = document.createElement('p');
  previewHint.textContent = 'Ink previews; preserved templates and unsupported page content may not appear.';
  pp.append(previewHint);
  window.notebookPagePreviews = rows => {
    if (sheet.hidden || sheet.dataset.panel !== 'pages') return;
    for (let row of rows) {
      if (previews.querySelector('[data-page="' + row.index + '"]')) continue;
      let card = document.createElement('button'), image = document.createElement('img'), caption = document.createElement('span');
      card.dataset.page = row.index;
      card.setAttribute('aria-label', 'Page ' + (row.index + 1) + (row.warning ? ': preview unavailable' : ''));
      card.setAttribute('aria-current', String(row.index === state.index));
      image.src = row.image;
      image.alt = '';
      caption.textContent = String(row.index + 1);
      card.append(image, caption);
      card.onclick = () => {
        if (busy) return;
        closeSheet();
        send({op: 'page', index: row.index})
      };
      previews.append(card)
    }
    previewStart = rows.length ? rows[rows.length - 1].index + 1 : previewStart;
    morePages.hidden = previewStart >= state.count;
    morePages.disabled = false
  };
  heading(pp, 'Current page');
  actions(pp, ['add-page', 'duplicate-page', 'transfer']);
  heading(pp, 'Page order');
  actions(pp, ['move-page-earlier']);
  let later = command('move-page-later');
  if (later) pp.lastChild.append(later);
  heading(pp, 'Remove page');
  actions(pp, ['delete-page']);
  let dp = panels.document;
  dp.append(control('title'));
  let shortcuts = document.createElement('div');
  shortcuts.className = 'sheet-actions sheet-shortcuts';
  for (let [button, label] of [
      [pagesToggle, 'Pages Overview'],
      [layersToggle, 'Layers']
    ]) {
    button.className = '';
    button.lastChild.textContent = label;
    shortcuts.append(button)
  }
  dp.append(shortcuts);
  heading(dp, 'File');
  actions(dp, ['save', 'save-as', 'export']);
  let files = document.createElement('div');
  files.className = 'sheet-actions';
  for (let [op, label] of [
      ['show-in-folder', 'Show in folder'],
      ['library', 'Close document'],
      ['delete-file', 'Delete document…']
    ]) {
    let b = document.createElement('button');
    b.textContent = label;
    b.dataset.fileAction = op;
    b.onclick = () => {
      closeSheet();
      send({
        op
      })
    };
    if (op === 'delete-file') b.className = 'danger';
    files.append(b)
  }
  dp.append(files);
  let viewToggle = document.createElement('button');
  viewToggle.textContent = 'View and input…';
  viewToggle.onclick = () => openSheet('view', more);
  viewToggle.className = 'view-options';
  dp.append(viewToggle);
  hideTools.onclick = () => {
    closeSheet();
    setToolsHidden(true)
  };
  hideTools.className = '';
  hideTools.append(document.createTextNode('Hide tools'));
  dp.append(hideTools);
  // The model still supports notebook metadata names for desktop/legacy files.
  // Mobile file renames belong to the file browser and retain the live binding.
  let legacyName = document.createElement('div');
  legacyName.hidden = true;
  legacyName.append(control('notebookName'));
  dp.append(legacyName);
  let vp = panels.view;
  field(vp, 'Zoom', control('zoom'));
  let fingerLabel = document.createElement('label');
  fingerLabel.append(control('finger'), document.createTextNode('Draw with finger'));
  vp.append(fingerLabel);
  let grayLabel = document.createElement('label');
  grayLabel.append(control('grayscale'), document.createTextNode('Grayscale preview'));
  vp.append(grayLabel);
  let hint = document.createElement('p');
  hint.textContent = 'Swipe left or right with a finger to change pages. When zoomed in, drag to pan. Stylus input always draws. Ballpoint, Pencil, Marker, Paintbrush, Calligraphy and Shader respond to pen pressure. Grayscale changes the preview only.';
  vp.append(hint);
  dp.append(control('status'));
  let addPage = document.createElement('button');
  addPage.textContent = 'Add page';
  addPage.className = 'menu-add-page';
  addPage.title = 'Add a page after the current page';
  addPage.onclick = () => {
    closeSheet();
    send({op: 'add-page'})
  };
  const menuFooter = document.createElement('div');
  menuFooter.className = 'menu-footer';
  menuFooter.append(addPage);
  dp.append(menuFooter);

  const documentDropdown = new WebDropdown(sheet, more, {items: dp, close: () => closeSheet()});

  function openSheet(key, opener) {
    if (active !== null) return;
    if (eraserDialog.open) eraserDialog.close();
    returnFocus = opener || document.activeElement;
    for (let k of Object.keys(panels)) panels[k].hidden = k !== key;
    $('sheetTitle').textContent = names[key];
    sheet.dataset.panel = key;
    const menu = key === 'document', floating = key === 'brush', nonmodal = menu || floating;
    sheet.setAttribute('role', menu ? 'menu' : 'dialog');
    sheet.setAttribute('aria-modal', String(!nonmodal));
    documentDropdown.deactivate();
    sheet.hidden = false;
    backdrop.hidden = nonmodal;
    closer.hidden = nonmodal;
    brushToggle.setAttribute('aria-expanded', String(floating));
    if (floating) positionPanel(sheet, brushToggle);
    else {
      sheet.style.removeProperty('top');
      sheet.style.removeProperty('left')
    }
    sheet.lastChild.scrollTop = 0;
    if (key === 'pages') {
      pageNumber.max = String(state.count);
      pageNumber.value = String(state.index + 1);
      previews.replaceChildren();
      previewStart = 0;
      morePages.hidden = false;
      morePages.disabled = true;
      send({op: 'page-previews', start: 0})
    }
    header.inert = !nonmodal;
    dock.inert = !nonmodal;
    restore.inert = !nonmodal;
    $('viewport').inert = !nonmodal;
    if (menu) documentDropdown.activate();
    else (floating ? grid.querySelector('[aria-pressed=true]') || grid.firstElementChild : closer).focus()
  }

  function closeSheet(restoreFocus = true) {
    sheet.hidden = backdrop.hidden = true;
    documentDropdown.deactivate();
    brushToggle.setAttribute('aria-expanded', 'false');
    header.inert = false;
    dock.inert = false;
    restore.inert = false;
    $('viewport').inert = false;
    if (!restoreFocus) return;
    if (returnFocus && returnFocus.isConnected && returnFocus.getClientRects().length) returnFocus.focus();
    else document.querySelector('header button[aria-label="Notebook actions"]').focus()
  }
  backdrop.onclick = () => closeSheet();

  // Floating tool panels leave the initiating outside pointer event untouched.
  function positionPanel(panel, opener) {
    const anchor = opener.getBoundingClientRect();
    panel.style.top = Math.min(anchor.bottom + 8, innerHeight - 64) + 'px';
    panel.style.left = Math.max(8, Math.min(anchor.left, innerWidth - panel.getBoundingClientRect().width - 8)) + 'px'
  }
  $('closeEraser').hidden = true;
  showEraserSettings = () => {
    if (!sheet.hidden) closeSheet(false);
    eraserDialog.show();
    positionPanel(eraserDialog, control('erase'));
    control('erase').setAttribute('aria-expanded', 'true')
  };
  eraserDialog.addEventListener('close', () => control('erase').setAttribute('aria-expanded', 'false'));
  control('erase').setAttribute('aria-expanded', 'false');
  const selectEraser = control('erase').onclick;
  control('erase').onclick = () => {
    if (active !== null) return;
    if (eraserDialog.open) eraserDialog.close();
    else selectEraser()
  };
  function dismissToolPanels(target) {
    if (!sheet.hidden && sheet.dataset.panel === 'document' &&
        !sheet.contains(target) && !more.contains(target)) closeSheet(false);
    if (!sheet.hidden && sheet.dataset.panel === 'brush' &&
        !sheet.contains(target) && !brushToggle.contains(target)) closeSheet(false);
    if (eraserDialog.open && !eraserDialog.contains(target) &&
        !control('erase').contains(target)) eraserDialog.close()
  }
  document.addEventListener('pointerdown', e => dismissToolPanels(e.target), true);
  const startPointer = canvas.onpointerdown;
  canvas.onpointerdown = e => {
    // The Android native pen bridge calls this handler directly.
    dismissToolPanels(canvas);
    startPointer(e)
  };
  window.addEventListener('resize', () => {
    if (!sheet.hidden && sheet.dataset.panel === 'brush') positionPanel(sheet, brushToggle);
    if (eraserDialog.open) positionPanel(eraserDialog, control('erase'))
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && eraserDialog.open) {
      e.preventDefault();
      eraserDialog.close();
      control('erase').focus()
    }
    if (sheet.hidden) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      closeSheet()
    }
    if (e.key === 'Tab' && sheet.dataset.panel !== 'brush') {
      let focus = [...sheet.querySelectorAll('button,input,select')].filter(el => !el.disabled && el.getClientRects().length);
      let first = focus[0],
        last = focus[focus.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus()
      }
    }
  });
  // Close the sheet before structural/native actions; keep ink choices open for
  // combining brush, color and width without repeated menu trips.
  sheet.addEventListener('click', e => {
    let b = e.target.closest('button');
    if (b && b.dataset.action) closeSheet()
  });

  function paletteColor(tool, color) {
    let native = nativeColor(tool, color),
      rgba = native.color_rgba;
    let rgb = rgba ? rgba.slice(0, 3) : [1, 3, 5].map(i => parseInt((palette[color] || '#000000').slice(i, i + 2), 16));
    let alpha = rgba ? rgba[3] / 255 : 1;
    return colorCss(rgb.map(v => Math.round(v * alpha + 255 * (1 - alpha))))
  }

  function colorDisc(color, extra = '') {
    const disc = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    disc.setAttribute('viewBox', '0 0 28 28');
    disc.setAttribute('aria-hidden', 'true');
    disc.setAttribute('class', 'color-disc ' + extra);
    disc.style.forcedColorAdjust = 'none';
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', '14');
    circle.setAttribute('cy', '14');
    circle.setAttribute('r', '12');
    circle.style.setProperty('fill', color, 'important');
    disc.append(circle);
    return disc
  }
  let toolSignature = '',
    colorSignature = '';

  function sync() {
    pageNumber.max = String(state.count);
    if (document.activeElement !== pageNumber) pageNumber.value = String(state.index + 1);
    for (let card of previews.querySelectorAll('[data-page]')) card.setAttribute('aria-current', String(Number(card.dataset.page) === state.index));
    for (let b of document.querySelectorAll('[data-file-action]')) b.hidden = b.dataset.fileAction === 'show-in-folder' ? !state.has_source : b.dataset.fileAction === 'delete-file' ? !state.can_delete : false;
    let t = control('tool'),
      c = control('color');
    const next = JSON.stringify(state.tools);
    if (toolSignature !== next) {
      toolSignature = next;
      grid.replaceChildren();
      for (let [name, value] of Object.entries(state.tools)) {
        let b = document.createElement('button');
        b.className = 'brush-card';
        b.dataset.tool = value;
        b.innerHTML = svg(brushNib(value));
        let label = document.createElement('span');
        label.textContent = name;
        b.append(label);
        b.setAttribute('aria-label', name);
        b.onclick = () => {
          t.value = value;
          t.onchange();
          selected.clear();
          draw();
          sync()
        };
        grid.append(b)
      }
    }
    const colors = t.value + ':' + JSON.stringify([...c.options].map(o => [o.textContent, o.value]));
    if (colorSignature !== colors) {
      colorSignature = colors;
      swatches.replaceChildren();
      for (let option of c.options) {
        let b = document.createElement('button');
        b.className = 'swatch';
        b.dataset.color = option.value;
        b.title = option.textContent;
        b.setAttribute('aria-label', option.textContent + ' ink');
        b.append(colorDisc(paletteColor(Number(t.value), Number(option.value))));
        b.onclick = () => {
          c.value = option.value;
          sync()
        };
        swatches.append(b)
      }
    }
    for (let b of grid.children) b.setAttribute('aria-pressed', String(b.dataset.tool === t.value));
    for (let b of swatches.children) b.setAttribute('aria-pressed', String(b.dataset.color === c.value));
    for (let b of widths.children) b.setAttribute('aria-pressed', String(Number(b.dataset.width) === Number(control('width').value)));
    let name = t.selectedOptions[0]?.textContent || 'Pen';
    brushToggle.innerHTML = svg(brushNib(t.value)) + '<small></small>';
    brushToggle.lastChild.textContent = name;
    brushToggle.append(colorDisc(paletteColor(Number(t.value), Number(c.value)), 'current-ink'));
    brushToggle.title = name + ' · ' + (c.selectedOptions[0]?.textContent || '') + ' · ' + (control('width').selectedOptions[0]?.textContent || '');
    brushToggle.setAttribute('aria-label', brushToggle.title + '. Change writing tools');
    brushToggle.setAttribute('aria-pressed', String(mode === 'ink'));
    for (let id of ['erase', 'select']) control(id).setAttribute('aria-pressed', String(mode === id));
  }
  for (let id of ['erase', 'select']) control(id).addEventListener('click', sync);
  control('grayscale').addEventListener('change', sync);
  let notice = document.createElement('div');
  notice.id = 'mobileNotice';
  notice.hidden = true;
  notice.setAttribute('role', 'alert');
  let noticeText = document.createElement('span');
  notice.append(noticeText, makeButton('close', 'Dismiss message', () => {
    notice.hidden = true
  }));
  document.body.append(notice);

  function showNotice(message) {
    noticeText.textContent = message;
    notice.hidden = false
  }
  const baseUpdate = window.notebookUpdate;
  window.notebookUpdate = function(next, error) {
    baseUpdate(next, error);
    if (error) showNotice(error)
  };
  const baseSend = send;
  send = function(action) {
    baseSend(action);
    if (!busy && control('status').textContent.includes('too large')) showNotice(control('status').textContent)
  };
  const baseRender = render;
  render = function() {
    baseRender();
    sync()
  };
  sync();
  resize();
})();

// Native Boox preview is optional. The canonical pointer/brush/save path remains
// shared, including for every unsupported brush, color and editing mode.
(function() {
  if (!window.LogisticsBooxInk) return;
  let previous = '', scheduled = false;
  function configure() {
    scheduled = false;
    const r = canvas.getBoundingClientRect(), v = $('viewport').getBoundingClientRect(), ink = chosenInk();
    const visible = el => el && !el.hidden && getComputedStyle(el).display !== 'none';
    const overlay = visible($('mobileSheet')) || !!document.querySelector('dialog[open]');
    const rect = [Math.max(0, r.left, v.left), Math.max(0, r.top, v.top),
      Math.min(innerWidth, r.right, v.right), Math.min(innerHeight, r.bottom, v.bottom)];
    const exclude = [...document.querySelectorAll('header,nav,#restoreTools')].filter(visible).map(el => {
      const b = el.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]
    });
    const {rgb, alpha} = inkColor(nativeColor(ink.tool, ink.color));
    // Use the same displayed RGB (including grayscale) as the canonical canvas;
    // keep the selected native color ID unchanged for saving.
    const argb = 0xff000000 + rgb[0] * 65536 + rgb[1] * 256 + rgb[2];
    const config = JSON.stringify({enabled: mode === 'ink' && [15, 17].includes(ink.tool) && alpha === 1 &&
      brushFor(ink.tool).colors.includes(ink.color) &&
      !overlay && !state.read_only && !state.warning && !pan && queue.length < 64 &&
      queue.every(a => a.op === 'stroke'), tool: ink.tool, color: ink.color, argb,
      width: brushFor(ink.tool).widths[ink.width - 1] * r.width / state.width,
      baseWidth: brushFor(ink.tool).widths[ink.width - 1],
      rect, exclude, viewportWidth: innerWidth, viewportHeight: innerHeight,
      // Changing scene or layer cancels any outstanding native gesture.
      scene: [state.index, state.width, state.height, ink.layer]});
    if (config !== previous) { previous = config; window.LogisticsBooxInk.configure(config) }
  }
  function schedule() { if (!scheduled) { scheduled = true; requestAnimationFrame(configure) } }
  new MutationObserver(schedule).observe(document.body, {subtree: true, attributes: true, childList: true, characterData: true});
  new ResizeObserver(schedule).observe(canvas);
  document.addEventListener('change', schedule, true);
  document.addEventListener('click', schedule, true);
  document.addEventListener('pointerup', schedule, true);
  document.addEventListener('scroll', schedule, true);
  addEventListener('resize', schedule);
  schedule();
})();
