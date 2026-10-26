"""Shared offline brush rendering; v6 point widths are already resolved."""

SCRIPT = r'''
const palette=state.palette,brushes=state.brushes;
const aliases={0:12,1:14,2:15,3:16,4:17,5:18,7:13};
const draft=$('draft'),draftCtx=draft.getContext('2d');
const mask=document.createElement('canvas'),maskCtx=mask.getContext('2d');
let draftCount=0;
let inkSettings=null;
function brushFor(tool){return brushes[aliases[tool]??tool]||brushes[17]}
function brushOptions(){
let brush=brushFor(Number($('tool').value));
options('color',brush.colors.map(id=>Object.entries(state.colors).find(([name,value])=>value===id)));
if(!$('width').options.length){options('width',Object.entries(state.widths));$('width').value='2'}
}
function chosenInk(){return {tool:Number($('tool').value),color:Number($('color').value),width:Number($('width').value),layer:$('layer').value}}
function nativeColor(tool,color){
if(tool===18)return {color:9,color_rgba:state.highlights[color]};
if(tool===23)return {color:9,color_rgba:state.shaders[color]};
return {color,color_rgba:null};
}
function strokePoint(samples,i,tool,width){
let brush=brushFor(tool),base=brush.widths[width-1],[x,y,p]=samples[i];
let w=base*(1-brush.pressure+brush.pressure*Math.pow(p,brush.exponent));
if(brush.directional){let before=samples[i?i-1:Math.min(1,samples.length-1)],angle=Math.atan2(y-before[1],x-before[0]);w*=.25+.75*Math.abs(Math.sin(angle-Math.PI/4))}
return [x,y,p,Math.max(.25,Math.round(w*4)/4)];
}
function strokePoints(samples,tool,width){return samples.map((p,i)=>strokePoint(samples,i,tool,width))}
function inkColor(s){
let rgba=s.color_rgba,hex=palette[s.color]||'#000000',rgb=rgba?rgba.slice(0,3):[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));
if($('grayscale').checked){let gray=Math.round(.2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]);rgb=[gray,gray,gray]}
return {rgb,alpha:rgba?rgba[3]/255:1};
}
function colorCss(rgb){return 'rgb('+rgb.join(',')+')'}
function swatchColor(tool,color){let {rgb,alpha}=inkColor(nativeColor(tool,color));return rgb.map(v=>Math.round(v*alpha+255*(1-alpha)))}
const grainCache=new Map();
function grain(target,rgb,mechanical){
let key=rgb.join(',')+mechanical;if(grainCache.has(key))return grainCache.get(key);
let tile=document.createElement('canvas');tile.width=tile.height=8;let g=tile.getContext('2d');
g.fillStyle=colorCss(rgb);g.globalAlpha=mechanical?.75:.6;g.fillRect(0,0,8,8);
for(let y=0;y<8;y++)for(let x=0;x<8;x++){g.globalAlpha=((x*13+y*7)%11)/14;g.fillRect(x,y,1,1)}
let pattern=target.createPattern(tile,'repeat');grainCache.set(key,pattern);return pattern;
}
function ribbon(target,p){
target.beginPath();
for(let i=0;i<p.length;i++){
let b=p[i],r=b[3]/2;target.moveTo(b[0]+r,b[1]);target.arc(b[0],b[1],r,0,Math.PI*2);
if(!i)continue;let a=p[i-1],dx=b[0]-a[0],dy=b[1]-a[1],length=Math.hypot(dx,dy);if(!length)continue;
let nx=-dy/length,ny=dx/length,ar=a[3]/2;
// Consistent winding makes the overlapping segment outlines one filled mask.
target.moveTo(a[0]+nx*ar,a[1]+ny*ar);target.lineTo(a[0]-nx*ar,a[1]-ny*ar);
target.lineTo(b[0]-nx*r,b[1]-ny*r);target.lineTo(b[0]+nx*r,b[1]+ny*r);target.closePath();
}
target.fill();
}
function geometry(target,p,family){
if(['fineliner','mechanical','highlighter'].includes(family)&&p.length>1&&p[0][3]>0&&p.every(v=>v[3]===p[0][3])){
target.lineWidth=p[0][3];target.beginPath();target.moveTo(p[0][0],p[0][1]);for(let i=1;i<p.length;i++)target.lineTo(p[i][0],p[i][1]);target.stroke();
}else ribbon(target,p);
}
function line(s,target=ctx){
let p=s.points;if(!p.length)return;let brush=brushFor(s.tool),family=brush.family,{rgb,alpha}=inkColor(s);
target.save();target.fillStyle=target.strokeStyle=colorCss(rgb);target.lineCap='round';target.lineJoin='round';target.globalAlpha=alpha;
if(brush.texture)target.fillStyle=target.strokeStyle=grain(target,rgb,family==='mechanical');
if(family==='highlighter'){target.globalCompositeOperation='darken';target.lineCap='butt'}
if(family==='shader'){target.globalCompositeOperation='multiply';if(!s.color_rgba)target.globalAlpha=.25}
if(family==='paintbrush'){target.filter='blur(.4px)';target.globalAlpha*=.85}
if(family==='marker')target.globalAlpha*=.9;
geometry(target,p,family);
if(selected.has(s.id)){target.globalAlpha=1;target.globalCompositeOperation='source-over';target.filter='none';target.strokeStyle='#2877cb';target.lineWidth=2;
let bounds=p.reduce((b,p)=>[Math.min(b[0],p[0]-p[3]/2),Math.min(b[1],p[1]-p[3]/2),Math.max(b[2],p[0]+p[3]/2),Math.max(b[3],p[1]+p[3]/2)],[Infinity,Infinity,-Infinity,-Infinity]);target.strokeRect(bounds[0]-5,bounds[1]-5,bounds[2]-bounds[0]+10,bounds[3]-bounds[1]+10)}
target.restore();
}
function clearDraft(){draftCtx.clearRect(0,0,state.width,state.height);maskCtx.clearRect(0,0,state.width,state.height);draftCount=0}
function sizeDraft(){
draft.width=mask.width=canvas.width;draft.height=mask.height=canvas.height;
draft.style.width=canvas.style.width;draft.style.height=canvas.style.height;
for(let target of [draftCtx,maskCtx])target.setTransform(canvas.width/state.width,0,0,canvas.height/state.height,0,0);
draftCount=0;
}
function preview(samples){
let settings=inkSettings||chosenInk(),{tool,color,width}=settings,brush=brushFor(tool);
if(['fineliner','ballpoint'].includes(brush.family)){
line({tool,...nativeColor(tool,color),points:strokePoints(samples,tool,width)},ctx);return;
}
// Accumulate opaque geometry in a mask. Recolor only the new segment's bounds,
// applying texture and alpha once. Work per move is independent of stroke length.
if(draftCount>points.length||(draftCount===1&&points.length>1))clearDraft();
let pending=[];for(let i=Math.max(0,draftCount-1);i<points.length;i++)pending.push(strokePoint(points,i,tool,width));
if(!pending.length)return;
let family=brush.family,{rgb,alpha}=inkColor(nativeColor(tool,color));
draft.style.mixBlendMode=family==='highlighter'?'darken':family==='shader'?'multiply':'normal';
maskCtx.save();maskCtx.fillStyle=maskCtx.strokeStyle='white';maskCtx.lineCap=family==='highlighter'?'butt':'round';maskCtx.lineJoin='round';
if(family==='paintbrush')maskCtx.filter='blur(.4px)';
geometry(maskCtx,pending,family);
if(family==='highlighter'&&draftCount>=2){let p=pending[0];maskCtx.beginPath();maskCtx.arc(p[0],p[1],p[3]/2,0,Math.PI*2);maskCtx.fill()}
maskCtx.restore();draftCount=points.length;
let bounds=pending.reduce((b,p)=>[Math.min(b[0],p[0]-p[3]/2-4),Math.min(b[1],p[1]-p[3]/2-4),Math.max(b[2],p[0]+p[3]/2+4),Math.max(b[3],p[1]+p[3]/2+4)],[Infinity,Infinity,-Infinity,-Infinity]);
let sx=canvas.width/state.width,sy=canvas.height/state.height;
let left=Math.max(0,Math.floor(bounds[0]*sx)),top=Math.max(0,Math.floor(bounds[1]*sy)),right=Math.min(canvas.width,Math.ceil(bounds[2]*sx)),bottom=Math.min(canvas.height,Math.ceil(bounds[3]*sy));
if(right<=left||bottom<=top)return;
draftCtx.save();draftCtx.setTransform(1,0,0,1,0,0);draftCtx.beginPath();draftCtx.rect(left,top,right-left,bottom-top);draftCtx.clip();draftCtx.clearRect(left,top,right-left,bottom-top);draftCtx.drawImage(mask,left,top,right-left,bottom-top,left,top,right-left,bottom-top);
draftCtx.setTransform(sx,0,0,sy,0,0);draftCtx.globalCompositeOperation='source-in';draftCtx.globalAlpha=alpha*(family==='marker'?.9:family==='paintbrush'?.85:1);
draftCtx.fillStyle=brush.texture?grain(draftCtx,rgb,family==='mechanical'):colorCss(rgb);draftCtx.fillRect(left/sx,top/sy,(right-left)/sx,(bottom-top)/sy);draftCtx.restore();
}
'''
