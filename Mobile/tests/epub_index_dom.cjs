// Synthetic offline chapter; count DOM walks and verify UTF-16 passage anchors.
const fs = require('fs'), assert = require('assert/strict');
const {chromium} = require('playwright');
(async () => {
 const fixture=JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
 const browser=await chromium.launch({headless:true, ...(process.env.LOGISTICS_CHROME ? {executablePath:process.env.LOGISTICS_CHROME} : {})});
 try {
  const page=await browser.newPage();
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
  const result=await page.evaluate(()=>{
   const expected=document.querySelector('p').textContent;
   for(let i=0;i<100;i++) {reader.seek(0,expected.length);if(getSelection().toString()!==expected)throw Error('UTF-16 selection mismatch');reader.speechSource();}
   const count=walks;reader.dispose();return {count,empty:!document.querySelector('body>div')};
  });
  assert.equal(result.count,1);assert(result.empty);
  console.log(JSON.stringify(result));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
