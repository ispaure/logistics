"""Synthetic native workspace rows: outline clearance and stable theme geometry."""
import asyncio
import json
from pathlib import Path
import traceback

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW

from logisticsmobile.appearance import list_button, paint_surface
from logisticsmobile.control_icons import icon_button
from logisticsmobile.folder_hub_style import compact_icon, folder_name, folder_row
from logisticsmobile.palette import set_eink_enabled


class WorkspaceSpacingProbe(toga.App):
    def startup(self):
        self.rows = []
        content = toga.Box(style=Pack(direction=COLUMN, margin=24))
        for source, icon in (('Local', 'folder'), ('Cloud', 'folder_locked'),
                             ('Home Server', 'folder_unlocked')):
            content.add(toga.Label(source, style=Pack(margin_top=16, margin_bottom=8)))
            indicator = icon_button(icon, source + ' folder')
            compact_icon(indicator, width=48, size=24)
            title = folder_name(list_button(toga.Button('Example workspace', style=Pack(flex=1))))
            menu = icon_button('more', 'Workspace actions')
            compact_icon(menu, width=48, size=18)
            row = folder_row(toga.Box(children=[indicator, title, menu],
                style=Pack(direction=ROW, height=48, align_items=CENTER)))
            content.add(row)
            self.rows.append((row, indicator, title, menu))
        self.main_window = toga.MainWindow(title='Workspace spacing QA')
        self.main_window.content = content
        self.main_window.show()

    def on_running(self):
        self.loop.create_task(self.check())

    async def check(self):
        result = {'success': False, 'modes': {}}
        output = Path(self.paths.cache) / 'workspace-spacing.json'
        try:
            baseline = None
            for enabled in (False, True, False):
                set_eink_enabled(enabled)
                for widgets in self.rows:
                    for widget in widgets:
                        paint_surface(widget._impl, 8 if widget is widgets[0] else 0)
                await asyncio.sleep(.5)
                geometry = []
                for row, indicator, title, menu in self.rows:
                    controls = []
                    for widget in (indicator, title, menu):
                        native = widget._impl.native
                        controls.append([native.getLeft(), native.getTop(), native.getWidth(),
                                         native.getHeight(), native.getPaddingLeft(), native.getPaddingRight(),
                                         float(native.getTextSize())])
                    for button, size in ((indicator, 24), (menu, 18)):
                        native = button._impl.native
                        bounds = button._impl._control_drawable.getBounds()
                        assert bounds.width() == button._impl.scale_in(size)
                        assert abs(native.getPaddingLeft() + bounds.width() / 2 - native.getWidth() / 2) <= 1
                        assert native.getPaddingLeft() >= button._impl.scale_in(12)
                    geometry.append(controls)
                if baseline is None:
                    baseline = geometry
                assert geometry == baseline, 'theme repaint moved or resized row content'
                result['modes']['contrast' if enabled else 'regular'] = geometry
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        output.write_text(json.dumps(result, indent=2))
        print('WORKSPACE_SPACING=' + json.dumps(result), flush=True)


def main():
    WorkspaceSpacingProbe('Workspace spacing QA', 'io.github.ispaure.logisticsworkspacespacingqa').main_loop()
