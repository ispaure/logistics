"""Native Android folder hierarchy keeps its scrollbar outside row outlines."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER

from mobile.appearance import install_appearance, refresh_appearance
from mobile.folder_hub_style import folder_scroll, folder_row, folder_name, compact_icon
from mobile.control_icons import icon_button
from mobile.palette import set_eink_enabled
from .fixtures import capture_window


class FolderTreeScrollbarProbe(toga.App):
    def startup(self):
        install_appearance(self)
        self.rows = []
        content = toga.Box(style=Pack(direction=COLUMN))
        for index in range(70):
            row = toga.Box(style=Pack(direction=ROW, align_items=CENTER, height=48, margin_left=40 * (index % 3)))
            indicator = icon_button('folder', 'Folder')
            compact_icon(indicator, width=48, size=24)
            row.add(indicator, folder_name(toga.Button(f'Group / Folder {index:02}', style=Pack(flex=1))))
            folder_row(row)
            content.add(row)
            self.rows.append(row)
        self.scroll = folder_scroll(content)
        self.main_window = toga.MainWindow(title='Folder hierarchy scrollbar QA')
        self.main_window.content = toga.Box(children=[self.scroll], style=Pack(direction=COLUMN, flex=1, margin=16))
        self.main_window.show()

    def on_running(self):
        self.loop.create_task(self.check())

    async def check(self):
        output = Path(self.paths.cache) / 'folder-tree-scrollbar'
        output.mkdir(exist_ok=True)
        result = {'success': False, 'gaps': []}
        try:
            from java import jarray, jint
            def x(widget):
                coordinates = jarray(jint)(2)
                widget._impl.native.getLocationOnScreen(coordinates)
                return int(coordinates[0])
            native = self.scroll._impl.native
            native.setScrollbarFadingEnabled(False)
            for contrast in (False, True):
                set_eink_enabled(contrast)
                refresh_appearance(self)
                for position in (0, 800):
                    self.scroll._impl.set_position(0, position)
                    await asyncio.sleep(.5)
                    if position:
                        assert native.getScrollY() > 0
                    required = native.getVerticalScrollbarWidth() + self.scroll._impl.scale_in(4)
                    viewport_right = x(self.scroll) + native.getWidth()
                    gap = min(viewport_right - x(row) - row._impl.native.getWidth() for row in self.rows)
                    assert gap >= required - 1, (gap, required)
                    result['gaps'].append({'contrast': contrast, 'position': position, 'pixels': gap})
                    await capture_window(self, output / (f'{contrast}-{position}.png'))
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(result, indent=2))
        print('FOLDER_TREE_SCROLLBAR=' + json.dumps(result), flush=True)


def main():
    FolderTreeScrollbarProbe('Folder tree scrollbar QA', 'io.github.ispaure.logisticsmobilespacingqa').main_loop()
