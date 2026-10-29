"""Synthetic native grouped-list checks: corners, selection and recycling."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback

import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from mobile.appearance import install_appearance, refresh_appearance, surface
from mobile.palette import set_eink_enabled
from mobile.recycled_file_list import RecycledFileList, file_list_icon
from .fixtures import capture_window


class FileListGroupProbe(toga.App):
    def startup(self):
        install_appearance(self)
        self.listing = RecycledFileList(style=Pack(flex=1))
        self.card = surface(toga.Box(children=[toga.Label('Same shape in both modes', style=Pack(margin=16))],
            style=Pack(direction=COLUMN, margin_bottom=12)), radius=16)
        self.content = surface(toga.Box(children=[self.card, self.listing],
            style=Pack(direction=COLUMN, flex=1, margin=16)),
            background='window', eink_outlined=False)
        self.main_window = toga.MainWindow(title='Grouped file list QA')
        self.main_window.content = self.content
        self.main_window.show()

    def on_running(self):
        self.loop.create_task(self.check())

    def populate(self, count):
        self.listing.data = [dict(title=f'Example {index:03}.txt', subtitle='',
            icon=file_list_icon(False), folder=False) for index in range(count)]

    async def check(self):
        output = Path(self.paths.cache) / 'file-list-group'
        output.mkdir(exist_ok=True)
        result = {'success': False}
        try:
            android = type(self._impl).__module__.startswith('toga_android.')
            native = self.listing._impl.native
            for mode in ('regular', 'contrast', 'regular-again') if android else ('light', 'dark'):
                if android:
                    set_eink_enabled(mode == 'contrast')
                else:
                    self.main_window._impl.native.overrideUserInterfaceStyle = 2 if mode == 'dark' else 1
                refresh_appearance(self)
                if android:
                    assert self.card._impl.native.getBackground().getCornerRadius() == self.card._impl.scale_in(16)
                self.populate(3)
                await asyncio.sleep(.7)
                self.listing.select_index(0)
                await asyncio.sleep(.2)
                if android:
                    assert native.getChildCount() == 3
                    assert native.getChildAt(0).getChildAt(0).getWidth() > 0
                else:
                    for cell in native.visibleCells:
                        index = native.indexPathForCell(cell).row
                        expected = (3 if index == 0 else 0) | (12 if index == 2 else 0)
                        assert cell.layer.cornerRadius == 16
                        assert int(cell.layer.maskedCorners) == expected
                await capture_window(self, output / (mode + '-short.png'))
                self.populate(100)
                await asyncio.sleep(.3)
                self.listing._impl.set_vertical_position(800)
                await asyncio.sleep(.4)
                assert self.listing._impl.get_vertical_position() > 0
                if not android:
                    for cell in native.visibleCells:
                        index = native.indexPathForCell(cell).row
                        assert 0 < index < 99
                        assert int(cell.layer.maskedCorners) == 0, 'recycled middle cell retained rounded corners'
                await capture_window(self, output / (mode + '-scrolled.png'))
                result[mode] = True
            self.populate(3)
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(result, indent=2))
        print('FILE_LIST_GROUP=' + json.dumps(result), flush=True)


def main():
    FileListGroupProbe('Grouped file list QA', 'io.github.ispaure.logisticsmobilespacingqa').main_loop()
