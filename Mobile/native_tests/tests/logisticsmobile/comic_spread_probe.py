"""Native composition proof for mobile auto layout and metadata direction."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from logisticsmobile.app import LogisticsMobile
from logisticsmobile.comic_layout_check import fixture_reader


class ComicSpreadProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('comic-spread-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        report = {'success': False, 'samples': []}
        try:
            await asyncio.sleep(1)
            assert self.preferences.values['comic_layout'] == 'auto'
            for rtl in (False, True):
                output = self.private_root / ('rtl' if rtl else 'ltr')
                output.mkdir(exist_ok=True)
                owner = await fixture_reader(self, output, pages=4, right_to_left=rtl)
                task = getattr(owner, '_comic_layout_task', None)
                if task is not None:
                    task.cancel()
                assert owner.book_reader.right_to_left == rtl
                # Exercise both pane shapes with real native spread composition.
                # The controller's ordinary resize watcher uses this same source.
                for viewport, expected in (((1100, 1000), (0, 1)), ((1000, 1100), (0,)), ((1000, 1000), (0,))):
                    owner.comic_viewport = lambda value=viewport: value
                    await owner.move_book_page(0)
                    assert owner.comic_navigation.visible == expected
                    view = owner.book_content.children[0]
                    assert hasattr(view, 'canvas') == (len(expected) == 2)
                    report['samples'].append(dict(right_to_left=rtl, viewport=viewport, visible=expected))
                owner.comic_viewport = lambda: (1100, 1000)
                await owner.move_book_page(0)
                owner.swipe_book_page(-1 if rtl else 1)
                await owner._comic_swipe_task
                assert owner.comic_navigation.visible == (2, 3)
                await owner.previous_book_page()
                assert owner.comic_navigation.visible == (0, 1)
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        report['backend'] = type(self._impl).__module__
        (Path(self.paths.cache) / 'comic-spread-result.json').write_text(json.dumps(report, indent=2))


def main():
    ComicSpreadProbe('Logistics Mobile', 'io.github.ispaure.logisticsmobile').main_loop()
