// Pure V8 checks of production link handlers; no native/browser acceptance.
const vm = require('node:vm');
function checkLinkGestures(source) {
  const results=[];
  for(const mobile of [false,true]) for(const platform of ['MacIntel','Win32','Linux x86_64']) {
    let now=1000, timer=null, fallback=0;
    const commands=[], listeners={};
    const viewport={scrollLeft:0,scrollTop:0,append(){}};
    const context={console,Math,document:{body:{classList:{contains:()=>mobile},append(){}},
      createElement:()=>({style:{},setAttribute(){},append(){},getContext:()=>({drawImage(){}})}),addEventListener:(name,callback)=>listeners[name]=callback},
      mobileViewport:()=>mobile,navigator:{platform},performance:{now:()=>now},
      setTimeout(callback,ms){timer={callback,ms};return timer},clearTimeout(){timer=null},
      canvas:{width:100,height:100,onpointerdown(){fallback++},onpointermove(){},onpointerup(){},onpointercancel(){},
        setPointerCapture(){},getBoundingClientRect:()=>({width:100,height:100,left:0,top:0})},
      backgroundContentBounds:()=>({x:0,y:0,width:context.state.width,height:context.state.height}),
      state:{index:0,count:4,width:100,height:100,links:[{rect:[.1,.1,.5,.3],index:2}]},
      busy:false,active:null,pan:null,pageSwipe:true,queue:[],penTouchBlocked:()=>false,
      coord:e=>[e.clientX,e.clientY],$:()=>viewport,
      beginPan(e){context.pan={id:e.pointerId,x:e.clientX,y:e.clientY,paging:true}},
      send(action){commands.push(action);context.queue.push(action);context.busy=true},
      window:{notebookUpdate(next){context.state=next;context.queue.shift();context.busy=false}}
    };
    vm.createContext(context);vm.runInContext(source,context);
    const run=s=>vm.runInContext(s,context);
    const check=(value,label)=>{if(!value)throw Error(`${mobile}/${platform}: ${label}`);results.push(label)};
    const reset=()=>{context.state.index=0;context.queue=[];context.busy=false;context.active=null;context.pan=null;commands.length=0;now+=2000;run('linkGesture=null;clearPageFeedback();pendingPageFeedback=null')};
    const event=(kind='touch',x=30,y=20,keys={})=>({pointerType:kind,pointerId:1,button:0,clientX:x,clientY:y,preventDefault(){},...keys});
    const keys=mobile?{}:platform==='MacIntel'?{metaKey:true}:{ctrlKey:true};
    const kind=mobile?'touch':'mouse';
    const tap=()=>{const e=event(kind,30,20,keys);context.canvas.onpointerdown(e);context.canvas.onpointerup(e)};
    tap();check(commands.length===1&&commands[0].index===2,'Completed authorized tap follows');
    check(run('!linkFeedback.hidden'),'Pending link shows feedback');
    context.window.notebookUpdate({...context.state,index:2});
    check(run("linkFeedback.hidden&&linkReturn===0&&!undoPageJump.hidden&&pageFeedbackLabel.textContent==='Page 3 of 4'") &&
      timer?.ms===3000,'Acknowledged jump shows the current page and offers Go back for three seconds');
    run('undoPageJump.onclick()');check(commands.at(-1).index===0,'Go back returns');
    context.window.notebookUpdate({...context.state,index:2},'failed');
    check(run('linkReturn===0&&!undoPageJump.hidden'),'Failed return keeps Go back available');
    run('undoPageJump.onclick()');context.window.notebookUpdate({...context.state,index:0});
    check(run('linkReturn===null&&undoPageJump.hidden'),'Confirmed return retires Go back');
    reset();tap();context.window.notebookUpdate({...context.state,index:0},'failed');check(run('linkFeedback.hidden&&undoPageJump.hidden'),'Failure clears feedback and has no undo');
    reset();tap();context.window.notebookUpdate({...context.state,index:2});
    timer.callback();
    check(run('linkReturn===null&&undoPageJump.hidden&&pageFeedback.hidden'),'Expiry hides the page feedback and clears the return');
    reset();tap();context.window.notebookUpdate({...context.state,index:2});
    context.window.notebookUpdate({...context.state,index:1});
    check(run('linkReturn===null&&undoPageJump.hidden'),'Moving to another page clears the return');
    reset();let e=event(kind,30,20,keys);context.canvas.onpointerdown(e);context.canvas.onpointermove(event(kind,60,20,keys));context.canvas.onpointermove(e);context.canvas.onpointerup(e);
    check(commands.length===0,'Move out and back does not follow');
    reset();context.canvas.onpointerdown(e);now+=601;context.canvas.onpointerup(e);check(commands.length===0,'Hold does not follow');
    reset();context.canvas.onpointerdown(e);context.canvas.onpointercancel(e);context.canvas.onpointerup(e);check(commands.length===0,'Cancel does not follow');
    reset();context.canvas.onpointerdown(e);listeners.pointerdown({pointerId:2});context.canvas.onpointerup(e);check(commands.length===0,'Second pointer cancels link');
    reset();context.canvas.onpointerdown(e);context.pan=null;context.canvas.onpointerup(e);check(commands.length===0,'Pen proximity or blur cancelling pan rejects link');
    reset();const pen=event('pen');context.canvas.onpointerdown(pen);context.canvas.onpointerup(pen);check(commands.length===0,'Pen never follows');
    if(!mobile){reset();e=event('mouse');context.canvas.onpointerdown(e);context.canvas.onpointerup(e);check(commands.length===0&&fallback>0,'Plain editor click delegates to drawing')}
    if(mobile){reset();e=event('touch');context.canvas.onpointerdown(e);context.canvas.onpointermove(event('touch',-40));context.canvas.onpointerup(event('touch',-40));check(commands.length===1&&commands[0].index===1,'Swipe pages without following destination')}
  }
  return {checks:results.length,success:true}
}
module.exports={checkLinkGestures};
