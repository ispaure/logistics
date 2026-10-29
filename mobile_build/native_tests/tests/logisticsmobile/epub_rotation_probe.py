"""Synthetic native reflow acceptance; no voice, user documents or credentials."""
import asyncio
import json
from pathlib import Path
import sys
import traceback
from uuid import uuid4

import toga
from toga.style import Pack
from features.books.mobile.presentation import chapter_view
from features.books.mobile.typography import css
from mobile.app import LogisticsMobile
from .rotation_checks import rotate

BUNDLE = 'io.github.ispaure.logisticsepubrotationqa'

# Inspect a real glyph, rather than merely checking an unchanged saved offset.
MEASURE = r'''JSON.stringify((()=>{
 const p=reader.pagination(),walk=document.createNodeIterator(document.body,NodeFilter.SHOW_TEXT);
 let node,total=0;
 while((node=walk.nextNode())){
  if(total+node.length>p.anchor){
   const r=document.createRange();r.setStart(node,p.anchor-total);r.setEnd(node,p.anchor-total+1);
   const b=r.getBoundingClientRect(),right=p.left+p.columns*p.width+(p.columns-1)*p.gap;
   return {anchor:p.anchor,index:p.index,columns:p.columns,count:p.count,
     width:innerWidth,height:innerHeight,box:b.toJSON(),pagination:p,
     visible:b.left>=p.left-1 && b.right<=right+1 && b.top>=0 && b.bottom<=innerHeight,
     highlight:window.CSS && CSS.highlights ? CSS.highlights.get('logistics-speech')?.size || 0 : String(getSelection()).length};
  }
  total+=node.length;
 }
 return {visible:false};
})())'''


class EpubRotationProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('rotation-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_started', False):
            self._started = True
            self.loop.create_task(self.check())

    async def check(self):
        result = dict(success=False, samples=[])
        try:
            async with asyncio.timeout(30):
                while getattr(self, '_startup_in_progress', False):
                    await asyncio.sleep(.1)
            content = ('<!doctype html><html><head><meta name="viewport" '
                       'content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">'
                       '<style>' + css(18, 16, 'light') + '</style></head><body>'
                       + '<p>First 😀 <strong>passage</strong> ends.</p>' * 2000 + '</body></html>')
            self.web = chapter_view(content, offset=25000, motion_enabled=False)
            box = toga.Box(children=[self.web], style=Pack(direction='column', flex=1))
            self.show_view(box, destination='documents', route='epub-rotation', title='EPUB rotation QA')
            async with asyncio.timeout(30):
                while not self.web._chapter_bridge.ready:
                    await asyncio.sleep(.1)
            await asyncio.sleep(1)
            poses = ['landscape-left', 'portrait', 'landscape-right', 'portrait']
            if sys.platform == 'ios':
                from rubicon.objc import ObjCClass
                if int(ObjCClass('UIDevice').currentDevice.userInterfaceIdiom) == 1:
                    poses.insert(2, 'portrait-upside-down')
            for speech in (False, True):
                await self.web.evaluate_javascript(
                    'reader.highlight(27000,27007)' if speech else 'reader.turn(1)')
                before = json.loads(await self.web.evaluate_javascript(MEASURE))
                assert before['visible'], before
                for pose in poses * 2:
                    await rotate(self, pose)
                    sample = json.loads(await self.web.evaluate_javascript(MEASURE))
                    sample.update(pose=pose, speech=speech)
                    result['samples'].append(sample)
                    assert sample['visible'] and sample['anchor'] == before['anchor'], sample
                    if speech:
                        assert sample['highlight'], sample
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'epub-rotation.json').write_text(json.dumps(result))
        print('EPUB_ROTATION=' + json.dumps(result), flush=True)


def main():
    EpubRotationProbe('EPUB rotation QA', BUNDLE).main_loop()
