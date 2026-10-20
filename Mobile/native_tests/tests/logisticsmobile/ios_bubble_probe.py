"""Disposable iOS glass/background, grouping, layout and close-safety probe."""
import asyncio
import json
from pathlib import Path
import traceback

from .reader_close_icon_probe import ReaderCloseIconProbe
from .fixtures import capture_window, make_books


class BubbleProbe(ReaderCloseIconProbe):
    async def capture_stage(self, stage):
        await self.inspect(stage)

    async def inspect(self, stage):
        from rubicon.objc import ObjCClass
        from logisticsmobile.appearance import paint_surface
        await asyncio.sleep(.5)
        view = self.body
        # The reader can be inside the workspace container.
        def reader(widget):
            if hasattr(widget, '_native_reader_buttons'):
                return widget
            return next((found for child in widget.children if (found := reader(child)) is not None), None)
        view = reader(view)
        assert view is not None
        buttons = [view._reader_close_button, *view._native_reader_buttons()]
        window = self.main_window._impl.native
        frames = []
        for button in buttons:
            button.refresh()
            paint_surface(button._impl, 8)
        window.layoutIfNeeded()
        await asyncio.sleep(.2)
        for button in buttons:
            native = button._impl.native
            assert native.configuration is None
            assert native.backgroundColor.isEqual(ObjCClass('UIColor').clearColor)
            assert float(native.layer.borderWidth) == 0
            rect = native.convertRect(native.bounds, toView=window)
            x, y, w, h = map(float, (rect.origin.x, rect.origin.y, rect.size.width, rect.size.height))
            # UIKit fits custom content to the bar's 36-point visual height.
            assert w >= 44 and h >= 32, (stage, button.accessible_name, w, h)
            assert x >= 0 and x + w <= float(window.bounds.size.width) + 1, (stage, x, w)
            frames.append((button.accessible_name, x, y, w, h))
        ordered = sorted(frames, key=lambda frame: frame[1])
        assert all(a[1] + a[3] <= b[1] + 1 for a, b in zip(ordered, ordered[1:])), frames
        self.bubble_checks.append(dict(stage=stage, frames=frames))
        await capture_window(self, Path(self.paths.cache) / (stage + '.png'))

    async def check(self):
        self.bubble_checks = []
        try:
            from rubicon.objc import ObjCClass
            from logisticsmobile.workspace_navigation import menu_button
            from logisticsmobile.appearance import paint_surface
            standalone = menu_button(lambda widget: None)
            for _ in range(2):
                paint_surface(standalone._impl, 8)
                assert standalone._impl.native.configuration is not None
                assert standalone._impl.native.backgroundColor.isEqual(ObjCClass('UIColor').clearColor)
            from commonUtils.runtime.document_access import LocalDocuments
            fixtures = Path(self.paths.cache) / 'bubble-fixtures'
            fixtures.mkdir(exist_ok=True)
            epub, _ = make_books(fixtures)
            record = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)
            await self.open_book(record['id'])
            owner = self.readers.active
            for mode, style in (('light', 1), ('dark', 2)):
                self.main_window._impl.native.overrideUserInterfaceStyle = style
                await self.inspect('epub-' + mode)
                assert len(self._reader_toolbar_groups) == 2
                assert owner.reader_actions_button._impl.native.menu is not None
                assert owner.reader_actions_button._impl.native.showsMenuAsPrimaryAction
                # Fullscreen rebuilds both items and their native menu anchors.
                owner.set_reading_mode(True)
                await asyncio.sleep(.2)
                owner.set_reading_mode(False)
                await self.inspect('epub-' + mode + '-restored')
            owner.reader_speech_button._impl.native.sendActionsForControlEvents(1 << 6)
            await asyncio.sleep(.5)
            assert getattr(owner, 'speech_panel', None) is not None
            owner.close_read_aloud()
            from .compact_reading_probe import CompactReadingProbe
            await CompactReadingProbe.rotate(self, True)
            await self.inspect('epub-landscape')
            await CompactReadingProbe.rotate(self, False)
            await self.inspect('epub-portrait-return')
            owner.library_view._reader_close_button._impl.native.sendActionsForControlEvents(1 << 6)
            await asyncio.sleep(.4)
            assert owner.session.id not in self.workspace.sessions
            await super().check()
            path = Path(self.paths.cache) / 'close-icon-result.json'
            result = json.loads(path.read_text())
            assert result['success'], result
            result['bubble_checks'] = self.bubble_checks
        except Exception:
            result = dict(success=False, error=traceback.format_exc(), bubble_checks=self.bubble_checks)
        (Path(self.paths.cache) / 'bubble-result.json').write_text(json.dumps(result, indent=2))


def main():
    return BubbleProbe('Bubble QA', 'io.github.ispaure.logisticsbubbleqa')
