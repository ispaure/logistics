// Synthetic offline chapter; count DOM walks and verify UTF-16 passage anchors.
const fs = require('fs'), assert = require('assert/strict');
const {chromium} = require('playwright');
(async () => {
 const fixture=JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
 const browser=await chromium.launch({headless:true, ...(process.env.LOGISTICS_CHROME ? {executablePath:process.env.LOGISTICS_CHROME} : {})});
 try {
  const page=await browser.newPage({viewport:{width:390,height:844}});
  let initialHTML=fixture.html,releaseImage;
  const pendingImage=new Promise(resolve=>{releaseImage=resolve;});
  const imageURL='https://logistics.invalid/delayed-cover.png';
  const raster=fixture.delayImage ? fixture.html.match(/data:image\/png;base64,([^"']+)/)[1] : null;
  if(raster)initialHTML=initialHTML.replace('data:image/png;base64,'+raster,imageURL)
    .replace('img-src data:','img-src data: https://logistics.invalid');
  await page.route('**/*', async r=>{
   if(raster && r.request().url()===imageURL){
    await pendingImage;await r.fulfill({contentType:'image/png',body:Buffer.from(raster,'base64')});
   }else await r.abort();
  });
  await page.setContent(initialHTML,{waitUntil:'domcontentloaded'});
  await page.evaluate(()=>{window.walks=0;const create=document.createTreeWalker.bind(document);document.createTreeWalker=(...args)=>{walks++;return create(...args);};});
  await page.evaluate(fixture.script);
  if(fixture.images){
   if(raster)assert.equal(await page.evaluate(()=>document.querySelector('img').complete),false,'Cover must still be loading at reader startup');
   releaseImage();
   await page.waitForFunction(()=>[...document.images].every(img=>img.complete && img.naturalWidth>0));
   for(const viewport of [{width:390,height:844},{width:844,height:390},{width:1200,height:800},
                          {width:800,height:1200}]){
    await page.setViewportSize(viewport);
    await page.waitForTimeout(60);
    const image=await page.evaluate(()=>{
     reader.setMotion(false);reader.seekPage(0);
     const position=reader.pagination(),left=document.querySelector('img').getBoundingClientRect().left;
     reader.seekPage(Math.floor((left-position.left+.5)/position.stride));
     const img=document.querySelector('img'),box=img.getBoundingClientRect();
     const view=document.body.firstElementChild.getBoundingClientRect();
     return {box:box.toJSON(),view:view.toJSON(),fragments:img.getClientRects().length,pages:reader.pagination().count,
       columns:reader.pagination().columns,columnWidth:reader.pagination().width,stride:reader.pagination().stride,
       style:img.style.cssText,width:innerWidth,height:innerHeight};
    });
    assert.equal(image.fragments,1,JSON.stringify(image));
    assert(image.box.top>=image.view.top-.5 && image.box.bottom<=image.view.bottom+.5,JSON.stringify(image));
    assert(image.box.left>=image.view.left-.5 && image.box.right<=image.view.right+.5,JSON.stringify(image));
    const columnLeft=image.view.left+Math.floor((image.box.left-image.view.left+.5)/image.stride)*image.stride;
    assert(image.box.right<=columnLeft+image.columnWidth+.5,'Image must not cross the gutter: '+JSON.stringify(image));
    assert(Math.abs(image.box.width/image.box.height-fixture.naturalWidth/fixture.naturalHeight)<.02,JSON.stringify(image));
    assert(image.box.width<=fixture.naturalWidth+.5 && image.box.height<=fixture.naturalHeight+.5,'Small images must not be enlarged');
    // Spread counts include the empty right column; there must be no extra spread.
    if(fixture.singleCover)assert.equal(image.pages,image.columns,'A single cover must fit the first spread: '+JSON.stringify(image));
    if(!fixture.singleCover){
     const after=await page.evaluate(()=>{
      const text=document.querySelector('#after').firstChild,range=document.createRange();
      range.selectNodeContents(document.body);range.setEnd(text,0);reader.seek(range.toString().length);
      const box=document.querySelector('#after').getBoundingClientRect(),view=document.body.firstElementChild.getBoundingClientRect();
      return box.left>=view.left-.5 && box.right<=view.right+.5 && box.top>=view.top-.5 && box.bottom<=view.bottom+.5;
     });
     assert(after,'Text after the image must remain reachable and visible');
    }
    await page.evaluate(html=>reader.measure(html,'cover'),fixture.html);
    await page.waitForFunction(()=>reader.measurement()?.done);
    const measured=await page.evaluate(()=>reader.measurement());
    assert(!measured.error,JSON.stringify(measured));
    assert.equal(measured.count,image.pages,'Hidden cover measurement must match the live cover');
   }
   process.stdout.write(JSON.stringify({images:true}));
   return;
  }
  const checkMeasurement=async()=>{
   const before=await page.evaluate(()=>reader.pagination());
   await page.evaluate(html=>reader.measure(html,'same-chapter'),fixture.html);
   await page.waitForFunction(()=>reader.measurement()?.done);
   const result=await page.evaluate(()=>reader.measurement());
   assert(!result.error,JSON.stringify(result));
   assert.equal(result.count,before.count,'Hidden columns must match the visible chapter exactly');
   assert.deepEqual(await page.evaluate(()=>reader.pagination()),before,'Counting moved the live passage');
  };
  await checkMeasurement();
  if(fixture.compactMargin){
   for(const viewport of [{width:390,height:844},{width:844,height:390},{width:1200,height:800},
                          {width:800,height:1200}]){
    await page.setViewportSize(viewport);
    await page.waitForTimeout(60);
    const box=await page.evaluate(()=>{
     reader.setMotion(false);reader.seek(0);
     const css=getComputedStyle(document.body),view=document.body.firstElementChild.getBoundingClientRect();
     return {top:view.top,bottom:view.bottom,height:innerHeight,heading:document.querySelector('h1').getBoundingClientRect().top,left:parseFloat(css.paddingLeft),
       right:parseFloat(css.paddingRight),font:parseFloat(css.fontSize),line:parseFloat(css.lineHeight)};
    });
    assert.equal(box.top,0,'The page must begin close to the native header');
    assert.equal(box.heading,0,'Pagination must not restore the chapter heading top margin');
    assert.equal(box.bottom,box.height,'The page must use the height above the native footer');
    assert.equal(box.left,fixture.compactMargin);assert.equal(box.right,fixture.compactMargin);
    assert.equal(box.font,24);assert.equal(box.line,36);
    await checkMeasurement();
    await page.evaluate(()=>reader.turn(1));
    assert(await page.evaluate(()=>reader.pagination().index>0),'The taller page must still turn');
   }
   process.stdout.write(JSON.stringify({compactMargins:true}));
   return;
  }
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
  await checkMeasurement();
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
  // A previous-chapter boundary supplies its exact text length, not an
  // oversized sentinel. End-of-text collapsed ranges can have an empty rect.
  await page.evaluate(()=>{
   const walk=document.createNodeIterator(document.body,NodeFilter.SHOW_TEXT);
   let node,length=0;while((node=walk.nextNode()))length+=node.length;
   reader.seek(0);reader.seek(length);
  });
  spread=await page.evaluate(()=>reader.pagination());
  assert.equal(spread.index,Math.floor((spread.count-1)/2)*2);
  await page.evaluate(()=>reader.turn(1));
  assert.equal(await page.evaluate(()=>new URL(window.syntheticNotification).pathname.endsWith('/next')),true);
  await page.evaluate(()=>{reader.setGeometry(null);reader.seek(0);});
  // Deep chapter seeks must measure against the new stride, never the outgoing
  // translation. Check actual glyph visibility; a retained numeric anchor alone
  // cannot detect landing several pages away from that anchor.
  const assertVisible=async offset=>{
   const visible=await page.evaluate(offset=>{
    const walk=document.createNodeIterator(document.body,NodeFilter.SHOW_TEXT);
    let node,total=0;
    while((node=walk.nextNode())){
     if(total+node.length>offset){
      const r=document.createRange();r.setStart(node,offset-total);r.setEnd(node,offset-total+1);
      const box=r.getBoundingClientRect(),p=reader.pagination();
      return {ok:box.left>=p.left-1 && box.right<=p.left+p.columns*p.width+(p.columns-1)*p.gap+1 && box.top>=0 && box.bottom<=innerHeight,
        box:box.toJSON(),pagination:p};
     }
     total+=node.length;
    }
    return false;
   },offset);
   assert(visible.ok,`Passage ${offset} is off screen after reflow: ${JSON.stringify(visible)}`);
  };
  await page.evaluate(()=>{reader.setMotion(false);reader.seek(25000);reader.turn(1);});
  const middle=await page.evaluate(()=>reader.pagination().anchor);
  await assertVisible(middle);
  for(const viewport of [{width:390,height:844},{width:844,height:390},{width:1200,height:800},
                         {width:800,height:1200},{width:390,height:844}]){
   await page.setViewportSize(viewport);
   await page.waitForTimeout(60);
   assert.equal(await page.evaluate(()=>reader.pagination().anchor),middle);
   await assertVisible(middle);
  }
  // A live (or paused) word highlight outranks a separately selected passage.
  await page.evaluate(()=>reader.highlight(27000,27007));
  // A repeated native load completion must retain the same live reader,
  // including speech/selection state, rather than seek the initial title page.
  await page.evaluate(()=>{window.retainedReader=reader;});
  await page.evaluate(fixture.script);
  assert.equal(await page.evaluate(()=>reader===window.retainedReader),true);
  assert.equal(await page.evaluate(()=>reader.pagination().anchor),27000);
  await assertVisible(27000);
  assert.equal(await page.evaluate(()=>CSS.highlights.get('logistics-speech').size),1);
  for(const viewport of [{width:1200,height:800},{width:844,height:390},{width:390,height:844}]){
   await page.evaluate(()=>{
    const node=document.querySelector('p').firstChild,r=document.createRange();
    r.setStart(node,0);r.setEnd(node,5);getSelection().addRange(r);
    document.dispatchEvent(new Event('selectionchange'));
   });
   await page.setViewportSize(viewport);
   await page.waitForTimeout(60);
   assert.equal(await page.evaluate(()=>reader.pagination().anchor),27000);
   await assertVisible(27000);
   assert.equal(await page.evaluate(()=>CSS.highlights.get('logistics-speech').size),1);
  }
  await page.evaluate(()=>reader.highlight(-1,-1));
  await page.evaluate(()=>{reader.seek(26000,26007);window.retainedReader=reader;});
  const selectedBeforeReload=await page.evaluate(()=>reader.speechSource().selection);
  await page.evaluate(fixture.script);
  assert.deepEqual(await page.evaluate(()=>reader.speechSource().selection),selectedBeforeReload);
  assert.equal(await page.evaluate(()=>reader.pagination().anchor),26000);
  // Older WebViews use a native selection as the speech highlight.
  await page.evaluate(()=>{
   Object.defineProperty(CSS,'highlights',{value:undefined,configurable:true});
   reader.highlight(28000,28007);
  });
  const spoken=await page.evaluate(()=>String(getSelection()));
  await page.setViewportSize({width:1200,height:800});
  await page.waitForTimeout(60);
  await assertVisible(28000);
  assert.equal(await page.evaluate(()=>String(getSelection())),spoken);
  await page.evaluate(()=>reader.highlight(-1,-1));
  const result=await page.evaluate(()=>{
   const expected=document.querySelector('p').textContent;
   for(let i=0;i<100;i++) {reader.seek(0,expected.length);if(getSelection().toString()!==expected)throw Error('UTF-16 selection mismatch');reader.speechSource();}
   const count=walks;reader.dispose();return {count,empty:!document.querySelector('body>div')};
  });
  assert.equal(result.count,1);assert(result.empty);
  // A slow chapter image may finish after the reader has moved or begun TTS.
  // Its load/error callback must restore the current word, not options.offset.
  await page.unroute('**/*');
  let finishImage;
  const requested=new Promise(resolve=>{
   page.route('**/late.png',route=>{finishImage=()=>route.abort();resolve();});
  });
  await page.setContent(fixture.html.replace('<body>','<body><img src="https://logistics.invalid/late.png">'),
                        {waitUntil:'domcontentloaded'});
  await requested;
  await page.evaluate(fixture.script);
  await page.evaluate(()=>{reader.seek(25000);reader.highlight(27000,27007);});
  await finishImage();
  await page.waitForTimeout(60);
  assert.equal(await page.evaluate(()=>reader.pagination().anchor),27000);
  await assertVisible(27000);
  console.log(JSON.stringify(result));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
