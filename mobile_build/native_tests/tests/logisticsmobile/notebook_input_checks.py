"""Browser-level gestures and native-batch contract, shared by native/Qt probes."""

INPUT_CHECKS = r'''(()=>{
const saved={send,state,active,points,pan,mode,inkSettings,selected,pendingInk,pendingErase,
    busy,eraserKind,erasePreviewCount,
    finger:$('finger').checked,tool:$('tool').value,capture:canvas.setPointerCapture,
    x:$('viewport').scrollLeft,y:$('viewport').scrollTop};
let actions=[],paints=0;
const original=preview, originalErase=previewErase, originalClear=ctx.clearRect;
const require=(value,message)=>{if(!value)throw Error(message)};
try{
    state={...state,index:1,count:3,native_pen:true,warning:'',read_only:false};
    send=a=>actions.push(a);active=null;points=[];pan=null;mode='ink';selected=new Set();pendingInk=null;
    canvas.setPointerCapture=()=>{};$('finger').checked=false;
    const r=canvas.getBoundingClientRect(),x=r.left+30,y=r.top+120;
    const event=(id,px,py)=>({pointerId:id,pointerType:'touch',clientX:px,clientY:py,preventDefault(){}});
    canvas.onpointerdown(event(1,x+100,y));canvas.onpointermove(event(1,x,y+3));canvas.onpointerup(event(1,x,y+3));
    require(actions.length===1&&actions[0].op==='page'&&actions[0].index===2,'Left swipe did not advance');
    canvas.onpointerdown(event(2,x,y));canvas.onpointermove(event(2,x+100,y));canvas.onpointerup(event(2,x+100,y));
    require(actions.length===2&&actions[1].index===0,'Right swipe did not go back');
    state.index=0;
    canvas.onpointerdown(event(3,x,y));canvas.onpointerup(event(3,x+100,y));
    canvas.onpointerdown(event(4,x,y));canvas.onpointermove(event(4,x+4,y+100));canvas.onpointerup(event(4,x+4,y+100));
    canvas.onpointerdown(event(5,x+100,y));canvas.onpointercancel(event(5,x,y));
    canvas.onpointerdown(event(6,x+100,y));canvas.onpointerdown(event(7,x+90,y));canvas.onpointerup(event(6,x,y));
    require(actions.length===2,'Boundary, vertical, cancelled or multi-touch gesture changed pages');
    $('tool').value='12';$('tool').onchange();
    preview=function(...args){paints++;return original(...args)};
    window.logisticsNativePen('down',9,[[x,y,.2]],innerWidth,innerHeight);
    const before=paints;
    window.logisticsNativePen('move',9,[[x+10,y+5,.4],[x+20,y+10,.8],[x+30,y+15,.9]],innerWidth,innerHeight);
    require(paints===before+1,'Native batch must paint immediately and only once '+JSON.stringify({paints,before,active,mode,pan,target:document.elementFromPoint(x,y)?.id,points:points.length,frameBatchedInk}));
    window.logisticsNativePen('up',9,[[x+30,y+15,0]],innerWidth,innerHeight);
    require(actions.length===3&&actions[2].op==='stroke'&&actions[2].points.length===4,'Native samples were lost or duplicated');
    const pressures=actions[2].points.map(p=>p[2]);
    require(JSON.stringify(pressures)==='[0.2,0.4,0.8,0.9]','Native pressure not retained');
    const widths=strokePoints(actions[2].points,12,2).map(p=>p[3]);
    require(widths[0]<widths[3],'Paintbrush pressure does not change width');
    window.logisticsNativePen('down',10,[[x,y,.5]],innerWidth,innerHeight);
    window.logisticsNativePen('cancel',10,[[x+5,y+5,0]],innerWidth,innerHeight);
    require(active===null&&points.length===0&&actions.length===3,'Native cancellation saved a stroke');
    mode='erase';eraserKind='partial';pendingErase=null;
    let clears=0,maxBatch=0;
    ctx.clearRect=function(...args){clears++;return originalClear.apply(this,args)};
    previewErase=function(samples,...args){maxBatch=Math.max(maxBatch,samples.length);return originalErase(samples,...args)};
    send=a=>{actions.push(a);busy=true};
    window.logisticsNativePen('down',11,[[x,y,.5]],innerWidth,innerHeight);
    const initialClears=clears;
    for(let batch=0;batch<10;batch++)window.logisticsNativePen('move',11,
        Array.from({length:8},(_,i)=>[x+(batch*8+i+1)/2,y+batch,.5]),innerWidth,innerHeight);
    require(clears===initialClears&&maxBatch<=9,'Partial eraser replayed the page or entire gesture during movement');
    window.logisticsNativePen('up',11,[[x+40,y+9,0]],innerWidth,innerHeight);
    require(clears===initialClears&&pendingErase&&actions[3].op==='erase','Pen-up restored ink before erase acknowledgement');
    pendingErase=null;busy=false;
    window.logisticsNativePen('down',12,[[x,y,.5]],innerWidth,innerHeight);
    window.logisticsNativePen('cancel',12,[[x+5,y,0]],innerWidth,innerHeight);
    require(active===null&&!pendingErase&&actions.length===4,'Cancelled erase saved or left a mask');
    return JSON.stringify({left_right_swipes:true,gesture_guards:true,native_samples:4,pressures,widths,immediate_batch_paint:true,incremental_eraser:true,eraser_max_batch:maxBatch,erase_preview_survives_pen_up:true});
}finally{
    preview=original;previewErase=originalErase;ctx.clearRect=originalClear;
    send=saved.send;state=saved.state;active=saved.active;points=saved.points;pan=saved.pan;
    busy=saved.busy;pendingErase=saved.pendingErase;eraserKind=saved.eraserKind;erasePreviewCount=saved.erasePreviewCount;
    mode=saved.mode;inkSettings=saved.inkSettings;selected=saved.selected;pendingInk=saved.pendingInk;
    $('finger').checked=saved.finger;$('tool').value=saved.tool;canvas.setPointerCapture=saved.capture;
    draw();$('viewport').scrollLeft=saved.x;$('viewport').scrollTop=saved.y;
}
})()'''
