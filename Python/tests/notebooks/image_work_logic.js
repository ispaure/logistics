/* Pure JS gesture regression. Native raster and file-picker acceptance is separate. */
export default function(source, vm, assert, inputSource = '') {
  const controls = new Map(), commands = [], paint = [], listeners = new Map();
  function node() {
    return {set id(value){controls.set(value,this)},style:{}, dataset:{}, classList:{add(){},remove(){},toggle(){}}, append(){}, insertBefore(){},
      setAttribute(){},addEventListener(){},set innerHTML(html) { for(const match of html.matchAll(/id="([^"]+)"/g)) controls.set(match[1],node()) }};
  }
  const context = {save(){},restore(){},transform(){},drawImage(...args){paint.push(['image',...args])},beginPath(){},moveTo(){},lineTo(){},closePath(){},stroke(){},fill(){},arc(){},fillRect(){},clip(){paint.push(['clip'])},scale(){},translate(){}};
  const canvas = {...node(),width:1404,height:1872,getBoundingClientRect(){return {left:0,top:0,width:1404,height:1872}},setPointerCapture(){},getContext(){return context},toDataURL(){return 'data:image/png;base64,synthetic'},onpointerdown(){},onpointermove(){},onpointerup(){},onpointercancel(){}};
  for(const id of ['viewport','erase','select','tool','status','layer','pdfBackground']) controls.set(id,node());
  controls.get('layer').value='L';
  controls.get('pdfBackground').complete=true;controls.get('pdfBackground').naturalWidth=1404;controls.get('pdfBackground').naturalHeight=1872;
  const document={elementFromPoint(){return canvas},body:node(),querySelector(){return node()},createElement(tag){return tag==='canvas'?{...canvas}:node()},addEventListener(type,handler){listeners.set(type,handler)}};
  const sandbox={document,console,Map,Set,Image:class{constructor(){this.complete=true;this.naturalWidth=16}},ctx:context,canvas,
    state:{page_id:'page-A',width:1404,height:1872,index:0,strokes:[],images:[],layers:[['L','Layer',true]],scene_order:[]},
    deferredUpdate:null,viewportResizePending:false,mode:'ink',selected:new Set(),active:null,busy:false,points:[],start:null,last:null,
    $:id=>controls.get(id),draw(){},coord:e=>[e.clientX,e.clientY,.5],penTouchBlocked:()=>false,
    notePenContact(){},flushUpdate(){},send:command=>commands.push(command),line:s=>paint.push(['stroke',s.id])};
  sandbox.window=sandbox;sandbox.innerWidth=1404;sandbox.innerHeight=1872;
  vm.createContext(sandbox);if(inputSource)vm.runInContext(inputSource,sandbox);vm.runInContext(source,sandbox);
  const run = code=>vm.runInContext(code,sandbox), event=(x,y,type='touch')=>({pointerId:7,pointerType:type,nativePen:true,clientX:x,clientY:y,preventDefault(){}});
  controls.get('capture').onclick();assert.equal(sandbox.mode,'capture');
  const picture={id:'P',layer:'L',src:'data:image/png;base64,synthetic',corners:[[100,100],[300,100],[300,250],[100,250]]};
  sandbox.state.images=[picture];run('imageRender()');
  canvas.onpointerdown(event(150,150));canvas.onpointermove(event(190,180));canvas.onpointerup(event(190,180));
  assert.equal(commands.at(-1).op,'image-transform');assert.deepEqual(JSON.parse(JSON.stringify(commands.at(-1).corners)),[[140,130],[340,130],[340,280],[140,280]]);
  assert.deepEqual(sandbox.state.images[0].corners,picture.corners,'Host owns durable geometry after pointer-up');
  if(inputSource) {
    sandbox.state.native_pen=true;
    sandbox.logisticsNativePen('down',11,[[150,150,.5]],1404,1872);
    sandbox.logisticsNativePen('move',11,[[170,160,.5]],1404,1872);
    sandbox.logisticsNativePen('up',11,[[180,170,.5]],1404,1872);
    assert.equal(commands.at(-1).op,'image-transform','Native pen-up reaches image commit');
    sandbox.state.native_pen=false;
  }
  controls.get('imageRotate').onclick();assert.equal(commands.at(-1).op,'image-transform');
  assert.ok(Math.abs(commands.at(-1).corners[0][1]-100)>10);
  controls.get('imageArrange').value='back';controls.get('imageArrange').onchange();assert.equal(commands.at(-1).direction,'back');
  picture.corners=[[120,90],[300,210],[210,345],[30,225]];
  controls.get('copyImage').onclick();sandbox.state.index=1;sandbox.state.page_id='page-B';sandbox.state.images=[];run('imageRender()');controls.get('pasteImage').onclick();controls.get('pasteImage').onclick();
  assert.equal(commands.filter(c=>c.op==='paste-image').length,2,'Clipboard survives page changes and repeated paste');
  assert.deepEqual(JSON.parse(JSON.stringify(commands.at(-1).corners)),picture.corners,'Cross-page paste preserves original page geometry');
  const prior=commands.length; sandbox.mode='select';listeners.get('keydown')({target:{tagName:'DIV'},ctrlKey:true,key:'v',preventDefault(){}});assert.equal(commands.length,prior,'Image clipboard must not intercept Select-mode paste');sandbox.mode='capture';
  sandbox.state.index=0;sandbox.state.page_id='page-A';sandbox.state.images=[picture];sandbox.state.background='background';sandbox.state.strokes=[{id:'A',layer:'L'},{id:'B',layer:'L'}];sandbox.state.scene_order=['A','P','B'];
  run('imageRender(); captureCutout([[0,0],[400,0],[200,400]])');
  assert.ok(paint.some(p=>p[0]==='clip'),'Capture clips the polygon');
  assert.deepEqual(paint.filter(p=>p[0]==='stroke').map(p=>p[1]),['A','B']);
  controls.get('pdfBackground').naturalWidth=1000;controls.get('pdfBackground').naturalHeight=500;run('captureCutout([[0,0],[400,0],[200,400]])');
  const bgPaint=paint.filter(p=>p[0]==='image' && p[1]===controls.get('pdfBackground')).at(-1);assert.deepEqual(bgPaint.slice(2),[0,585,1404,702],'Capture background must match CSS object-fit contain');
  controls.get('pdfBackground').naturalWidth=1404;controls.get('pdfBackground').naturalHeight=1872;
  controls.get('newCutout').onclick();canvas.onpointerdown(event(150,150));assert.equal(run('imageGesture'),null,'Explicit lasso can start inside an image');canvas.onpointercancel(event(150,150));
  canvas.onpointerdown(event(150,150));canvas.onpointerup(event(150,150));controls.get('cutImage').onclick();assert.equal(commands.at(-1).op,'delete-image','Cut commits source deletion');assert.deepEqual(JSON.parse(JSON.stringify(run('imageClipboard.sourceCorners'))),picture.corners);
  const before=commands.length;canvas.onpointerdown(event(50,50));canvas.onpointermove(event(60,60));canvas.onpointercancel(event(60,60));assert.equal(commands.length,before,'Cancelled gesture does not commit');
  sandbox.state.password_required=true;run('imageRender()');canvas.onpointerdown(event(150,150));assert.equal(sandbox.active,null,'Locked page rejects capture');
  assert.equal(controls.get('viewport').style.visibility,'hidden');
  return {passed:true,background_proportions:true, finger_move:true,rotate:true,arrange:true,repeat_paste_across_pages:true,lasso_clips:true,mixed_scene:true,cancel:true,password_gate:true,cross_page_origin:true,rotated_scaled_copy:true,image_cut:true,select_mode_paste_isolation:true};
};
