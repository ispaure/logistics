"""Disposable iOS glass/background, grouping, layout and close-safety probe."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
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
        from .fixtures import ios_toolbar_items
        await asyncio.sleep(.5)
        controller = self._reader_toolbar_controller
        nav = controller.navigationItem
        leading = ios_toolbar_items(controller, leading=True)
        actions = ios_toolbar_items(controller)
        assert leading and str(leading[0].accessibilityLabel) == 'Close document'
        assert all(item.customView is None and item.accessibilityLabel
                   for item in (*leading, *actions))
        assert actions or nav.additionalOverflowItems is not None
        self.bubble_checks.append(dict(stage=stage,
            leading=[str(item.title or item.accessibilityLabel) for item in leading], actions=[str(item.title) for item in actions],
            groups=len(nav.trailingItemGroups), overflow=nav.additionalOverflowItems is not None))
        await capture_window(self, Path(self.paths.cache) / (stage + '.png'))

    async def check(self):
        self.bubble_checks = []
        try:
            from rubicon.objc import ObjCClass
            from mobile.workspace_navigation import menu_button
            from mobile.appearance import paint_surface
            standalone = menu_button(lambda widget: None)
            for _ in range(2):
                paint_surface(standalone._impl, 8)
                assert standalone._impl.native.configuration is not None
                assert standalone._impl.native.backgroundColor.isEqual(ObjCClass('UIColor').clearColor)
            from commonUtils.runtime.resources.documents import LocalDocuments
            fixtures = Path(self.paths.cache) / 'bubble-fixtures'
            fixtures.mkdir(exist_ok=True)
            epub, _ = make_books(fixtures)
            record = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)
            await self.open_book(record['id'])
            owner = self.readers.active
            for mode, style in (('light', 1), ('dark', 2)):
                self.main_window._impl.native.overrideUserInterfaceStyle = style
                await self.inspect('epub-' + mode)
                assert self._reader_toolbar_controller.navigationItem.trailingItemGroups
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
