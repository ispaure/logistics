// Execute production Select handlers in V8. This is independent of native UI/raster acceptance.
const vm = require('node:vm');
const assert = require('node:assert/strict');

function checkSelectionGestures(source, inputSource = '', linksSource = '', imagesSource = '') {
  const controls = new Map(), commands = [], paints = [];
  function eventTarget() {
    const listeners = new Map();
    return {
      addEventListener(name, callback) {
        if (!listeners.has(name)) listeners.set(name, []);
        if (!listeners.get(name).includes(callback)) listeners.get(name).push(callback);
      },
      dispatchEvent(event) {for (const callback of listeners.get(event.type) || []) callback(event)}
    };
  }
  // Browser EventTargets keep ordered listener lists separately per target.
  const targetA = eventTarget(), targetB = eventTarget(), observed = [];
  const first = () => observed.push('first');
  targetA.addEventListener('shared', first); targetA.addEventListener('shared', first);
  targetA.addEventListener('shared', () => observed.push('second'));
  targetB.addEventListener('shared', () => observed.push('other-target'));
  targetA.dispatchEvent({type:'shared'});
  assert.deepEqual(observed, ['first', 'second']);
  targetB.dispatchEvent({type:'shared'});
  assert.deepEqual(observed, ['first', 'second', 'other-target']);
  function node() {
    return {...eventTarget(), set id(value) {controls.set(value, this)}, style: {}, dataset: {}, checked: false,
      classList: {add() {}, remove() {}, toggle() {}, contains() {return false}},
      append() {}, appendChild() {}, insertBefore() {}, setAttribute() {},
      getBoundingClientRect() {return {left: 0, top: 0, width: 1404, height: 1872}},
      set innerHTML(html) {for (const match of html.matchAll(/id="([^"]+)"/g)) controls.set(match[1], node())}};
  }
  const ctx = new Proxy({}, {get(target, key) {
    if (!(key in target)) target[key] = (...args) => paints.push([key, ...args]);
    return target[key]
  }});
  const canvas = {...node(), width: 1404, height: 1872, setPointerCapture() {},
    getContext() {return ctx}, onpointerdown() {}, onpointermove() {}, onpointerup() {},
    onpointercancel() {}, onlostpointercapture() {}};
  for (const id of ['viewport', 'paperWrap', 'inkLayers', 'erase', 'select', 'tool', 'status', 'layer', 'finger', 'capture']) controls.set(id, node());
  controls.get('layer').value = 'L';
  const document = {...eventTarget(), body: node(), head: node(), createElement: node, elementFromPoint() {return canvas},
    querySelector(selector) {return selector==='header'?node():null}};
  document.body.classList.contains = value => value === 'notebook-mobile';
  const sandbox = {console, document, Image: class {constructor() {this.complete=true;this.naturalWidth=16}}, navigator: {platform: 'iPhone'}, canvas, ctx, Map, Set, Math, performance: {now: () => 1000},
    innerWidth: 1404, innerHeight: 1872,
    state: {width: 1404, height: 1872, index: 0, layers: [['L', 'Layer', true], ['H', 'Hidden', false]],
      strokes: [], images: [], scene_order: [], links: [{rect: [0,0,1,1], index: 1}]},
    mode: 'select', selected: new Set(), active: null, busy: false, points: [], start: null, last: null,
    pan: null, queue: [], deferredUpdate: null, viewportResizePending: false, penContactActive: false,
    touchContacts: new Map(), continuousInk: false, frameBatchedInk: false,
    $: id => controls.get(id), coord: e => [e.clientX, e.clientY, .5],
    distance(p, a, b) {const dx=b[0]-a[0],dy=b[1]-a[1],d=dx*dx+dy*dy;
      const t=d?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/d)):0;
      return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)},
    draw() {if (sandbox.paintSelection) sandbox.paintSelection()}, render() {}, clearDraft() {}, penTouchBlocked: () => false,
    notePenContact() {}, cancelTouchZoom() {}, flushUpdate() {}, cancelPreview() {}, flushPreview() {},
    send(command) {commands.push(command)}, chosenInk: () => ({tool: 17, color: 0, width: 2}),
    window: {notebookUpdate(next) {sandbox.state = next}},
    ...eventTarget(), setTimeout, clearTimeout};
  sandbox.window = sandbox;
  sandbox.notebookUpdate = next => {sandbox.state = next};
  vm.createContext(sandbox);
  if (inputSource) vm.runInContext(inputSource, sandbox);
  if (imagesSource) vm.runInContext(imagesSource, sandbox);
  vm.runInContext(source, sandbox);
  if (linksSource) vm.runInContext(linksSource, sandbox);
  const run = code => vm.runInContext(code, sandbox);
  const plain = value => JSON.parse(JSON.stringify(value));
  const event = (x, y, pointerType = 'touch') => ({pointerId: 7, pointerType,
    nativePen: true, clientX: x, clientY: y, pressure: .5, preventDefault() {}});
  canvas.dispatchEvent({...event(0,0,'pen'),type:'pointerdown'});
  assert.equal(sandbox.logisticsInputTrace().counts['delivered-pointerdown:pen'],1,
    'Actual input diagnostic listeners remain independently registered on the canvas');
  const stroke = (id, points, layer = 'L') => ({id, layer, tool: 17, color: 0,
    points: points.map(([x,y,w=2]) => [x,y,.5,w])});
  const polygon = [[80,80],[320,80],[320,320],[80,320]];
  const inside = stroke('A', [[120,120],[240,240]]);
  const partial = stroke('B', [[200,200],[400,200]]);
  assert.equal(run(`selectionContains(${JSON.stringify(inside)}, ${JSON.stringify(polygon)})`), true);
  assert.equal(run(`selectionContains(${JSON.stringify(partial)}, ${JSON.stringify(polygon)})`), false,
    'A partly enclosed stroke must be omitted');
  // Both endpoints are inside the U, but its segment crosses the missing center.
  const concave = [[0,0],[400,0],[400,400],[280,400],[280,120],[120,120],[120,400],[0,400]];
  assert.equal(run(`selectionContains(${JSON.stringify(stroke('C',[[60,280],[340,280]]))}, ${JSON.stringify(concave)})`), false,
    'Checking endpoints alone must not select a segment outside a concave lasso');
  assert.equal(run(`selectionContains(${JSON.stringify(stroke('wide',[[85,150,20]]))}, ${JSON.stringify(polygon)})`), false,
    'Painted stroke diameter must fit inside the lasso');
  sandbox.state.strokes = [inside, partial, stroke('H',[[150,150]],'H')];
  const lasso = (type = 'touch') => {
    canvas.onpointerdown(event(...polygon[0],type));
    for (const p of polygon.slice(1)) canvas.onpointermove(event(...p,type));
    canvas.onpointerup(event(...polygon[0],type));
  };
  for (const type of ['touch','pen','mouse']) {
    sandbox.selected = new Set();
    lasso(type);
    assert.deepEqual([...sandbox.selected], ['A'], `${type} lasso must contain complete visible strokes only`);
  }
  assert.equal(controls.get('finger').checked, false, 'Finger selection does not require finger drawing');
  assert.equal(commands.length, 0, 'Selecting a lasso must not save a transform');

  const original = plain(sandbox.state.strokes);
  let bounds = plain(run('selectionBounds()'));
  assert.equal(bounds.length, 4);
  const corners = plain(run('selectionHandles(selectionBounds())'));
  assert.equal(corners.length, 5, 'Four square corner handles and one rotation handle');
  const center = [(bounds[0]+bounds[2])/2,(bounds[1]+bounds[3])/2];
  // Corner drag changes one scalar, keeping the original aspect ratio.
  canvas.onpointerdown(event(...corners[0], 'pen'));
  canvas.onpointermove(event(2*corners[0][0]-center[0],2*corners[0][1]-center[1], 'pen'));
  const preview = plain(sandbox.state.strokes[0].points);
  assert.equal(preview[1][0]-preview[0][0], 240);
  assert.equal(preview[1][1]-preview[0][1], 240);
  assert.equal(preview[0][3], 4, 'Uniform scale includes painted diameter');
  assert.equal(preview[0][2], .5, 'Transforms preserve pressure');
  canvas.onpointerup(event(2*corners[0][0]-center[0],2*corners[0][1]-center[1], 'pen'));
  assert.equal(commands.at(-1).op, 'transform');
  assert.equal(commands.at(-1).scale, 2);
  assert.deepEqual(plain(sandbox.state.strokes), original, 'Host owns durable geometry after gesture preview');
  assert.equal(commands.at(-1).angle, 0);
  // Radial travel itself does not rotate. Tangential travel is finer farther out.
  const rotate = corners[4];
  canvas.onpointerdown(event(...rotate));
  canvas.onpointerup(event(rotate[0]+30,rotate[1]));
  const nearAngle = Math.abs(commands.at(-1).angle);
  canvas.onpointerdown(event(...rotate));
  canvas.onpointermove(event(rotate[0],rotate[1]-60));
  canvas.onpointerup(event(rotate[0]+30,rotate[1]-60));
  assert.ok(Math.abs(commands.at(-1).angle) < nearAngle, 'Rotation becomes finer farther from its center');
  assert.equal(commands.at(-1).scale, 1);
  const fartherAngle=Math.abs(commands.at(-1).angle);
  canvas.onpointerdown(event(...rotate));
  canvas.onpointermove(event(rotate[0],-400));
  canvas.onpointerup(event(rotate[0]+30,-400));
  assert.ok(Math.abs(commands.at(-1).angle)<fartherAngle,'Rotation remains finer when captured pointer travels outside the paper');
  const beforeCancel = commands.length;
  canvas.onpointerdown(event(...center));canvas.onpointermove(event(center[0]+20,center[1]+30));
  canvas.onpointercancel(event(center[0]+20,center[1]+30));
  assert.equal(commands.length, beforeCancel, 'Cancelled transform cannot save');
  assert.deepEqual(plain(sandbox.state.strokes), original, 'Cancelled preview restores original geometry');
  sandbox.state.native_pen = true;
  sandbox.logisticsNativePen('down',11,[[...center,.5]],1404,1872);
  sandbox.logisticsNativePen('move',11,[[center[0]+20,center[1]+30,.5]],1404,1872);
  sandbox.logisticsNativePen('up',11,[[center[0]+20,center[1]+30,.5]],1404,1872);
  assert.ok(Math.abs(commands.at(-1).dx-20)<1e-8, 'Native pen-up dispatches through actual finish to selection');
  assert.ok(Math.abs(commands.at(-1).dy-30)<1e-8);
  sandbox.state.native_pen = false;
  controls.get('copyStrokes').onclick();
  assert.equal(commands.at(-1).op, 'copy-strokes');
  assert.deepEqual(plain(commands.at(-1).ids), ['A']);
  assert.equal(sandbox.selected.size, 1, 'Copy retains selection');
  sandbox.state.stroke_clipboard = true;
  sandbox.state.index = 1;run('selectionRender()');
  assert.equal(sandbox.selected.size, 0, 'Page navigation clears stale selected IDs');
  controls.get('pasteStrokes').onclick();controls.get('pasteStrokes').onclick();
  assert.equal(commands.filter(command => command.op === 'paste-strokes').length, 2,
    'Paste remains available across pages and repeated pastes');
  sandbox.state.index=0;sandbox.selected=new Set(['A']);
  controls.get('cutStrokes').onclick();
  assert.equal(commands.at(-1).op, 'cut-strokes');assert.equal(sandbox.selected.size,0);
  sandbox.selected=new Set(['A']);controls.get('deleteStrokes').onclick();
  assert.equal(commands.at(-1).op, 'erase');assert.equal(sandbox.selected.size,0);
  const pasted=stroke('Pasted',[[140,140],[180,180]]);
  sandbox.queue.push({op:'paste-strokes'});
  sandbox.notebookUpdate({...sandbox.state,strokes:[...sandbox.state.strokes,pasted],selection_ids:['Pasted']});
  sandbox.queue=[];
  assert.deepEqual([...sandbox.selected],['Pasted'],'Paste acknowledgement selects fresh native IDs');
  for(const operation of ['transform','copy-strokes','undo','redo','page']) {
    sandbox.queue=[{op:operation}];
    sandbox.notebookUpdate({...sandbox.state,selection_ids:operation==='undo'?[]:['Pasted']});
    assert.deepEqual([...sandbox.selected],operation==='undo'?[]:['Pasted'],`${operation} acknowledgement uses current host selection`);
  }
  sandbox.queue=[];
  if(imagesSource) {
    run("imageClipboard={src:'data:image/png;base64,synthetic',width:100,height:80}");
    sandbox.state.stroke_clipboard=true;
    const key=letter=>({key:letter,ctrlKey:true,target:{tagName:'BODY'},preventDefault(){}});
    const dispatch=letter=>document.dispatchEvent({...key(letter),type:'keydown'});
    let before=commands.length;
    sandbox.mode='select';dispatch('v');
    assert.equal(commands.length,before+1,'Select paste must issue exactly one command despite both clipboards');
    assert.equal(commands.at(-1).op,'paste-strokes','Select paste must use native ink clipboard');
    sandbox.selected=new Set(['Pasted']);before=commands.length;dispatch('c');
    assert.equal(commands.length,before+1);assert.equal(commands.at(-1).op,'copy-strokes');
    sandbox.mode='capture';before=commands.length;dispatch('v');
    assert.equal(commands.length,before+1);assert.equal(commands.at(-1).op,'paste-image','Capture paste uses only image clipboard');
    sandbox.mode='ink';before=commands.length;dispatch('v');
    assert.equal(commands.length,before,'Inactive clipboard modes must not paste');
    sandbox.mode='select';
    const query=document.querySelector;
    document.querySelector=selector=>selector.startsWith('dialog[open]')?node():query(selector);
    before=commands.length;dispatch('v');dispatch('Delete');
    assert.equal(commands.length,before,'An open dialog or mobile sheet blocks background selection shortcuts');
    document.querySelector=query;
  }
  // Repeated point work is bounded across the entire gesture; an earlier
  // accepted stroke must not survive if a later stroke exhausts the budget.
  sandbox.state.strokes=[stroke('first',[[120,120]]),stroke('complex',Array.from({length:100},()=>[120,120]))];
  sandbox.selected=new Set();
  run('selectionPrepareSaved=selectionPrepare;selectionPreparationCalls=0;selectionPrepare=path=>{if(Array.isArray(path))selectionPreparationCalls++;const index=selectionPrepareSaved(path);index.limit=35;return index}');
  lasso();
  assert.equal(sandbox.selected.size,0,'Work abort must clear the whole selection, including earlier accepted strokes');
  assert.equal(run('selectionPreparationCalls'),1,'Lasso polygon is prepared once for all page strokes');
  assert.match(controls.get('status').textContent,/complex/);
  run('selectionPrepare=selectionPrepareSaved');
  sandbox.state.strokes=original;
  sandbox.selected=new Set(['A']);run('selectionRender()');
  sandbox.state.page_id='new-stable-page';run('selectionRender()');
  assert.equal(sandbox.selected.size,0,'A new stable page ID clears selection even if its index is unchanged');
  const beforeLocked=commands.length;
  for(const field of ['read_only','password_required']) {
    sandbox.state[field]=true;
    canvas.onpointerdown(event(100,100));assert.equal(sandbox.active,null);
    controls.get('pasteStrokes').onclick();assert.equal(commands.length,beforeLocked);
    sandbox.state[field]=false;
  }
  sandbox.penTouchBlocked=()=>true;
  canvas.onpointerdown(event(100,100));assert.equal(sandbox.active,null,'Palm rejection still blocks touch selection');
  sandbox.state.strokes=[stroke('tiny',[[700,700,.5]])];sandbox.selected=new Set(['tiny']);run('selectionRender()');
  const tinyCorner=plain(run('selectionHandles(selectionBounds())[0]')),beforeTiny=commands.length;
  canvas.onpointerdown(event(...tinyCorner,'mouse'));canvas.onpointerup(event(...tinyCorner,'mouse'));
  assert.equal(commands.length,beforeTiny,'Tapping a sub-unit dot corner must not shrink it');
  return {passed: true, full_containment: true, painted_radius: true, concave_segments: true,
    hidden_layers: true, finger_pen_mouse: true, finger_ink_disabled: true,
    uniform_scale: true, fine_rotation: true, cancelled_preview_restored: true,
    native_pen_finish: true, clipboard_actions: true, cross_page_repeat_paste: true,
    locked_pages: true, select_over_pdf_links: !!linksSource, offpage_fine_rotation: true,
    host_selection_normalization: true, whole_selection_work_abort: true, stable_page_identity: true, dual_clipboard_shortcuts: !!imagesSource};
}
module.exports = {checkSelectionGestures};
if (require.main === module) {
  const fs = require('node:fs'), path = require('node:path');
  const assets = path.resolve(__dirname, '../../features/notebooks/assets');
  console.log(JSON.stringify(checkSelectionGestures(fs.readFileSync(path.join(assets,'selection.js'),'utf8'),
    fs.readFileSync(path.join(assets,'input.js'),'utf8'),fs.readFileSync(path.join(assets,'links.js'),'utf8'),fs.readFileSync(path.join(assets,'images.js'),'utf8'))));
}
