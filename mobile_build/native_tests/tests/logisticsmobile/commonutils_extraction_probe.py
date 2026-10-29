"""Disposable simulator/emulator proof of shared presentation with synthetic data."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.ui.native.event_loop import bind_cooperative_loop
from commonUtils.ui.native.appearance import SurfacePainter, SurfaceStyle, default_palette, default_apple_color
from commonUtils.ui.native.draw_ready import wait_for_draw
from commonUtils.ui.native.icons import IconSpec, IconRenderer
from commonUtils.ui.native.forms import FittedLabel, fit_text, disclosure, collapsible
from commonUtils.ui.native.recycled_list import RecycledList, ListAppearance
from commonUtils.ui.native.text_size import TextSizeBinding

BUNDLE = 'io.github.ispaure.logisticsextractionqa'
APPLE = toga.platform.current_platform == 'iOS'
if APPLE:
    from toga_iOS.app import PythonAppDelegate
    class LogisticsSceneAppDelegate(PythonAppDelegate):
        pass


class ExtractionProbe(toga.App):
    def startup(self):
        bind_cooperative_loop(self.loop)
        self.editor = toga.MultilineTextInput(value='Synthetic unsaved draft', style=Pack(height=80))
        self.command = toga.Button('Synthetic command', style=Pack(height=52))
        self.status = FittedLabel('Long synthetic status message and unbrokenidentifier123456789')
        self.field = toga.TextInput(value='Retained draft')
        self.advanced, self.toggle = collapsible('Advanced', [self.field])
        self.rows = RecycledList(data=[{'title': f'Item {i}', 'subtitle': 'Synthetic', 'folder': False,
                                       'icon': None, 'index': i, 'thumbnail': False}
                                      for i in range(1000)], style=Pack(flex=1),
                                 appearance=ListAppearance(high_contrast=lambda: True))
        self.panel = toga.Box(children=[self.status, self.command, self.editor, self.advanced, self.rows],
                              style=Pack(direction=COLUMN, flex=1))
        self.main_window = toga.MainWindow(title='Extraction QA', content=self.panel)
        self.main_window.show()

    def on_running(self):
        if not getattr(self, 'started', False):
            self.started = True
            self.loop.create_task(self.check())

    async def check(self):
        report = dict(success=False, cases=[], synthetic=True,
                      environment='ios-simulator' if APPLE else 'android-emulator')
        resources = []
        try:
            await asyncio.sleep(.5)
            assert await wait_for_draw(self.panel, timeout=3)
            report['cases'].append('native_draw_acknowledgement')
            icons = IconRenderer({
                'vector': IconSpec('square', '[]', (((3, 3), (21, 3), (21, 21), (3, 21), (3, 3)),),
                                   fills=(((8, 8), (16, 8), (16, 16), (8, 16)),), apple_vector=True),
                'skip': IconSpec('gobackward.15', '15', (((8, 2), (3, 5), (7, 8)),),
                                 arcs=((3, 3, 21, 21, -50, -280),), text='15', apple_vector=True),
            })
            callback = self.command.on_press
            for name in ('vector', 'skip', 'vector'):
                icons.apply(self.command, name, 'Synthetic action', preserve_layout=True)
            assert self.command.on_press is callback
            disclosure(self.command)
            fit_text(self.status, 160)
            assert '\n' in self.status.text
            fit_text(self.status, 2000)
            assert self.status.text == self.status._settings_source_text
            report['cases'].append('native_icon_artwork_accessory_and_text_measurement')
            self.toggle.on_press()
            body = self.advanced.children[1]
            self.toggle.on_press()
            self.toggle.on_press()
            assert self.advanced.children[1] is body and self.field.value == 'Retained draft'
            report['cases'].append('retained_collapsed_form')
            self.rows.select_index(999)
            self.rows.scroll_to_row(999)
            self.rows.refresh_palette()
            await asyncio.sleep(.3)
            assert self.rows.selection.title == 'Item 999'
            if not APPLE:
                count = self.rows._impl.native.getChildCount()
                assert 0 < count < 100, count
                report['visible_native_rows'] = count
            report['cases'].append('recycled_list_selection_scroll_and_high_contrast')
            sizes = [16]
            binding = TextSizeBinding(self.editor, loop=self.loop, get_size=lambda: sizes[0],
                                      save_size=lambda size: sizes.__setitem__(0, size))
            binding.install()
            resources.append(binding.dispose)
            if APPLE:
                binding.gesture('begin')
                binding.gesture('change', 1.5)
                binding.gesture('end')
            else:
                # Exercise the actual Java touch listener with native MotionEvents.
                from android.view import MotionEvent, InputDevice
                from android.os import SystemClock
                from java import jarray
                props = jarray(MotionEvent.PointerProperties)(2)
                coords = jarray(MotionEvent.PointerCoords)(2)
                for index in range(2):
                    props[index] = MotionEvent.PointerProperties()
                    props[index].id = index
                    props[index].toolType = MotionEvent.TOOL_TYPE_FINGER
                    coords[index] = MotionEvent.PointerCoords()
                    coords[index].y = 20
                    coords[index].pressure = coords[index].size = 1
                now = SystemClock.uptimeMillis()
                for action, span in ((MotionEvent.ACTION_POINTER_DOWN, 100), (MotionEvent.ACTION_MOVE, 150),
                                     (MotionEvent.ACTION_POINTER_UP, 150)):
                    coords[0].x, coords[1].x = 20, 20 + span
                    event = MotionEvent.obtain(now, now + 10, action, 2, props, coords, 0, 0,
                                               1., 1., 0, 0, InputDevice.SOURCE_TOUCHSCREEN, 0)
                    assert binding.listener.onTouch(self.editor._impl.native, event)
                    event.recycle()
            assert sizes[0] == 24 and self.editor.value == 'Synthetic unsaved draft'
            report['cases'].append('native_pinch_binding')
            if APPLE:
                from commonUtils.ui.native.keyboard import install
                keyboard = install(self.main_window)
                resources.append(keyboard.dispose)
                assert keyboard.gesture is not None
                from commonUtils.ui.native.bars import apple_bar_group, apple_bar_title, apple_bar_separator
                button = toga.Button('Retained bar action')
                item, group = apple_bar_group([button])
                title, label = apple_bar_title('Synthetic title', 180, group)
                self._bar_resources = item, group, title, label, apple_bar_separator()
                assert str(label.text) == 'Synthetic title' and len(group.arrangedSubviews) == 1
                self.panel._impl.native.addSubview(title)
                title.layoutIfNeeded()
                assert title.readerWidth is not None
                report['cases'].append('native_keyboard_and_retained_uikit_bar')
            else:
                from commonUtils.ui.native.keyboard import SearchDismissal
                from android.view import MotionEvent
                from android.os import SystemClock
                keyboard = SearchDismissal(self.field)
                keyboard.bind([self.command])
                resources.append(keyboard.dispose)
                self.field._impl.native.requestFocus()
                assert self.field._impl.native.hasFocus()
                now = SystemClock.uptimeMillis()
                event = MotionEvent.obtain(now, now, MotionEvent.ACTION_DOWN, 0., 0., 0)
                assert not keyboard.listener.onTouch(self.command._impl.native, event)
                event.recycle()
                assert not self.field._impl.native.hasFocus()
                report['cases'].append('native_keyboard_outside_touch')
                from commonUtils.ui.native.bars import android_bar
                control = toga.Button('Retained bar action')
                root, title, status = android_bar(self._impl.native, [], [control])
                self._bar_resources = root, title, status, control
                assert control._impl.native.getParent() is not None
                report['cases'].append('native_android_bar_mount')
            painter = SurfacePainter(high_contrast=lambda: True)
            painter.paint(self.command._impl, SurfaceStyle(high_contrast_selected=True, foreground='text'))
            painter.paint(self.status._impl, SurfaceStyle(radius=0, background='surface', foreground='text'))
            report['cases'].append('native_high_contrast_surfaces')
            for dispose in reversed(resources):
                dispose()
            resources.clear()
            assert binding.closed
            binding.gesture('begin')
            binding.gesture('change', 2)
            binding.gesture('end')
            assert sizes[0] == 24
            report['cases'].append('native_resource_disposal')
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            for dispose in reversed(resources):
                dispose()
            output = Path(self.paths.cache) / 'commonutils-extraction-result.json'
            output.write_text(json.dumps(report, indent=2) + '\n')
            print('COMMONUTILS_EXTRACTION=' + json.dumps(report), flush=True)


def main():
    return ExtractionProbe('Extraction QA', BUNDLE)
