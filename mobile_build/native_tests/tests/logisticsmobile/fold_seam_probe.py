"""Cache-only native seam geometry check; injected status is explicit in evidence."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4
from mobile.app import LogisticsMobile
from mobile.comic_layout_check import fixture_reader


class FoldSeamProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('fold-seam-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        from .fixtures import capture_window
        from mobile.fold_layout import seam_fraction
        report = {'success': False, 'samples': []}
        output = Path(self.paths.cache) / 'fold-seam-probe'
        output.mkdir(exist_ok=True)
        try:
            await asyncio.sleep(1)
            report['observed_hinge_status'] = getattr(self, '_hinge_status', None)
            report['interaction_installed'] = hasattr(self, '_hinge_interaction')
            window = self.main_window._impl.native
            report['interface_orientation'] = int(window.windowScene.interfaceOrientation)
            expected = float(window.bounds.size.width / 2)
            # Exercise the partial-state layout even when the simulator is flat.
            self._hinge_status = 2
            self.show_home()
            await asyncio.sleep(.5)
            self.resize_workspace()
            await asyncio.sleep(.5)
            hub = self.home_sections
            report['home'] = dict(seam=seam_fraction(self, hub), paired=hub.paired)
            first = hub.leading_scroll._impl.native
            rect = first.convertRect(first.bounds, toView=window)
            join = float(rect.origin.x + rect.size.width)
            report['samples'].append(dict(name='home-sections', join=join, expected=expected,
                left=float(rect.origin.x), width=float(rect.size.width)))
            await capture_window(self, output / 'home-partial.png')
            assert all(abs(item['join'] - expected) <= 1 for item in report['samples']), report
            owner = await fixture_reader(self, output, pages=4)
            await asyncio.sleep(.7)
            await owner.move_book_page(0)
            assert owner.comic_navigation.visible == (0, 1)
            report['comic_seam'] = seam_fraction(owner, owner.book_content)
            assert report['comic_seam'] is not None
            await asyncio.sleep(.5)
            canvas = owner.book_content.children[0].canvas._impl
            rect = canvas.picture.convertRect(canvas.picture.bounds, toView=window)
            image = canvas.interface.image._impl.native
            center_pixel = round(float(image.size.width) * report['comic_seam'])
            join = float(rect.origin.x + rect.size.width * center_pixel / image.size.width)
            report['comic_join'] = dict(join=join, expected=expected)
            assert abs(join - expected) <= 1, report['comic_join']
            await capture_window(self, output / 'comic-partial.png')
            self._hinge_status = 3
            self.show_home()
            await asyncio.sleep(.5)
            assert seam_fraction(self, self.home_content) is None
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))


def main():
    FoldSeamProbe('Logistics Mobile', 'io.github.ispaure.logisticsmobile.foldprobe').main_loop()
