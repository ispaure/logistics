"""Synthetic Android reader proof, including tablet rail/fullscreen transitions."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from logisticsmobile.app import LogisticsMobile
from logisticsmobile.comic_layout_check import fixture_reader


class ComicViewportProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('comic-viewport-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        report = {'success': False, 'samples': []}
        try:
            from java import jarray, jint, jclass
            await asyncio.sleep(1)
            output = Path(self.paths.cache) / 'comic-viewport-fixture'
            output.mkdir(exist_ok=True)
            owner = await fixture_reader(self, output)
            decor = self._impl.native.getWindow().getDecorView()
            for immersive in (True, False, True, False, True):
                owner.set_reading_mode(immersive)
                await asyncio.sleep(1)
                page = owner.book_content.children[0]
                canvas = getattr(page, 'canvas', page)._impl.native
                location = jarray(jint)(2)
                canvas.getLocationOnScreen(location)
                image = canvas.getDrawable()
                rect = jclass('android.graphics.RectF')(0, 0, image.getIntrinsicWidth(), image.getIntrinsicHeight())
                canvas.getImageMatrix().mapRect(rect)
                size = [int(canvas.getWidth()), int(canvas.getHeight())]
                window = [int(decor.getWidth()), int(decor.getHeight())]
                sample = dict(fullscreen=immersive, canvas=size, window=window,
                              origin=list(location), image_center=[float(rect.centerX()), float(rect.centerY())])
                report['samples'].append(sample)
                assert abs(rect.centerX() - size[0] / 2) < 2, sample
                assert abs(rect.centerY() - size[1] / 2) < 2, sample
                if immersive:
                    assert max(abs(size[i] - window[i]) for i in (0, 1)) <= 2, sample
                    assert max(abs(value) for value in location) <= 2, sample
                else:
                    assert size[1] < window[1] - 100, sample
            report['navigation_mode'] = self.native_host.adapter.mode
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'comic-viewport-result.json').write_text(json.dumps(report, indent=2))


def main():
    ComicViewportProbe('Logistics Mobile', 'io.github.ispaure.logisticsmobile').main_loop()
