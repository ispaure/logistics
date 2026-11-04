// Indexed production containment against an exhaustive geometric oracle.
const vm = require('node:vm');
const assert = require('node:assert/strict');
function checkSelectionIndex(source) {
  const distance=(p,a,b)=>{const dx=b[0]-a[0],dy=b[1]-a[1],v=dx*dx+dy*dy;
    const t=v?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/v)):0;
    return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)};
  function inside(p,path) {
    let result=false;
    for(let i=0,j=path.length-1;i<path.length;j=i++) {
      const a=path[i],b=path[j];
      if(distance(p,a,b)<1e-8)return true;
      if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])result=!result
    }
    return result
  }
  const side=(p,q,r)=>(q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0]);
  const cross=(a,b,c,d)=>side(a,b,c)*side(a,b,d)<0&&side(c,d,a)*side(c,d,b)<0;
  function brute(stroke,path) {
    if(path.length<3||!stroke.points.length)return false;
    const box=path.reduce((b,p)=>[Math.min(b[0],p[0]),Math.min(b[1],p[1]),Math.max(b[2],p[0]),Math.max(b[3],p[1])],[Infinity,Infinity,-Infinity,-Infinity]);
    if(stroke.points.some(p=>p[0]-p[3]/2<box[0]||p[1]-p[3]/2<box[1]||p[0]+p[3]/2>box[2]||p[1]+p[3]/2>box[3]))return false;
    for(let i=0;i<stroke.points.length;i++) {
      const b=stroke.points[i],a=stroke.points[Math.max(0,i-1)],radius=Math.max(a[3]||0,b[3]||0)/2;
      if(!inside(b,path))return false;
      for(let j=0;j<path.length;j++) {
        const c=path[j],d=path[(j+1)%path.length];
        if(cross(a,b,c,d)||Math.min(distance(a,c,d),distance(b,c,d),distance(c,a,b),distance(d,a,b))<radius-1e-8)return false
      }
    }
    return true
  }
  const sandbox={distance,Math,Map};vm.createContext(sandbox);
  vm.runInContext(source.slice(source.indexOf('function selectionPrepare('),source.indexOf('function selectionBounds(')),sandbox);
  let seed=0x79a10b3;
  const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296};
  let comparisons=0;
  for(let fixture=0;fixture<250;fixture++) {
    const count=3+Math.floor(random()*30),path=Array.from({length:count},(_,i)=>{
      const angle=i/count*Math.PI*2,radius=60+random()*100;
      return [200+Math.cos(angle)*radius,200+Math.sin(angle)*radius]
    });
    if(fixture%3===0)path.reverse();
    if(fixture%5===0)[path[1],path[2]]=[path[2],path[1]]; // Include self-intersections.
    const prepared=sandbox.selectionPrepare(path);
    for(let sample=0;sample<16;sample++) {
      const extent=sample%2?30:180;
      const stroke={points:Array.from({length:1+Math.floor(random()*6)},()=>[200+(random()-.5)*extent*2,200+(random()-.5)*extent*2,.5,random()*12])};
      assert.equal(sandbox.selectionContains(stroke,prepared),brute(stroke,path),`Fixture ${fixture}/${sample}`);
      comparisons++;
    }
    for(const point of path)for(const epsilon of [0,1e-9,-1e-9]) {
      const p=[point[0]+epsilon,point[1]+epsilon];
      assert.equal(sandbox.selectionInside(p,prepared),inside(p,path),'Boundary tolerance must match exhaustive parity');
      comparisons++
    }
  }
  const square=[[0,0],[100,0],[100,100],[0,100]];
  const edgeCases=[
    {points:[[1,20,.5,2],[1,80,.5,2]]},
    {points:[[1,20,.5,2.0000001],[1,80,.5,2.0000001]]},
    {points:[[50,50,.2,2],[50,50,.8,8]]},
    {points:[[0,20,.5,0],[0,80,.5,0]]},
    {points:[[1e-9,20,.5,0],[1e-9,80,.5,0]]},
    {points:[[10,10,.5,2],[90,90,.5,2]]}
  ];
  for(const stroke of edgeCases) {
    assert.equal(sandbox.selectionContains(stroke,square),brute(stroke,square),'Boundary, coincident or edge-aligned segment changed');
    comparisons++
  }
  for(const path of [[],[[0,0]],[[0,0],[100,100]],[[0,0],[50,0],[100,0]]]) {
    assert.equal(sandbox.selectionContains({points:[[50,50,.5,2]]},path),brute({points:[[50,50,.5,2]]},path),'Degenerate path changed');
    comparisons++
  }
  const path=Array.from({length:2048},(_,i)=>[700+600*Math.cos(i/2048*Math.PI*2),900+600*Math.sin(i/2048*Math.PI*2)]);
  const prepared=sandbox.selectionPrepare(path);
  const dense={points:Array.from({length:100000},(_,i)=>[710+Math.sin(i*.02),910+Math.cos(i*.02),.5,1])};
  for(let i=0;i<10;i++)assert.equal(sandbox.selectionContains(dense,prepared),true);
  assert.ok(prepared.work<1_001_000,`Dense interior work exceeded linear certificate bound: ${prepared.work}`);
  assert.ok(prepared.edgeTests<100,'Dense interior points must not rescan polygon edges');
  assert.equal(prepared.exhausted,false);
  const limited=sandbox.selectionPrepare(path);limited.limit=10;
  assert.equal(sandbox.selectionContains(dense,limited),false);
  assert.equal(limited.exhausted,true,'Pathological work stops explicitly rather than accepting an unchecked result');
  return {passed:true,oracle_comparisons:comparisons,lasso_edges:path.length,dense_page_points:1000000,
    counted_work:prepared.work,exact_edge_tests:prepared.edgeTests,work_limit_abort:true,
    scope:'Deterministic operation counts, not wall-clock or device latency'}
}
module.exports={checkSelectionIndex};
if(require.main===module) {
  const fs=require('node:fs'),path=require('node:path');
  console.log(JSON.stringify(checkSelectionIndex(fs.readFileSync(path.resolve(__dirname,'../../features/notebooks/assets/selection.js'),'utf8'))))
}
