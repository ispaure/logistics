// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

// Exercise production zoom functions with a deterministic clock, without a GUI.
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const source = fs.readFileSync(process.argv[2] || path.resolve(__dirname, '../../features/notebooks/assets/zoom.js'), 'utf8');
let checks = 0;
function fixture(mobile = true) {
  const nodes = new Map(), listeners = new Map(), timers = new Map(), frames = new Map();
  let now = 0, serial = 0, scale = 1;
  const classes = new Set(mobile ? ['notebook-mobile'] : []);
  function node(id) {
    return {id, value:'1', hidden:false, options:[{value:'1'},{value:'page'},{value:'fit'}],
      clientWidth:400,clientHeight:600,scrollLeft:0,scrollTop:0,style:{},classList:{remove(){},toggle(){}},
      setAttribute(name,value){this[name]=value},append(){},setPointerCapture(){},
      addEventListener(type,fn){const key=id+':'+type;(listeners.get(key)||listeners.set(key,[]).get(key)).push(fn)},
      closest(selector){return selector==='#viewport'?$('viewport'):null},
      getBoundingClientRect(){return {left:0,top:0,width:id==='paper'?1000*scale:400,height:id==='paper'?1500*scale:600}}};
  }
  const $=id=>{if(!nodes.has(id))nodes.set(id,node(id));return nodes.get(id)};
  const c={console,Map,Set,Math,$,innerWidth:400,innerHeight:600,
    document:{body:{classList:{contains:name=>classes.has(name)}},createElement:()=>node('new'),head:{append(){}},elementFromPoint:()=>$('paper')},
    getComputedStyle:()=>({paddingLeft:'0px',paddingRight:'0px'}),
    pageViewportSpace:()=>({width:400,height:600}),paperBounds:()=>({width:1000,height:1500}),
    window:{addEventListener(){}},canvas:$('paper'),state:{width:1000,height:1500},active:null,pan:null,paperView:'pro',
    resize(){const value=$('zoom').value;scale=['page','fit'].includes(value)?1:Number(value);vm.runInContext('updateZoomChrome()',c)},
    setTimeout(fn,delay){const id=++serial;timers.set(id,{fn,deadline:now+delay});return id},clearTimeout:id=>timers.delete(id),
    requestAnimationFrame(fn){const id=++serial;frames.set(id,fn);return id},cancelAnimationFrame:id=>frames.delete(id),
    beginPan(){},finish(){},penTouchBlocked:()=>false};
  vm.createContext(c);vm.runInContext(source,c);
  const run=code=>vm.runInContext(code,c),check=(value,message)=>{assert.ok(value,message);checks++};
  const advance=ms=>{now+=ms;for(const [id,timer]of [...timers])if(timer.deadline<=now){timers.delete(id);timer.fn()}};
  const emit=(type,event)=>{for(const fn of listeners.get('viewport:'+type)||[])fn(event)};
  run("createZoomControls($('zoomControls'))");
  return {c,$,run,check,advance,timers,emit,frames,classes};
}
let f=fixture();f.check(f.$('zoomControls').hidden,'mobile default hidden');
f.run('updateZoomChrome();resetViewportZoom(false);prepareViewportZoom();finishViewportZoom(null)');
f.check(f.$('zoomControls').hidden&&!f.timers.size,'initial/layout/page reset never reveals');
f.run("setZoom('2')");f.check(!f.$('zoomControls').hidden,'accepted zoom reveals');
f.advance(2000);f.run("setZoom('3')");f.advance(2999);f.check(!f.$('zoomControls').hidden,'fresh zoom restarts inactivity deadline');
f.advance(1);f.check(f.$('zoomControls').hidden,'hides three seconds after last zoom');
f.run("setZoom('3')");f.check(f.$('zoomControls').hidden,'unchanged two-finger pan scale does not reveal');
f.run("active=42;setZoom('2');$('zoomFit').onclick()");f.check(f.$('zoomControls').hidden&&!f.timers.size,'active pen rejects zoom/reset without showing');
f.run("active=null;setZoom('invalid')");f.check(f.$('zoomControls').hidden,'invalid zoom stays hidden');
f.run("window.notebookNativeZoom(1.2,100,100)");f.check(!f.$('zoomControls').hidden,'accepted native pinch reveals');f.advance(3000);
f.run("$('zoomFit').onclick()");f.check(!f.$('zoomControls').hidden,'explicit reset reveals');f.advance(3000);
f.run('updateZoomChrome();resetViewportZoom(false)');f.check(f.$('zoomControls').hidden,'passive page/layout update stays hidden after prior use');
f.run("paperView='move';$('zoomPageFit').onclick()");
f.check(f.$('zoom').value==='page'&&f.c.paperView==='pro'&&f.$('zoomPageFit')['aria-pressed']==='true',
  'Fit page selects the full page instead of the automatic phone strip');
f.run("$('zoomPageFill').onclick();rememberViewportZoom()");
f.c.innerWidth=800;f.c.innerHeight=400;
f.run('prepareViewportZoom();updateZoomChrome()');
f.check(f.$('zoom').value==='fill'&&f.$('zoomPageFill')['aria-pressed']==='true'&&f.$('zoomPageFit')['aria-pressed']==='false',
  'Fill stays selected after rotating and exposes its active state');
for (const [pageWidth,pageHeight] of [[1000,1500],[1500,1000]]) {
  const widthFit=400/pageWidth, heightFit=600/pageHeight;
  f.check(f.run(`pageZoomScale('page',${widthFit},${heightFit})`)===Math.min(widthFit,heightFit),'Fit contains portrait and landscape');
  f.check(f.run(`pageZoomScale('fill',${widthFit},${heightFit})`)===Math.max(widthFit,heightFit),'Fill covers portrait and landscape');
}
f.run("$('zoomFit').onclick();prepareViewportZoom();updateZoomChrome()");
f.check(f.$('zoomPageFit')['aria-pressed']==='false'&&f.$('zoomPageFill')['aria-pressed']==='false','Reset restores automatic framing');
f.advance(3000);
f.classes.add('tools-hidden');f.run("setZoom('2')");f.check(f.$('zoomControls').hidden&&!f.timers.size,'focus mode stays hidden');
f=fixture(false);f.check(!f.$('zoomControls').hidden,'desktop controls stay visible');f.run("setZoom('2')");f.check(!f.timers.size,'desktop has no mobile auto-hide timer');
// Real production touch handlers: an accepted pinch reveals, pen-owned contact does not.
f=fixture();const event=(id,x)=>({pointerId:id,pointerType:'touch',clientX:x,clientY:100,target:f.$('paper'),preventDefault(){},stopImmediatePropagation(){}});
f.c.active=7;f.emit('pointerdown',event(1,100));f.emit('pointerdown',event(2,200));
f.check(!f.frames.size&&f.$('zoomControls').hidden,'active pen prevents touch pinch admission');f.c.active=null;
f.emit('pointerdown',event(1,100));f.emit('pointerdown',event(2,200));f.emit('pointermove',event(2,250));
for(const [id,fn]of [...f.frames]){f.frames.delete(id);fn()}
f.check(!f.$('zoomControls').hidden,'actual production touch pinch reveals');
console.log(JSON.stringify({success:true,checks}));
