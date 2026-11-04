// Execute the native QA fixture with the actual shared input/palm/zoom owners.
// The outer clock models elapsed time; the fixture never changes production time.
const vm = require('node:vm');
const assert = require('node:assert/strict');
function checkNativePointerContract(bundle) {
  function scene(seed=true) {
    let now=1000;
    function target() {
      const listeners=new Map();
      return {listeners,addEventListener(name,callback,options={}) {
        if(!listeners.has(name))listeners.set(name,[]);
        listeners.get(name).push({callback,capture:!!options.capture})
      }}
    }
    const viewport={...target(),clientWidth:400,clientHeight:700,scrollLeft:11,scrollTop:23};
    const finger={checked:false}, canvas={...target(),style:{},setPointerCapture(){},
      getBoundingClientRect:()=>({left:0,top:0,width:400,height:700})};
    const document={...target(),hidden:false,elementFromPoint:()=>canvas};
    class PointerEvent {
      constructor(type,values){Object.assign(this,values);this.type=type;this.isTrusted=false}
      preventDefault(){this.defaultPrevented=true}
      stopImmediatePropagation(){this.stopped=true}
    }
    canvas.dispatchEvent=e=>{
      e.target=canvas;
      for(const {callback,capture}of viewport.listeners.get(e.type)||[])if(capture&&!e.stopped)callback(e);
      for(const {callback}of canvas.listeners.get(e.type)||[])if(!e.stopped)callback(e);
      if(!e.stopped)canvas['on'+e.type]?.(e);
      for(const {callback,capture}of viewport.listeners.get(e.type)||[])if(!capture&&!e.stopped)callback(e);
      return !e.defaultPrevented
    };
    const context={console,Map,Set,Math,JSON,PointerEvent,canvas,document,
      window:target(),zoomViewport:viewport,innerWidth:400,innerHeight:700,
      performance:{now:()=>now},$:id=>id==='finger'?finger:viewport,
      state:{width:1404,height:1872,layers:[['L','Ink',true]],strokes:[],native_pen:true},
      active:null,pan:null,mode:'ink',points:[],selected:new Set(),start:null,last:null,
      pendingInk:null,inkSettings:null,continuousInk:false,frameBatchedInk:false,
      busy:false,queue:[],pageSwipe:false,previewCount:0,viewportResizePending:false,deferredUpdate:null,
      trackpadGesture:null,minZoom:.1,maxZoom:4,chosenInk:()=>({tool:17,color:0,width:2}),
      brushFor:()=>({family:'fineliner'}),nativeColor:()=>({color:0}),
      strokePoints:rows=>rows.map(p=>[...p,2]),
      send(){throw Error('Fixture leaked a durable ink command')},draw(){},flushPreview(){},cancelPreview(){},
      schedulePreview(){},previewErase(){},setZoom(){},
      requestAnimationFrame:()=>1,cancelAnimationFrame(){},setTimeout(){},clearTimeout(){}};
    vm.createContext(context);
    vm.runInContext(bundle.palm,context);
    vm.runInContext(bundle.input.slice(0,bundle.input.indexOf('// Android supplies')),context);
    vm.runInContext(bundle.zoom.slice(bundle.zoom.indexOf('const touchContacts = new Map();'),bundle.zoom.indexOf('// Native desktop palette')),context);
    const run=code=>vm.runInContext(code,context);
    // Nonempty original state proves fixture cleanup restores rather than clears.
    if(seed)run("penHoverSources.add('existing-observer');penBlockedUntil=2000;touchContacts.set(701,{x:1,y:2})");
    const snapshot=()=>run('JSON.stringify({active,mode,penContactActive,penBlockedUntil,hover:[...penHoverSources],contacts:[...touchContacts],native:state.native_pen,finger:$("finger").checked,scroll:[$("viewport").scrollLeft,$("viewport").scrollTop],fixture:!!window.notebookPointerProbe})');
    return {run,snapshot,context,advance:amount=>{now+=amount}}
  }
  const old=scene(false);
  if(bundle.legacy)assert.throws(()=>old.run(bundle.legacy),/Explicit finger drawing failed/,
    'The compiled-70b fixture must reproduce the exact observed failure');
  const corrected=scene(),original=corrected.snapshot();
  assert.equal(JSON.parse(corrected.run(bundle.begin)).release_grace_blocked,true);
  const grace=corrected.run('penReleaseGrace');
  corrected.advance(grace-1);assert.equal(JSON.parse(corrected.run(bundle.ready)).blocked,true);
  corrected.advance(2);assert.equal(JSON.parse(corrected.run(bundle.ready)).blocked,false);
  const report=JSON.parse(corrected.run(bundle.complete));
  assert.equal(report.release_grace_blocked,true);assert.equal(report.release_grace_recovered,true);
  assert.equal(report.finger_drawing,true);assert.equal(report.coalesced_samples,true);
  assert.equal(report.palm_motion_ignored,true);assert.equal(report.cancellation,true);assert.equal(report.capture_loss,true);
  assert.deepEqual(report.pen_pressure,[.2,.4,.8]);
  assert.equal(corrected.snapshot(),original,'Positive result must restore original guard/hover/contact/native state');
  const early=scene(),before=early.snapshot();early.run(bundle.begin);
  const failure=JSON.parse(early.run(bundle.complete));
  assert.match(failure.error,/requires actual pen-release grace to expire/);
  assert.ok(failure.stack);assert.equal(early.snapshot(),before,'Failed second phase must restore all state');
  assert.equal(early.run(bundle.cleanup),true,'Cleanup is idempotent');
  const broken=scene(),beforeBroken=broken.snapshot();broken.run(bundle.begin);
  broken.context.draw=()=>{throw Error('Synthetic restore failure')};
  const primary=JSON.parse(broken.run(bundle.complete));
  assert.match(primary.error,/requires actual pen-release grace to expire/);
  assert.match(primary.cleanup_error,/Synthetic restore failure/);assert.ok(primary.stack);
  assert.equal(broken.snapshot(),beforeBroken,'Cleanup failure still restores scalar state and retires fixture');
  const occupied=scene();
  occupied.context.window.notebookPointerProbe={identity:'another-fixture',restore(){throw Error('Not owned')}};
  const existing=occupied.context.window.notebookPointerProbe,occupiedBefore=occupied.snapshot();
  const rejected=JSON.parse(occupied.run(bundle.begin));
  assert.match(rejected.error,/already active/);assert.equal(rejected.fixture_owned,false);
  assert.equal(occupied.context.window.notebookPointerProbe,existing);
  assert.equal(occupied.snapshot(),occupiedBefore,'An existing fixture must not be overwritten or restored');
  return {passed:true,compiled_fixture_negative_control:!!bundle.legacy,release_grace_ms:grace,blocked_until_boundary:true,recovers_after_boundary:true,
    original_state_restored:true,error_message_preserved:true,early_phase_rejected:true,
    javascript_cleanup_preserves_primary:true,existing_fixture_preserved:true,
    pressure_pan_cancel_capture_assertions_retained:true,scope:'Pure V8 fixture/source proof; no native engine or hardware run'}
}
module.exports={checkNativePointerContract};
if(require.main===module){
  const fs=require('node:fs');
  const bundle=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
  console.log(JSON.stringify(checkNativePointerContract(bundle)))
}
