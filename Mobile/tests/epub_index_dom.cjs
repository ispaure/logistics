// Synthetic offline chapter; count DOM walks and verify UTF-16 passage anchors.
const fs = require('fs'), assert = require('assert/strict');
const {chromium} = require('playwright');
(async () => {
 const fixture=JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
 const browser=await chromium.launch({headless:true, ...(process.env.LOGISTICS_CHROME ? {executablePath:process.env.LOGISTICS_CHROME} : {})});
 try {
  const page=await browser.newPage({viewport:{width:390,height:844}});
  await page.route('**/*', r=>r.abort());
  await page.setContent(fixture.html);
  await page.evaluate(()=>{window.walks=0;const create=document.createTreeWalker.bind(document);document.createTreeWalker=(...args)=>{walks++;return create(...args);};});
  await page.evaluate(fixture.script);
  await page.evaluate(()=>reader.seek(0));
  const motion=await page.evaluate(()=>{
   reader.turn(1);const position=reader.pagination();
   return {count:document.getAnimations().length,position,anchor:Number(new URL(window.syntheticNotification).searchParams.get('offset'))};
  });
  assert(motion.count>0);assert(motion.position.index===1);assert.equal(motion.anchor,motion.position.anchor);
  await page.evaluate(()=>reader.setMotion(false));
  assert.equal(await page.evaluate(()=>document.getAnimations().length),0);
  await page.evaluate(()=>reader.turn(-1));
  assert.equal(await page.evaluate(()=>document.getAnimations().length),0);
  await page.evaluate(()=>{reader.setMotion(true);reader.turn(1);});
  assert.equal(await page.evaluate(()=>document.getAnimations().length),1);
  await page.evaluate(()=>{const style=document.createElement('style');style.id='logistics-eink';document.head.appendChild(style);});
  await page.waitForTimeout(20);
  assert.equal(await page.evaluate(()=>document.getAnimations().length),0);
  await page.evaluate(()=>reader.turn(-1));
  assert.equal(await page.evaluate(()=>document.getAnimations().length),0);
  await page.evaluate(()=>document.getElementById('logistics-eink').remove());
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.evaluate(()=>reader.turn(1));
  assert.equal(await page.evaluate(()=>document.getAnimations().length),0);
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.evaluate(()=>{reader.turn(-1);reader.turn(1);});
  assert.equal(await page.evaluate(()=>document.getAnimations().length),1);
  await page.evaluate(()=>reader.seek(0));
  assert.equal(await page.evaluate(()=>document.getAnimations().length),0);
  // Tablets show equal columns; turns move one whole spread and seeks on
  // the right page remain on that spread. Reflow retains the logical anchor.
  await page.setViewportSize({width:1200,height:800});
  await page.waitForFunction(()=>reader.pagination().columns===2);
  await page.evaluate(()=>{reader.setMotion(false);reader.seek(0);});
  let spread=await page.evaluate(()=>reader.pagination());
  assert.equal(spread.columns,2);assert.equal(spread.index,0);
  assert(Math.abs(spread.left+spread.width+spread.gap/2-600)<1);
  const rightAnchor=await page.evaluate(()=>{
   const p=reader.pagination();
   for(const el of document.querySelectorAll('p')){
    const r=el.getBoundingClientRect();
    if(r.left>p.left+p.width && r.left<1200){
     const before=document.createRange();before.selectNodeContents(document.body);before.setEnd(el,0);
     return before.toString().length;
    }
   }
   throw Error('No right-page text');
  });
  await page.evaluate(offset=>reader.seek(offset),rightAnchor);
  assert.equal(await page.evaluate(()=>reader.pagination().index),0);
  await page.evaluate(()=>reader.turn(1));
  assert.equal(await page.evaluate(()=>reader.pagination().index),2);
  assert.equal(await page.evaluate(()=>document.getAnimations().length),0);
  const anchor=await page.evaluate(()=>reader.pagination().anchor);
  await page.setViewportSize({width:800,height:1200});
  await page.waitForFunction(()=>reader.pagination().columns===1);
  assert.equal(await page.evaluate(()=>reader.pagination().columns),1);
  assert.equal(await page.evaluate(()=>reader.pagination().anchor),anchor);
  await page.setViewportSize({width:1200,height:800});
  await page.waitForFunction(()=>reader.pagination().columns===2);
  // Off-center crease: equal text widths; surplus stays at the outer edge.
  await page.evaluate(()=>{reader.setGeometry({seam:.55,gap:.03});reader.seek(0);});
  spread=await page.evaluate(()=>reader.pagination());
  assert.equal(spread.columns,2);
  assert(Math.abs(spread.left+spread.width+spread.gap/2-660)<1);
  assert(spread.left>16);
  const rects=await page.evaluate(()=>{
   const p=reader.pagination(), boxes=[];
   for(const el of document.querySelectorAll('p')){
    const r=document.createRange();r.selectNodeContents(el);
    boxes.push(...[...r.getClientRects()].map(b=>({left:b.left,right:b.right})));
   }
   return boxes.filter(b=>b.left>=p.left-.5 && b.left<1200);
  });
  assert(rects.some(r=>r.left>678));
  assert(rects.every(r=>r.right<=642.5 || r.left>=677.5));
  await page.evaluate(()=>reader.seek(10000000));
  spread=await page.evaluate(()=>reader.pagination());
  assert.equal(spread.index,Math.floor((spread.count-1)/2)*2);
  await page.evaluate(()=>reader.turn(1));
  assert.equal(await page.evaluate(()=>new URL(window.syntheticNotification).pathname.endsWith('/next')),true);
  await page.evaluate(()=>{reader.setGeometry(null);reader.seek(0);});
  const result=await page.evaluate(()=>{
   const expected=document.querySelector('p').textContent;
   for(let i=0;i<100;i++) {reader.seek(0,expected.length);if(getSelection().toString()!==expected)throw Error('UTF-16 selection mismatch');reader.speechSource();}
   const count=walks;reader.dispose();return {count,empty:!document.querySelector('body>div')};
  });
  assert.equal(result.count,1);assert(result.empty);
  console.log(JSON.stringify(result));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
