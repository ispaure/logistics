// Execute production touch arbitration, input, zoom and links in a tiny DOM.
const vm = require('node:vm');
function checkTouchNavigation(sources) {
  const listeners={document:{},viewport:{},window:{},canvas:{}};
  const commands=[],frames=new Map(),nodes=new Map();let now=1000,frame=0,width=2000,height=3000,checks=0;
  class Node {
    constructor(id){this.id=id;this.value='2';this.checked=false;this.style={};this.hidden=false;this.children=[];this.clientWidth=400;this.clientHeight=600;this.scrollLeft=500;this.scrollTop=600;this.options=[{value:'2'}];this.classList={contains:()=>false,add(){},remove(){},toggle(){}}}
    addEventListener(type,fn){const group=this.id==='viewport'?'viewport':this.id==='paper'?'canvas':null;if(group)(listeners[group][type]??=[]).push(fn)}
    setAttribute(){}append(...rows){this.children.push(...rows)}contains(node){return node===canvas||node===this}closest(){return null}
    getBoundingClientRect(){return this===canvas?{left:-viewport.scrollLeft,top:-viewport.scrollTop,width,height,right:width-viewport.scrollLeft,bottom:height-viewport.scrollTop}:{left:0,top:0,width:400,height:600,right:400,bottom:600}}
    setPointerCapture(){}showModal(){}close(){}
  }
  const $=id=>{if(!nodes.has(id))nodes.set(id,new Node(id));return nodes.get(id)};
  const canvas=$('paper'),viewport=$('viewport');
  const eventTarget=group=>({addEventListener(type,fn){(listeners[group][type]??=[]).push(fn)}});
  const context={console,Math,Map,Set,innerWidth:400,innerHeight:600,devicePixelRatio:1,
    document:{...eventTarget('document'),body:{append(){},classList:{contains:x=>x==='notebook-mobile'}},createElement:()=>new Node('new'),elementFromPoint:()=>canvas,hidden:false},
    window:{...eventTarget('window'),notebookUpdate(next){context.state=next;context.queue.shift();context.busy=false}},
    navigator:{platform:'MacIntel'},performance:{now:()=>now},$: $,canvas,ctx:{},
    state:{index:0,count:3,width:1000,height:1500,layers:[['L','Ink',true]],strokes:[],links:[]},
    active:null,pan:null,mode:'ink',busy:false,queue:[],points:[],selected:new Set(),start:null,last:null,
    pendingInk:null,continuousInk:false,frameBatchedInk:false,viewportResizePending:false,deferredUpdate:null,pageSwipe:true,previewCount:0,inkSettings:null,paperView:'pro',
    getComputedStyle:()=>({paddingLeft:'0',paddingRight:'0'}),
    requestAnimationFrame(fn){frames.set(++frame,fn);return frame},cancelAnimationFrame(id){frames.delete(id)},
    setTimeout(){return 1},clearTimeout(){},
    resize(){width=1000*Number($('zoom').value);height=1500*Number($('zoom').value)},
    chosenInk:()=>({tool:17,color:0,width:2,layer:'L'}),draw(){},cancelPreview(){},flushPreview(){},strokePoints:p=>p,nativeColor:()=>({}),
    previewErase(){},brushFor:()=>({family:'ballpoint'}),commitDraft(){},schedulePreview(){},
    send(action){commands.push(action);context.queue.push(action);context.busy=true}
  };
  vm.createContext(context);
  for(const source of sources)vm.runInContext(source,context);
  const run=text=>vm.runInContext(text,context),check=(v,label)=>{if(!v)throw Error(label);checks++};
  const event=(type,x=200,y=300,id=9,kind='touch',target=canvas)=>({type,pointerId:id,pointerType:kind,button:0,clientX:x,clientY:y,pressure:.5,target,preventDefault(){this.prevented=true},stopImmediatePropagation(){this.stopped=true}});
  function dispatch(e){for(const f of listeners.document[e.type]||[]){f(e);if(e.stopped)return}for(const f of listeners.viewport[e.type]||[]){f(e);if(e.stopped)return}if(e.target===canvas)canvas['on'+e.type]?.(e)}
  function reset(){run('cancelTouchZoom();resetPenRejection();pageTouch=null;pan=null;active=null;linkGesture=null;hideSwipePage();addingSwipePage=false;defaultViewportZoom=false;points=[]');context.state={index:0,count:3,width:1000,height:1500,layers:[['L','Ink',true]],strokes:[],links:[]};context.busy=false;context.queue=[];commands.length=0;context.mode='ink';$('finger').checked=false;$('zoom').value='2';width=2000;height=3000;viewport.scrollLeft=500;viewport.scrollTop=600;now+=2000}
  function swipe(dx,dy=0,target=canvas){dispatch(event('pointerdown',200,300,9,'touch',target));dispatch(event('pointermove',200+dx,300+dy,9,'touch',target));dispatch(event('pointerup',200+dx,300+dy,9,'touch',target))}
  reset();swipe(-100);check(commands.length===1&&commands[0].index===1,'zoomed single-finger swipe changes page');check(viewport.scrollLeft===500&&viewport.scrollTop===600,'single-finger swipe never pans');
  reset();swipe(0,-150);check(!commands.length&&viewport.scrollTop===600,'single-finger vertical drag never pans');
  reset();swipe(-100,0,viewport);check(commands[0]?.index===1&&viewport.scrollLeft===500,'margin swipe pages without panning');
  reset();context.state.links=[{rect:[0,0,1,1],index:2}];swipe(-100);check(commands.length===1&&commands[0].index===1,'swipe over link pages rather than follows link');
  reset();context.state.links=[{rect:[0,0,1,1],index:2}];dispatch(event('pointerdown'));dispatch(event('pointerup'));check(commands[0]?.index===2,'stationary link tap retained');
  reset();$('finger').checked=true;context.state.links=[{rect:[0,0,1,1],index:2}];swipe(-100);check(commands[0]?.index===1&&viewport.scrollLeft===500,'link swipe never pans with finger drawing enabled');
  reset();context.state.links=[{rect:[0,0,1,1],index:2}];dispatch(event('pointerdown'));dispatch(event('pointermove',230));dispatch(event('pointermove'));dispatch(event('pointerup'));check(!commands.length,'out-and-back cannot follow link');
  reset();context.state.index=2;swipe(-100);check(!commands.length&&!run('swipeAddPage.hidden'),'last-page swipe offers creation without creating');run('swipeAddPage.onclick()');check(commands.length===1&&commands[0].op==='add-page','button explicitly creates page');run('swipeAddPage.onclick()');check(commands.length===1,'busy button cannot duplicate creation');context.window.notebookUpdate({...context.state,index:3,count:4});check(run('swipeAddPage.hidden'),'successful creation retires offer');
  reset();context.state.index=2;swipe(-100);run('swipeAddPage.onclick()');context.window.notebookUpdate({...context.state},'failed');check(!run('swipeAddPage.hidden')&&!run('swipeAddPage.disabled'),'failed creation retains retry offer');
  reset();context.state.index=2;context.state.read_only=true;swipe(-100);check(run('swipeAddPage.hidden')&&!commands.length,'read-only page offers no creation');
  reset();swipe(100);check(!commands.length,'first-page back swipe stays bounded');
  reset();dispatch(event('pointerdown',100,100,1));dispatch(event('pointerdown',200,100,2));dispatch(event('pointermove',130,120,1));dispatch(event('pointermove',230,120,2));dispatch(event('pointerup',230,120,2));check(Math.abs(viewport.scrollLeft-470)<.001&&Math.abs(viewport.scrollTop-580)<.001,'two fingers pan horizontally and vertically');check(!commands.length,'two-finger pan never changes pages');const position=[viewport.scrollLeft,viewport.scrollTop];dispatch(event('pointermove',10,120,1));dispatch(event('pointerup',10,120,1));check(!commands.length&&viewport.scrollLeft===position[0]&&viewport.scrollTop===position[1],'remaining finger does not navigate or pan');
  reset();dispatch(event('pointerdown',100,100,1));dispatch(event('pointerdown',200,100,2));dispatch(event('pointermove',250,100,2));dispatch(event('pointerup',250,100,2));dispatch(event('pointerup',100,100,1));check(Math.abs(width-3000)<.001&&!commands.length,'two-finger pinch retained');
  reset();dispatch(event('pointerdown'));dispatch(event('pointercancel'));dispatch(event('pointerup',100));check(!commands.length,'cancelled swipe cannot navigate');
  reset();dispatch(event('pointerdown'));run("notePenHover('native',true);notePenHover('native',false)");now+=2000;dispatch(event('pointerup',100));check(!commands.length,'pen proximity cancels candidate beyond grace');
  reset();dispatch(event('pointerdown'));now+=1000;dispatch(event('pointerup',100));check(!commands.length,'long drag cannot page');
  reset();dispatch(event('pointerdown'));context.state.index=1;dispatch(event('pointerup',100));check(!commands.length,'stale page gesture rejected');
  reset();$('finger').checked=true;swipe(-100);check(commands[0]?.op==='stroke','explicit finger drawing retained');
  reset();dispatch(event('pointerdown',200,300,9,'pen'));dispatch(event('pointerup',200,300,9,'pen'));check(commands[0]?.op==='stroke','pen still draws');
  return {success:true,checks}
}
module.exports={checkTouchNavigation};
if(require.main===module){const fs=require('node:fs'),path=require('node:path');const root=path.resolve(__dirname,'../../features/notebooks/assets');console.log(JSON.stringify(checkTouchNavigation(['palm.js','input.js','zoom.js','links.js','touch_navigation.js'].map(name=>fs.readFileSync(path.join(root,name),'utf8')))))}
