const fs = require('fs'), vm = require('vm'), assert = require('assert');
const path=process.argv[2] || require('path').join(__dirname,'../../features/notebooks/assets/input.js'), source=fs.readFileSync(path,'utf8');
new vm.Script(source); // Parse the full actual candidate asset.
let start=source.indexOf('let nativePenContact =');
let end=source.indexOf('let eraserKind =',start);
let code=source.slice(0,source.indexOf('// Bounded content-free input diagnostics'))+source.slice(source.indexOf('function coord('),source.indexOf('function distance('))+source.slice(start,end);
let events=[];
const context={window:{},state:{native_pen:true,width:100,height:100},innerWidth:200,innerHeight:100,active:null,
 document:{elementFromPoint:()=>context.canvas},
 canvas:{getBoundingClientRect:()=>({left:0,top:0,width:200,height:100}),onpointerdown:e=>{context.active=e.pointerId;events.push(['down',e.pointerId,e.pressure])},
 onpointermove:e=>events.push(['move',e.pointerId,e.getCoalescedEvents().length])},
 finish:(e,cancel=false)=>{if(context.active===e.pointerId){events.push([cancel?'cancel':'up',e.pointerId]);context.active=null}}};
vm.createContext(context);vm.runInContext(code,context);
for(let id=1;id<=20;id++){
 context.window.logisticsNativePen('down',id,[[10,10,.5]],200,100);
 context.window.logisticsNativePen('up',id,[[10,10,.5]],200,100)
}
assert.equal(events.length,40);assert.equal(events.filter(e=>e[0]==='down').length,20);
assert.equal(context.active,null);
context.window.logisticsNativePen('down',21,[[10,10,.5]],200,100);
context.window.logisticsNativePenReset();assert.equal(events.at(-1)[0],'cancel');assert.equal(context.active,null);
context.active=17;context.window.logisticsNativePenReset();assert.equal(context.active,17,'Retirement must not cancel ordinary mouse/finger contact');
console.log(JSON.stringify({passed:true,rapid_contacts:20,paired_packets:40,native_retire_cancel:true,ordinary_contact_preserved:true,scope:'actual JS transport glue with synthetic canvas handlers; not native/UI/digitizer acceptance'}));

assert.equal(vm.runInContext("coord({pointerType:'pen',clientX:10,clientY:10,pressure:.2})[2]",context),.2);
vm.runInContext('constantPenPressure=true',context);
for(const pressure of [0,1])assert.equal(vm.runInContext(`coord({pointerType:'pen',clientX:10,clientY:10,pressure:${pressure}})[2]`,context),.5);
vm.runInContext('constantPenPressure=false;active=null;busy=false',context);
const mobile=fs.readFileSync(path.replace('input.js','mobile.js'),'utf8');new vm.Script(mobile);
context.vp={append(){}};
context.document.createElement=()=>({append(){}});
context.document.createTextNode=s=>s;
vm.runInContext(mobile.slice(mobile.indexOf("  const constantPressure ="),mobile.indexOf('  let grayLabel =')),context);
vm.runInContext('constantPressure.checked=true;constantPressure.onchange()',context);
assert.equal(vm.runInContext('constantPenPressure',context),true);
vm.runInContext('active=7;constantPressure.checked=false;constantPressure.onchange()',context);
assert.equal(vm.runInContext('constantPressure.checked',context),true);
assert.equal(context.active,7,'Changing pressure must not cancel an active contact');
vm.runInContext('active=null;busy=true;constantPressure.checked=false;constantPressure.onchange()',context);
assert.equal(vm.runInContext('constantPressure.checked',context),true);
vm.runInContext('busy=false;constantPressure.checked=false;constantPressure.onchange()',context);
assert.equal(vm.runInContext('constantPenPressure',context),false);
console.log(JSON.stringify({constant_pressure_choice:true,default_event_force_preserved:true,no_midstroke_or_busy_change:true}));

const queueSource=fs.readFileSync(path.replace('input.js','queue.js'),'utf8');
context.queue=[{op:'save'},{op:'stroke',points:[[1,1,.5]]}];context.busy=true;context.continuousInk=false;context.active=null;
context.$=()=>({textContent:''});context.render=()=>{};context.pump=()=>{};
context.wholeErasePreview=new Set(['previewed-stroke']);
vm.runInContext(queueSource.slice(queueSource.indexOf('window.notebookUpdate ='),queueSource.indexOf('// Mobile acknowledges')),context);
context.window.notebookUpdate({native_pen:true},'');
assert.equal(context.queue.length,1);assert.equal(context.queue[0].op,'stroke','Retry ack lost queued pen input');
assert.equal(context.wholeErasePreview.size,0,'Acknowledgement must clear the live eraser preview');
console.log(JSON.stringify({retry_nonerror_ack_preserves_queued_stroke:true}));

// Execute the production command pump too. Only the generated host-transport
// placeholder is replaced by a receiver that records the real encoded action.
const pumpCode=queueSource.slice(queueSource.indexOf('function pump()'),queueSource.indexOf('window.notebookUpdate ='))
 .replace('__MAX_COMMAND__','8388608').replace('__SEND_COMMAND__','__recordCommand(command)');
context.bridge='logistics-notebook://fixture/';context.seq=0;
let dispatched=[];context.__recordCommand=command=>dispatched.push(JSON.parse(decodeURIComponent(command.split('?command=')[1])).action);
vm.runInContext(pumpCode,context);
const status={textContent:''};context.$=()=>status;context.document.getElementById=()=>status;
const failedSaveQueue=()=>{context.queue=[{op:'save'},{op:'stroke',points:[[1,1,.5]]}];context.busy=true;context.active=null;context.continuousInk=false;dispatched=[]};
failedSaveQueue();context.window.notebookUpdate({native_pen:true},'Provider rejected Save');
assert.equal(context.queue.length,0,'Negative control must reproduce the old destructive error ACK');
assert.equal(dispatched.length,0);
failedSaveQueue();
vm.runInContext("window.notebookUpdate({native_pen:true},'');document.getElementById('status').textContent='Provider rejected Save; your draft remains open.'",context);
assert.equal(context.queue.length,1);assert.equal(context.queue[0].op,'stroke');
assert.equal(dispatched.length,1);assert.equal(dispatched[0].op,'stroke');
assert.deepEqual(dispatched[0].points,[[1,1,.5]]);
assert.equal(context.busy,true,'Preserved stroke must actually dispatch and await its own acknowledgement');
assert.match(status.textContent,/Provider rejected Save/);
console.log(JSON.stringify({failed_save_old_error_ack_destructive_negative_control:true,failed_save_nonerror_ack_dispatches_preserved_stroke:true,truthful_failure_status:true}));
