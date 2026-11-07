renderEraserChoices();
(function() {

  continuousInk = true;
  frameBatchedInk = !!state.frame_batched_ink;
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
    button.style.touchAction = 'manipulation';
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
  let railLeft = 0, railRight = 0;
  window.notebookViewportInsets = ([left, right, home] = [0, 0, 0]) => {
    const railChanged = left !== railLeft || right !== railRight;
    railLeft = left;
    railRight = right;
    document.body.style.setProperty('--notebook-rail-left', left + 'px');
    document.body.style.setProperty('--notebook-rail-right', right + 'px');
    document.body.style.setProperty('--notebook-home-bottom', home + 'px');
    if (railChanged) scheduleViewportResize();
    repositionBrushPanel();
    if (eraserDialog.open) positionPanel(eraserDialog, control('erase'));
    if (presetMenu.open) presetMenu.close();
    if (!swipeAddPage.hidden) showSwipePage();
    selectionRender();
    return true;
  };
  window.notebookPortraitBand = enabled => {
    const usable = enabled === true && !!state.native_close && !!state.native_actions &&
      !document.body.classList.contains('native-drawing-tools');
    document.body.classList.toggle('notebook-portrait-band', usable);
    return usable
  };
  window.notebookPortraitBand(!!state.native_top_band);
  if (state.native_close) command('library').hidden = true;
  let more = makeButton('more', 'Notebook actions', e => sheet.hidden ? openSheet('document', e.currentTarget) : closeSheet());
  more.hidden = !!state.native_actions;
  header.append(iconButton(command('library'), 'close', 'Close document'), more);
  let dock = document.createElement('nav');
  dock.className = 'mobile-dock';
  dock.setAttribute('aria-label', 'Drawing and page tools');
  header.insertBefore(dock, more);
  let tools = document.createElement('div');
  tools.className = 'mobile-tools';
  dock.append(tools);
  let workingPreset, activePreset = null;
  let brushToggle = makeButton(17, 'Brush, color and width', () => {
    if (active === null) tapBrushSlot(brushToggle, workingPreset);
  }, 'Pen');
  brushToggle.id = 'brushToggle';
  brushToggle.setAttribute('aria-haspopup', 'dialog');
  brushToggle.setAttribute('aria-expanded', 'false');
  const presetButtons = document.createElement('div');
  presetButtons.className = 'preset-buttons';
  presetButtons.setAttribute('role', 'group');
  presetButtons.setAttribute('aria-label', 'Brush presets');
  tools.append(brushToggle, presetButtons);
  const presetLimit = state.brush_preset_limit ?? 2;
  const presetMenu = document.createElement('dialog');
  presetMenu.id = 'brushPresetMenu';
  presetMenu.setAttribute('aria-label', 'Brush preset actions');
  const removePreset = document.createElement('button');
  removePreset.type = 'button';
  removePreset.textContent = 'Delete preset';
  presetMenu.append(removePreset);
  document.body.append(presetMenu);
  let presetMenuOpener = null;
  const addPreset = makeButton('plus', 'Add current brush preset', pinBrush);
  addPreset.id = 'addBrushPreset';
  addPreset.title = 'Add current brush preset';
  tools.append(addPreset);
  for (let [id, label] of [
      ['erase', 'Erase'],
      ['select', 'Select'],
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
    if (presetMenu.open) presetMenu.close();
    document.body.classList.toggle('tools-hidden', hidden);
    restore.hidden = !hidden;
    (hidden ? restore : more.hidden ? brushToggle : more).focus({preventScroll: true})
  }
  let pages = document.createElement('div');
  pages.className = 'mobile-pages';
  pages.append(iconButton(control('prev'), 'back', 'Previous page'), control('pageinfo'), iconButton(control('next'), 'next', 'Next page'));
  let pagesToggle = makeButton('pages', 'Pages Overview', e => openSheet('pages', e.currentTarget), 'Pages Overview');
  pagesToggle.id = 'pagesToggle';
  let layersToggle = makeButton('layers', 'Page template and layers', e => openSheet('layers', e.currentTarget), 'Page template');
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
    layers: 'Page template and layers',
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
  heading(bp, 'Ink color');
  let swatches = document.createElement('div');
  swatches.className = 'swatches';
  bp.append(swatches);
  heading(bp, 'Stroke width');
  let widths = document.createElement('div');
  widths.className = 'widths';
  bp.append(widths);
  const strokeSample = document.createElement('span');
  strokeSample.className = 'stroke-sample';
  strokeSample.innerHTML = svg('<path d="M1 15c6 4 13-8 22-5"/>');
  widths.append(strokeSample);
  for (let [label, value] of Object.entries(state.widths)) {
    let b = document.createElement('button');
    b.title = label;
    b.setAttribute('aria-label', label + ' stroke');
    b.dataset.width = value;
    b.innerHTML = '<svg viewBox="0 0 60 32" aria-hidden="true"><path d="M16 16h28" fill="none" stroke="currentColor" stroke-linecap="round"/></svg><small></small>';
    b.lastChild.textContent = label;
    b.onclick = () => {
      control('width').value = value;
      saveBrushSlot()
    };
    widths.append(b)
  }
  control('width').hidden = true;
  bp.append(control('width'));
  // Native-select backing values remain available to the common pointer engine.
  for (let id of ['tool', 'color']) {
    control(id).hidden = true;
    bp.append(control(id))
  }
  let lp = panels.layers;
  lp.append(control('templateControls'));
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
  const pageTemplateButton = document.createElement('button');
  pageTemplateButton.textContent = 'Page template…';
  pageTemplateButton.id = 'pageTemplateButton';
  pageTemplateButton.onclick = e => openSheet('layers', e.currentTarget);
  pp.append(pageTemplateButton);
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
  const notebookTitle = control('title');
  dp.append(notebookTitle);
  let titleHold, titleTouch;
  function cancelTitleHold() {
    clearTimeout(titleHold);
    titleTouch = null;
  }
  notebookTitle.addEventListener('pointerdown', e => {
    cancelTitleHold();
    if (!e.isPrimary || e.button !== 0) return;
    titleTouch = {id: e.pointerId, x: e.clientX, y: e.clientY};
    titleHold = setTimeout(() => {
      cancelTitleHold();
      if (!sheet.hidden && sheet.dataset.panel === 'document') send({op: 'document-location'});
    }, 500);
  });
  notebookTitle.addEventListener('pointermove', e => {
    if (titleTouch && e.pointerId === titleTouch.id &&
        Math.hypot(e.clientX - titleTouch.x, e.clientY - titleTouch.y) > 8) cancelTitleHold();
  });
  for (const event of ['pointerup', 'pointercancel', 'pointerleave', 'lostpointercapture']) {
    notebookTitle.addEventListener(event, cancelTitleHold);
  }
  window.addEventListener('blur', cancelTitleHold);
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
  const captureButton = control('capture'), toggleCapture = captureButton.onclick;
  captureButton.className = '';
  captureButton.textContent = 'Capture cutouts and arrange images';
  captureButton.setAttribute('aria-label', 'Capture cutouts and arrange images');
  captureButton.onclick = event => {
    if (active !== null || busy) return;
    closeSheet(false);
    toggleCapture(event)
  };
  vp.append(captureButton);
  control('zoom').add(new Option('Fit page', 'page'));
  field(vp, 'Zoom', control('zoom'));
  const zoomControls = document.createElement('div');
  document.body.append(zoomControls);
  createZoomControls(zoomControls);
  let fingerLabel = document.createElement('label');
  fingerLabel.append(control('finger'), document.createTextNode('Draw with finger'));
  vp.append(fingerLabel);
  const constantPressure = document.createElement('input');
  constantPressure.type = 'checkbox';
  constantPressure.id = 'constantPenPressure';
  constantPressure.checked = constantPenPressure;
  constantPressure.onchange = () => {
    if (active !== null || busy) {
      constantPressure.checked = constantPenPressure;
      return
    }
    constantPenPressure = constantPressure.checked
  };
  const constantPressureLabel = document.createElement('label');
  constantPressureLabel.append(constantPressure, document.createTextNode('Constant stylus pressure (this open document)'));
  vp.append(constantPressureLabel);
  const constantPressureHint = document.createElement('p');
  constantPressureHint.textContent = 'For pens without pressure sensitivity, including Apple Pencil (USB-C). Pressure stays fixed while enabled.';
  vp.append(constantPressureHint);
  let grayLabel = document.createElement('label');
  grayLabel.append(control('grayscale'), document.createTextNode('Grayscale preview'));
  vp.append(grayLabel);
  let hint = document.createElement('p');
  hint.textContent = 'Swipe left or right with a finger to change pages. Drag with two fingers to pan; pinch with two fingers to zoom. Swipe past the last page for the + Page button. Stylus input always draws. Ballpoint, Pencil, Marker, Paintbrush, Calligraphy and Shader respond to pen pressure. Grayscale changes the preview only.';
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

  const laptopTools = document.createElement('section');
  laptopTools.id = 'laptopTools';
  laptopTools.setAttribute('aria-label', 'Notebook drawing settings');
  laptopTools.hidden = true;
  document.body.append(laptopTools);
  function measureToolbar() {
    document.body.style.setProperty('--notebook-toolbar-bottom',
      header.getBoundingClientRect().bottom + 'px')
  }
  const toolbarObserver = new ResizeObserver(measureToolbar);
  toolbarObserver.observe(header);
  window.addEventListener('resize', measureToolbar);
  measureToolbar();
  let fold = null, foldFrame = null;
  function applyFold() {
    foldFrame = null;
    // Never move the paper underneath a live pen contact.
    if (active !== null) { foldFrame = requestAnimationFrame(applyFold); return; }
    const enabled = !!fold;
    const zoomSnapshot = captureViewportZoom();
    closeSheet(false);
    if (eraserDialog.open) eraserDialog.close();
    document.body.classList.toggle('notebook-laptop', enabled);
    document.body.classList.remove('tools-hidden');
    restore.hidden = true;
    hideTools.hidden = enabled;
    laptopTools.hidden = !enabled;
    for (let key of ['brush', 'view', 'layers']) {
      (enabled ? laptopTools : sheet.lastChild).append(panels[key]);
      panels[key].hidden = !enabled;
    }
    if (enabled) {
      document.body.style.setProperty('--fold-top', (fold[0] * innerHeight) + 'px');
      document.body.style.setProperty('--fold-bottom', (fold[1] * innerHeight) + 'px');
    }
    restoreViewportZoom(zoomSnapshot);
  }
  window.notebookFold = geometry => {
    const nextFold = Array.isArray(geometry) && geometry.length === 2 &&
      geometry.every(Number.isFinite) && geometry[0] > 0 && geometry[1] >= geometry[0] && geometry[1] < 1 ? geometry : null;
    // Initial host geometry can arrive after the user opens a tool picker.
    // An already-flat canvas needs no reparenting or panel dismissal.
    if (fold === null && nextFold === null) return;
    fold = nextFold;
    if (foldFrame === null) foldFrame = requestAnimationFrame(applyFold);
  };

  function openSheet(key, opener) {
    if (active !== null) return;
    if (presetMenu.open) presetMenu.close();
    cancelTitleHold();
    cancelTouchZoom();
    if (fold && ['brush', 'layers', 'view'].includes(key)) {
      closeSheet(false);
      panels[key].scrollIntoView({block: 'nearest'});
      panels[key].querySelector('button,select,input')?.focus({preventScroll: true});
      return;
    }
    if (eraserDialog.open) eraserDialog.close();
    if (brushPanelOpener) closeSheet(false);
    returnFocus = opener || document.activeElement;
    for (let k of Object.keys(panels)) panels[k].hidden = k !== key && !(fold && panels[k].parentElement === laptopTools);
    $('sheetTitle').textContent = names[key];
    sheet.dataset.panel = key;
    const menu = key === 'document', floating = key === 'brush', nonmodal = menu || floating;
    sheet.setAttribute('role', menu ? 'menu' : 'dialog');
    sheet.setAttribute('aria-modal', String(!nonmodal));
    documentDropdown.deactivate();
    sheet.hidden = false;
    backdrop.hidden = nonmodal;
    closer.hidden = nonmodal;
    if (floating) {
      brushPanelOpener = opener?.matches('[data-preset]') ? opener : brushToggle;
      brushPanelOpener.setAttribute('aria-expanded', 'true');
      brushPanelAnchor = nativeToolAnchor;
      positionPanel(sheet, brushPanelOpener);
    }
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
    zoomControls.inert = !nonmodal;
    $('viewport').inert = !nonmodal;
    if (menu) documentDropdown.activate();
    else (floating ? grid.querySelector('[aria-pressed=true]') || grid.firstElementChild : closer).focus({preventScroll: true})
  }

  // Native toolbar actions enter the same queue as canvas controls, preserving
  // pending ink and the normal save/delete/close guards.
  window.notebookNativeAction = name => {
    if (active !== null) return;
    if (Object.hasOwn(panels, name)) {
      openSheet(name, more);
    } else if (name === 'hide-tools') {
      closeSheet(false);
      setToolsHidden(true);
    } else if (['save', 'save-as', 'export', 'show-in-folder', 'document-location',
                'add-page', 'library', 'delete-file'].includes(name)) {
      closeSheet(false);
      send({op: name});
    }
  };

  // Native drawing controls invoke these original DOM handlers and read
  // their real state. A short lease restores the DOM toolbar if the host stalls.
  let nativeToolsLease = null, nativeToolAnchor = null, brushPanelAnchor = null, brushPanelOpener = null;
  window.notebookNativeTools = action => {
    clearTimeout(nativeToolsLease);
    const restoreTools = () => {
      // Keep paper geometry stable until every current contact/queued edit retires.
      if (active !== null || busy || queue.length) {
        nativeToolsLease = setTimeout(restoreTools, 100);
        return;
      }
      const changed = document.body.classList.contains('native-drawing-tools');
      document.body.classList.remove('native-drawing-tools');
      if (changed) resize();
    };
    if (action === false) { restoreTools(); return null; }
    const hidden = document.body.classList.contains('tools-hidden');
    const controls = {pen:brushToggle, ...window.notebookPresetTargets?.(), erase:control('erase'),
                      select:control('select'), undo:control('undo'), redo:control('redo')};
    const snapshot = () => JSON.stringify(Object.fromEntries(Object.entries(controls).map(([name, button]) => {
      const unavailable = active !== null || busy;
      const row = {disabled:!button || !!(button.disabled || header.inert || dock.inert || unavailable),
                   active:!unavailable && button?.getAttribute('aria-pressed') === 'true'};
      if (name === 'add-preset') row.visible = !button.hidden;
      if (name.startsWith('preset-')) {
        row.visible = !!button;
        if (button) {
          row.label = button.title;
          row.preset = button.dataset.brush.split(',').map(Number);
          row.preset_id = button.dataset.preset;
          row.rgb = button.dataset.nativeColor.match(/\d+/g).map(Number);
        }
      }
      return [name, row];
    })));
    if (hidden || active !== null || busy) {
      nativeToolsLease = setTimeout(restoreTools, 1500);
      return hidden || !document.body.classList.contains('native-drawing-tools')
        ? JSON.stringify(null) : snapshot();
    }
    if (action !== null) {
      if (!action || !Object.hasOwn(controls, action.name) || !Array.isArray(action.anchor)
          || action.anchor.length !== 4 || !action.anchor.every(Number.isFinite)
          || action.anchor[2] < 44 || action.anchor[3] < 44) throw new Error('Unknown native drawing tool');
      const target = controls[action.name], [x,y,width,height] = action.anchor;
      nativeToolAnchor = {left:x, top:y, right:x+width, bottom:y+height, width, height};
      try {
        if (target && !target.hidden && !target.disabled && !header.inert && !dock.inert &&
            (!action.preset || action.preset === target.dataset?.preset)) {
          dismissToolPanels(target);
          if (action.hold && target.dataset?.preset) showPresetActions(target);
          else if (!action.hold) target.click();
        }
      } finally { nativeToolAnchor = null; }
    }
    const changed = !document.body.classList.contains('native-drawing-tools');
    document.body.classList.add('native-drawing-tools');
    if (changed) resize();
    nativeToolsLease = setTimeout(restoreTools, 1500);
    return snapshot();
  };

  function closeSheet(restoreFocus = true) {
    cancelTitleHold();
    sheet.hidden = backdrop.hidden = true;
    documentDropdown.deactivate();
    brushPanelOpener?.setAttribute('aria-expanded', 'false');
    brushPanelOpener = null;
    brushPanelAnchor = null;
    header.inert = false;
    dock.inert = false;
    restore.inert = false;
    zoomControls.inert = false;
    $('viewport').inert = false;
    if (!restoreFocus) return;
    const fallback = more.hidden ? brushToggle : more;
    const target = returnFocus?.getClientRects().length ? returnFocus : fallback;
    if (target.getClientRects().length && getComputedStyle(target).visibility !== 'hidden') {
      target.focus({preventScroll: true});
    } else if (sheet.contains(document.activeElement)) {
      // Native controls live outside WebKit. Retire focus on the closed panel.
      document.activeElement.blur();
    }
  }
  backdrop.onclick = () => closeSheet();

  // Floating tool panels leave the initiating outside pointer event untouched.
  function positionPanel(panel, opener) {
    const anchor = (panel === sheet ? brushPanelAnchor : nativeToolAnchor) || opener.getBoundingClientRect();
    const width = panel.getBoundingClientRect().width;
    const top = Math.max(8, Math.min(anchor.bottom + 8, innerHeight - 64));
    const left = Math.max(railLeft + 8, Math.min(anchor.left, innerWidth - railRight - width - 8));
    panel.style.top = top + 'px';
    panel.style.left = left + 'px';
    if (panel === sheet) {
      panel.style.setProperty('--drawer-top', top + 'px');
      panel.style.setProperty('--drawer-notch', Math.max(14, Math.min(width - 14, anchor.left + anchor.width / 2 - left)) + 'px');
    }
  }
  $('closeEraser').hidden = true;
  onEraserKindChanged = kind => {
    if (state.eraser_kind !== undefined) send({op: 'eraser-kind', kind});
  };
  showEraserSettings = () => {
    if (!sheet.hidden) closeSheet(false);
    eraserDialog.show();
    positionPanel(eraserDialog, control('erase'));
    control('erase').setAttribute('aria-expanded', 'true')
  };
  eraserDialog.addEventListener('close', () => control('erase').setAttribute('aria-expanded', 'false'));
  control('erase').setAttribute('aria-expanded', 'false');
  control('erase').onclick = () => {
    if (active !== null) return;
    if (eraserDialog.open) eraserDialog.close();
    else if (mode === 'erase') showEraserSettings();
    else selectEraser();
  };
  function dismissToolPanels(target) {
    if (presetMenu.open && !presetMenu.contains(target)) presetMenu.close();
    if (!sheet.hidden && sheet.dataset.panel === 'document' &&
        !sheet.contains(target) && !more.contains(target)) closeSheet(false);
    if (!sheet.hidden && sheet.dataset.panel === 'brush' &&
        !sheet.contains(target) && !brushPanelOpener?.contains(target)) closeSheet(false);
    if (eraserDialog.open && !eraserDialog.contains(target) &&
        !control('erase').contains(target)) eraserDialog.close()
  }
  function inSideRail(x) {
    return (railLeft > 0 && x < railLeft) || (railRight > 0 && x >= innerWidth - railRight);
  }
  window.clipNotebookControls = target => {
    if (!railLeft && !railRight) return;
    const box = canvas.getBoundingClientRect();
    if (!box.width) return;
    const scale = state.width / box.width;
    target.beginPath();
    target.rect((railLeft - box.left) * scale, 0, (innerWidth - railLeft - railRight) * scale, state.height);
    target.clip();
  };
  document.addEventListener('pointerdown', e => {
    if (inSideRail(e.clientX) && $('viewport').contains(e.target)) {
      cancelPageTouch();
      e.preventDefault();
      e.stopImmediatePropagation();
      return;
    }
    dismissToolPanels(e.target);
  }, true);
  const paper = control('paperWrap');
  paper.addEventListener('selectstart', e => e.preventDefault());
  paper.addEventListener('contextmenu', e => e.preventDefault());
  function clearPaperSelection() {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return;
    for (let i = 0; i < selection.rangeCount; i++) {
      const range = selection.getRangeAt(i);
      const node = range.commonAncestorContainer;
      const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
      if (element?.closest('input,textarea,[contenteditable=true]')) continue;
      if (range.intersectsNode(paper)) {
        selection.removeAllRanges();
        break
      }
    }
  }
  document.addEventListener('selectionchange', clearPaperSelection);
  const startPointer = canvas.onpointerdown;
  canvas.onpointerdown = e => {
    if (inSideRail(e.clientX)) return;
    // The Android native pen bridge calls this handler directly.
    dismissToolPanels(canvas);
    // WebKit need not emit selectionchange for a programmatic/nonselectable
    // range. A drawing or palm contact also clears any stale paper selection.
    clearPaperSelection();
    startPointer(e)
  };
  window.addEventListener('resize', () => {
    if (presetMenu.open) presetMenu.close();
    if (fold) window.notebookFold(fold);
    repositionBrushPanel();
    if (eraserDialog.open) positionPanel(eraserDialog, control('erase'))
  });
  function repositionBrushPanel() {
    if (brushPanelOpener) positionPanel(sheet, brushPanelOpener);
  }
  dock.addEventListener('scroll', repositionBrushPanel);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && presetMenu.open) {
      e.preventDefault();
      presetMenu.close();
      if (presetMenuOpener?.getClientRects().length) presetMenuOpener.focus({preventScroll: true});
      return;
    }
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
      rgba = native.color_rgba || (tool === 18 ? state.native_highlights[native.color] : null);
    let rgb = rgba ? rgba.slice(0, 3) : [1, 3, 5].map(i => parseInt((palette[native.color] || '#000000').slice(i, i + 2), 16));
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

  function currentPreset() {
    const {tool, color, width} = chosenInk();
    return [tool, color, width];
  }

  function pinBrush() {
    if (active !== null || addPreset.hidden || addPreset.disabled) return;
    if (brushPanelOpener) closeSheet(false);
    send({op: 'add-brush-preset', preset: currentPreset()});
  }

  function showPresetActions(button) {
    if (active !== null || !button.isConnected || (presetMenu.open && presetMenuOpener === button)) return;
    if (!sheet.hidden) closeSheet(false);
    if (eraserDialog.open) eraserDialog.close();
    presetMenuOpener = button;
    if (!presetMenu.open) presetMenu.show();
    positionPanel(presetMenu, button);
    removePreset.setAttribute('aria-label', 'Delete preset ' + button.title);
    removePreset.onclick = () => {
      presetMenu.close();
      if (active === null) send({op: 'remove-brush-preset', id: button.dataset.preset});
    };
    removePreset.focus({preventScroll: true});
  }

  function bindPresetHold(button) {
    button.style.touchAction = 'pan-x';
    let timer, start, held = false;
    const cancel = () => {
      clearTimeout(timer);
      start = null;
    };
    button.addEventListener('pointerdown', event => {
      if (!event.isPrimary || event.button !== 0) return;
      held = false;
      start = [event.clientX, event.clientY];
      timer = setTimeout(() => {
        held = true;
        showPresetActions(button);
      }, 500);
    });
    button.addEventListener('pointermove', event => {
      if (start && Math.hypot(event.clientX - start[0], event.clientY - start[1]) > 10) cancel();
    });
    for (const event of ['pointerup', 'pointercancel', 'pointerleave']) button.addEventListener(event, cancel);
    button.addEventListener('contextmenu', event => {
      event.preventDefault();
      cancel();
      held = true;
      showPresetActions(button);
    });
    button.addEventListener('keydown', event => {
      if (event.key === 'Delete' || event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) {
        event.preventDefault();
        showPresetActions(button);
      }
    });
    button.onclick = event => {
      if (held && event.detail !== 0) return;
      if (active === null) tapBrushSlot(button, presetFor(button.dataset.preset));
    };
  }

  function tapBrushSlot(button, preset) {
    if (brushPanelOpener === button) {
      closeSheet();
      return;
    }
    if (!sheet.hidden) closeSheet(false);
    const key = button.dataset.preset || null;
    if (mode === 'ink' && activePreset === key) {
      openSheet('brush', button);
      return;
    }
    if (eraserDialog.open) eraserDialog.close();
    if (!preset) return;
    activePreset = key;
    applyBrushSlot(preset, true);
    selected.clear();
    draw();
    sync();
  }

  function applyBrushSlot([tool, color, width], activate = false) {
    rememberBrushOptions = false;
    control('tool').value = tool;
    if (activate) control('tool').onchange();
    else brushOptions();
    control('color').value = color;
    control('width').value = width;
    rememberBrushOptions = activePreset === null;
  }

  function visiblePresets() {
    const updates = new Map(queue.filter(action => action.op === 'update-brush-preset')
      .map(action => [action.id, action.preset]));
    return (state.brush_presets || []).map(entry => ({
      id: entry.id, brush: updates.get(entry.id) || entry.brush
    }));
  }

  function presetFor(id) {
    return visiblePresets().find(entry => entry.id === id)?.brush;
  }

  function saveBrushSlot() {
    const brush = currentPreset();
    if (activePreset !== null && presetFor(activePreset)?.join(',') !== brush.join(',')) {
      send({op: 'update-brush-preset', id: activePreset, preset: brush});
    }
    sync();
  }

  function restoreBrushSlot() {
    if (activePreset === null) return;
    const brush = presetFor(activePreset);
    if (brush) applyBrushSlot(brush);
    else {
      activePreset = null;
      applyBrushSlot(workingPreset);
    }
  }

  if (state.brush_preset_limit) {
    window.notebookPresetTargets = () => ({
      'preset-0': presetButtons.children[0],
      'preset-1': presetButtons.children[1],
      'add-preset': addPreset
    });
  }

  function syncPresets() {
    const presets = visiblePresets();
    const ids = new Set(presets.map(entry => entry.id));
    for (const button of [...presetButtons.children]) {
      if (ids.has(button.dataset.preset)) continue;
      if (brushPanelOpener === button) closeSheet(false);
      if (presetMenuOpener === button && presetMenu.open) presetMenu.close();
      button.remove();
    }
    for (const [index, {id, brush}] of presets.entries()) {
      let button = [...presetButtons.children].find(b => b.dataset.preset === id);
      if (!button) {
        button = makeButton(brush[0], 'Brush preset', null);
        button.dataset.preset = id;
        bindPresetHold(button);
        button.setAttribute('aria-haspopup', 'dialog');
        button.setAttribute('aria-keyshortcuts', 'Delete Shift+F10');
        button.setAttribute('aria-expanded', 'false');
      }
      if (presetButtons.children[index] !== button) {
        presetButtons.insertBefore(button, presetButtons.children[index] || null);
      }
      if (button.dataset.brush !== brush.join(',')) {
        const [tool, color, width] = brush;
        const brushName = Object.keys(state.tools).find(name => state.tools[name] === tool);
        const colorName = Object.keys(state.colors).find(name => state.colors[name] === color);
        const fixed = brushFor(tool).fixed_width;
        const widthName = fixed ? 'Fixed' : Object.keys(state.widths)[width - 1];
        button.dataset.brush = brush.join(',');
        button.dataset.nativeColor = paletteColor(tool, color);
        button.title = [brushName, colorName, widthName].join(' · ');
        button.setAttribute('aria-label', 'Use preset ' + button.title);
        button.innerHTML = svg(brushNib(tool));
        button.append(colorDisc(button.dataset.nativeColor, 'current-ink'));
        if (!fixed) {
          const marks = document.createElement('span');
          marks.className = 'preset-width';
          marks.setAttribute('aria-hidden', 'true');
          marks.textContent = '•'.repeat(width);
          button.append(marks);
        }
      }
      button.setAttribute('aria-pressed', String(mode === 'ink' && id === activePreset));
    }
    const current = currentPreset().join(',');
    addPreset.hidden = presets.length >= presetLimit;
    addPreset.disabled = presets.some(entry => entry.brush.join(',') === current);
  }

  window.notebookBrushPresetUpdate = (presets, error) => {
    if (active !== null) {
      deferredUpdate = () => window.notebookBrushPresetUpdate(presets, error);
      return;
    }
    const action = queue[0];
    const removing = action?.op === 'remove-brush-preset';
    const restorePresetFocus = removing && (presetButtons.contains(document.activeElement) ||
      document.activeElement === removePreset || !document.activeElement?.getClientRects().length);
    state.brush_presets = presets;
    if (!error && action?.op === 'add-brush-preset' && action.preset.join(',') === currentPreset().join(',')) {
      activePreset = presets.find(entry => entry.brush.join(',') === action.preset.join(','))?.id ?? null;
    }
    window.notebookBrushColorUpdate('');
    restoreBrushSlot();
    sync();
    if (restorePresetFocus && !error) {
      (addPreset.hidden || addPreset.disabled ? brushToggle : addPreset).focus({preventScroll: true});
    }
    if (error) showNotice(error);
  };
  window.notebookRefreshBrushPresets = presets => {
    if (active !== null || busy) return false;
    state.brush_presets = presets;
    restoreBrushSlot();
    sync();
    return true;
  };

  let toolSignature = '',
    colorSignature = '';

  function sync() {
    pageNumber.max = String(state.count);
    if (document.activeElement !== pageNumber) pageNumber.value = String(state.index + 1);
    for (let card of previews.querySelectorAll('[data-page]')) card.setAttribute('aria-current', String(Number(card.dataset.page) === state.index));
    for (let b of document.querySelectorAll('[data-file-action]')) b.hidden = state.notes_library && ['library','save-as','transfer','show-in-folder','delete-file'].includes(b.dataset.fileAction) ? true : b.dataset.fileAction === 'show-in-folder' ? !state.has_source : b.dataset.fileAction === 'delete-file' ? !state.can_delete : false;
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
          saveBrushSlot()
        };
        grid.append(b);

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
          c.dispatchEvent(new Event('change'));
          saveBrushSlot()
        };
        swatches.append(b);

      }
    }
    for (let b of grid.children) b.setAttribute('aria-pressed', String(b.dataset.tool === t.value));
    for (let b of swatches.children) b.setAttribute('aria-pressed', String(b.dataset.color === c.value));
    const ink = chosenInk();
    const sample = strokeSample.querySelector('path');
    sample.style.stroke = paletteColor(ink.tool, ink.color);
    sample.style.strokeWidth = String(Math.min(7, Math.max(.9, brushFor(ink.tool).widths[ink.width - 1] * .4)));
    const fixed = brushFor(ink.tool).fixed_width;
    // A horizontal finger stroke also gives directional brushes a defined angle.
    const fingerSample = [[16, 16, fallbackPressure], [44, 16, fallbackPressure]];
    for (const button of widths.querySelectorAll('button')) {
      const width = Number(button.dataset.width);
      button.hidden = fixed && width !== 1;
      button.querySelector('path').setAttribute('stroke-width', strokePoint(fingerSample, 1, ink.tool, width)[3]);
      const label = fixed ? 'Fixed' : Object.keys(state.widths)[width - 1];
      button.title = label;
      button.lastChild.textContent = label;
      button.setAttribute('aria-label', label + ' stroke');
      button.setAttribute('aria-pressed', String(width === ink.width));
    }
    const current = [ink.tool, ink.color, ink.width];
    if (activePreset === null) workingPreset = current;
    // The unsaved brush slot retains its settings while a saved slot is in use.
    const [workingTool, workingColor, workingWidth] = workingPreset || current;
    const name = Object.keys(state.tools).find(label => state.tools[label] === workingTool);
    const colorName = Object.keys(state.colors).find(label => state.colors[label] === workingColor);
    const widthName = brushFor(workingTool).fixed_width ? 'Fixed' : Object.keys(state.widths)[workingWidth - 1];
    brushToggle.innerHTML = svg(brushNib(workingTool)) + '<small></small>';
    brushToggle.lastChild.textContent = name;
    brushToggle.append(colorDisc(paletteColor(workingTool, workingColor), 'current-ink'));
    brushToggle.title = [name, colorName, widthName].join(' · ');
    brushToggle.setAttribute('aria-label', 'Working brush ' + brushToggle.title);
    brushToggle.setAttribute('aria-pressed', String(mode === 'ink' && activePreset === null));
    for (let id of ['erase', 'select']) control(id).setAttribute('aria-pressed', String(mode === id));
    syncPresets();
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
    restoreBrushSlot();
    sync()
  };
  sync();
  window.notebookViewportInsets(state.notebook_viewport_insets);
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
    const visible = el => el && !el.hidden && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden';
    const overlay = visible($('mobileSheet')) || !!document.querySelector('dialog[open]');
    const paper = $('paperWrap').getBoundingClientRect();
    const rect = [Math.max(0, r.left, v.left, paper.left), Math.max(0, r.top, v.top, paper.top),
      Math.min(innerWidth, r.right, v.right, paper.right), Math.min(innerHeight, r.bottom, v.bottom, paper.bottom)];
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
      pressureFactor: brushFor(ink.tool).pressure,
      pressureExponent: brushFor(ink.tool).exponent,
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
