"""Prepare disposable files for the UIKit long-press drag acceptance test."""

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "marcandre.voyer@gmail.com"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
import json
from pathlib import Path
import sys
import traceback

from commonUtils.testing.stages import TestStage
from . import start_native_check
from .notebook_probe import NotebookProbe


TEST_STAGE = TestStage.EXTENDED


class FileDragGestureProbe(NotebookProbe):
    def on_running(self):
        start_native_check(self, type(self).prepare_fixture)

    async def prepare_fixture(self):
        startup = getattr(self, 'startup_task', None)
        if startup is not None:
            await asyncio.shield(startup)
        assert await self.show_files(location=('Local files', ''))
        root = self.file_provider.root
        (root / 'Drop destination').mkdir(exist_ok=True)
        (root / 'List source').mkdir(exist_ok=True)
        (root / 'List source' / 'nested.txt').write_text('List drag')
        (root / 'Tile source.txt').write_text('Tile drag')
        self.file_browser._show_mode('List')
        assert await self.browse_files()
        cache = Path(self.paths.cache)
        if getattr(self.file_browser, '_file_drag_delegate', None) is not None:
            from commonUtils.ui.native.keyboard import native_value
            browser = self.file_browser
            original_actions = browser.on_item_actions
            drag = browser.file_drag
            finish = drag.finish
            move = drag.move

            def record(event, **values):
                with (cache / 'file-drag-events.jsonl').open('a') as stream:
                    stream.write(json.dumps(dict(event=event, path=self.file_path, **values)) + '\n')

            def finish_and_record(token, target):
                record('drop', target=None if target is None else target.label,
                       actual_source=drag.source is not None, enters_folder=drag.entered is not None,
                       opening=drag.opening, in_browser=drag.context() is not None)
                return finish(token, target)

            async def move_and_record(operation, stamp):
                succeeded = await move(operation, stamp)
                record('move', succeeded=succeeded, status=self.file_status.value)
                return succeeded

            def check_menu(row):
                gesture = browser._file_drag_delegate[-1]
                if int(native_value(gesture.state)) in (1, 2):
                    (cache / 'file-drag-tile-menu-held.txt').touch()
                original_actions(row)

            browser.on_item_actions = check_menu
            drag.finish = finish_and_record
            drag.move = move_and_record
        (cache / 'file-drag-fixture.json').write_text(json.dumps({'root': str(root)}))
        for _ in range(800):
            if not (root / 'List source').exists() and self.file_status.value == 'Moved to Drop destination.':
                assert self.file_path == 'Drop destination', 'List hover did not open the folder'
                assert (root / 'Drop destination/List source/nested.txt').read_text() == 'List drag'
                (cache / 'file-drag-list-opened.txt').write_text(self.file_path)
                assert await self.browser_file_location(('Local files', ''))
                self.file_browser.show_tiles()
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError('List move did not complete')
        for _ in range(800):
            if not (root / 'Tile source.txt').exists() and self.file_status.value == 'Moved to Drop destination.':
                assert self.file_path == 'Drop destination', 'Tile hover did not open the folder'
                assert (root / 'Drop destination/Tile source.txt').read_text() == 'Tile drag'
                (cache / 'file-drag-tiles-opened.txt').write_text(self.file_path)
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError('Tile move did not complete')

        destination = root / 'Drop destination' / 'Group destination'
        destination.mkdir()
        self.file_browser._show_mode('List')
        assert await self.browse_files()
        for _ in range(450):
            if (destination / 'Tile source.txt').exists():
                if getattr(self.file_browser, '_file_drag_delegate', None) is not None:
                    assert (cache / 'file-drag-tile-menu-held.txt').exists()
                assert (destination / 'Tile source.txt').read_text() == 'Tile drag'
                assert (destination / 'List source/nested.txt').read_text() == 'List drag'
                assert not (destination.parent / 'Tile source.txt').exists()
                assert not (destination.parent / 'List source').exists()
                (cache / 'file-drag-result.json').write_text(json.dumps({'list_spring_opened': True,
                    'tiles_spring_opened': True, 'destination_bytes_match': True, 'batch_move_verified': True}))
                return
            await asyncio.sleep(.1)
        raise AssertionError('Group move did not complete')


class AndroidFileDragGestureProbe(NotebookProbe):
    def on_running(self):
        start_native_check(self, type(self).check_android)

    async def check_android(self):
        from commonUtils.formats.image_headers import image_header
        from commonUtils.testing.waiting import wait_until
        from mobile.native.file_drag_android import screen_origin
        from .browser_thumbnail_checks import cached, png, preview_attached

        cache = Path(self.paths.cache)
        report = dict(success=False)
        observed = cache / 'file-drag-held-menu.txt'
        request = cache / 'file-drag-android-request.json'

        def center(view):
            x, y = screen_origin(view)
            assert view.isShown() and view.getWidth() > 0 and view.getHeight() > 0
            return [x + view.getWidth() // 2, y + view.getHeight() // 2]

        async def request_input(**data):
            pending = request.with_suffix('.tmp')
            pending.write_text(json.dumps(data))
            pending.replace(request)
            await wait_until(lambda: not request.exists(), timeout=30)

        try:
            if getattr(self, 'startup_task', None) is not None:
                await asyncio.shield(self.startup_task)
            assert await self.show_files(location=('Local files', ''))
            root = self.file_provider.root
            target = root / 'Drop destination'
            target.mkdir()
            files = {'List file.txt': b'List drag', 'Tile image.png': png(1600, (30, 100, 170))}
            for name, data in files.items():
                (root / name).write_bytes(data)
            browser = self.file_browser
            await wait_until(lambda: browser.file_drag.context() is not None, timeout=15,
                             message='The local File Browser did not become ready for drag.')
            original_actions = browser.on_item_actions

            def menu(row):
                observed.touch()
                original_actions(row)

            browser.on_item_actions = menu
            for mode, filename in zip(('List', 'Tiles'), files):
                browser._show_mode(mode)
                assert await self.browse_files()
                await asyncio.sleep(.4)
                if mode == 'List':
                    impl = browser.native_list._impl.native
                    views = {row.title: impl.getChildAt(index - impl.getFirstVisiblePosition())
                             for index, row in enumerate(browser.native_list.data)}
                else:
                    source = next(entry for entry in browser.entries if entry.label == filename)
                    await wait_until(lambda: preview_attached(browser, source.identity), timeout=12)
                    thumbnail = image_header(cached(browser, filename), max_bytes=1024 * 1024)
                    assert thumbnail.width == browser._tile_thumbnail_size()[0] > 160
                    report['tile_thumbnail_pixels'] = thumbnail.width
                    views = {}
                    for entry, card, *_ in browser._tile_cards.values():
                        preview = card.children[-2]
                        icon = preview.children[0]
                        actual = center(icon._impl.native)
                        expected = center(preview._impl.native)
                        assert all(abs(a - b) <= 2 for a, b in zip(actual, expected)), (actual, expected)
                        views[entry.label] = icon._impl.native
                    report['tile_media_centered'] = True
                    opened = []
                    original_open = browser.on_open_file
                    browser.on_open_file = lambda row: opened.append(row['path'])
                    try:
                        await request_input(gesture='tap', start=center(views[filename]))
                        assert opened == [filename], opened
                    finally:
                        browser.on_open_file = original_open
                    self.begin_file_selection()
                    await asyncio.sleep(.2)
                    image, _ = browser._tile_previews[source.identity]
                    point = center(image._impl.native)
                    await request_input(gesture='tap', start=point)
                    assert browser.checked_entries == {source.identity}
                    await request_input(gesture='tap', start=point)
                    assert not browser.checked_entries
                    self.end_file_selection()
                    await wait_until(lambda: preview_attached(browser, source.identity), timeout=12)
                    views = {entry.label: card.children[-2].children[0]._impl.native
                             for entry, card, *_ in browser._tile_cards.values()}
                    report['tile_artwork_taps_open_and_select'] = True
                    await request_input(gesture='menu', start=center(views[filename]))
                    assert observed.exists(), 'Holding still did not invoke the tile menu'
                    report['tile_menu_opened'] = True
                await request_input(gesture='drag', layout=mode.lower(), start=center(views[filename]),
                                    target=center(views[target.name]))
                await wait_until(lambda: (target / filename).is_file(), timeout=12,
                                 message='Android drag did not move ' + filename)
                assert self.file_path == target.name, 'Dwell did not open the destination'
                assert (target / filename).read_bytes() == files[filename] and not (root / filename).exists()
                report[mode.lower() + '_spring_open_and_move'] = True
                assert await self.browser_file_location(('Local files', ''))
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (cache / 'file-drag-android-result.json').write_text(json.dumps(report, indent=2))


def main():
    probe = FileDragGestureProbe if sys.platform == 'ios' else AndroidFileDragGestureProbe
    return probe('File Drag QA', 'io.github.ispaure.logisticsnotebookqa')
