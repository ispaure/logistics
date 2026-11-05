const fs=require('fs'),vm=require('vm'),assert=require('assert');
const path=require('path');
const src=fs.readFileSync(process.argv[2] || path.resolve(__dirname,'../../features/notebooks/assets/mobile.js'),'utf8');
const block=src.slice(src.indexOf('  let nativeToolsLease = null,'),src.indexOf('  function closeSheet(restoreFocus'));
const classes=new Set(), clicks=[], timers=new Map();let serial=0;
function button(name){return {disabled:false,pressed:name==='pen',getAttribute(){return String(this.pressed)},click(){clicks.push(name);this.pressed=true}}}
const buttons=Object.fromEntries(['pen','erase','select','undo','redo'].map(n=>[n,button(n)]));buttons.redo.disabled=true;
const context={window:{},document:{body:{classList:{add:n=>classes.add(n),remove:n=>classes.delete(n),contains:n=>classes.has(n)}}},
 active:null,busy:false,queue:[],resize:()=>{},dismissToolPanels:()=>{},header:{inert:false},dock:{inert:false},brushToggle:buttons.pen,control:n=>buttons[n],
 setTimeout:(f,ms)=>{f.delay=ms;timers.set(++serial,f);return serial},clearTimeout:id=>timers.delete(id)};
vm.createContext(context);vm.runInContext(block,context);
let state=JSON.parse(context.window.notebookNativeTools(null));assert(state.redo.disabled);assert(state.pen.active);assert(classes.has('native-drawing-tools'));
context.window.notebookNativeTools({name:'undo',anchor:[100,-48,44,48]});assert.deepEqual(clicks,['undo']);
context.window.notebookNativeTools({name:'redo',anchor:[100,-48,44,48]});assert.deepEqual(clicks,['undo']);
context.active=1;context.window.notebookNativeTools({name:'erase',anchor:[100,-48,44,48]});assert.deepEqual(clicks,['undo']);assert(classes.has('native-drawing-tools'));[...timers.values()].at(-1)();assert(classes.has('native-drawing-tools'));context.active=null;context.window.notebookNativeTools(null);
assert(classes.has('native-drawing-tools'), 'Ending a contact must retain the live lease');
context.busy=true;context.window.notebookNativeTools(null);context.busy=false;
assert.equal([...timers.values()].at(-1).delay,1500);
assert(classes.has('native-drawing-tools'), 'A busy heartbeat must renew the live lease');
[...timers.values()].at(-1)();assert(!classes.has('native-drawing-tools'));
context.header.inert=true;state=JSON.parse(context.window.notebookNativeTools({name:'select',anchor:[100,-48,44,48]}));assert(state.select.disabled);assert.deepEqual(clicks,['undo']);context.header.inert=false;
assert.throws(()=>context.window.notebookNativeTools({name:'delete-file',anchor:[100,-48,44,48]}),/Unknown/);
context.window.notebookNativeTools(null);[...timers.values()].at(-1)();assert(!classes.has('native-drawing-tools'));
context.window.notebookNativeTools(null);context.window.notebookNativeTools(false);assert(!classes.has('native-drawing-tools'));
console.log('Production dispatcher: exact handlers, disabled/modal/pen guards, state and lease restoration PASS');

context.window.notebookNativeTools(null);classes.add('tools-hidden');assert.equal(JSON.parse(context.window.notebookNativeTools(null)),null);
assert(classes.has('native-drawing-tools'));
classes.delete('tools-hidden');
assert(JSON.parse(context.window.notebookNativeTools(null)).pen.active);
assert(classes.has('native-drawing-tools'));
