"""Synthetic native document groups retain geometry, status and row actions."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace as NS
import traceback

import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from mobile import appearance
from mobile.control_icons import button_icons
from mobile.hub_ui import HubUI, document_group, heading
from mobile.palette import set_eink_enabled
from .fixtures import capture_window


class DocumentGroupsProbe(toga.App):
    def startup(self):
        appearance.install_appearance(self)
        self.opened, self.closed = [], []
        facade = NS(workspace=NS(sessions={}),
            recent_opener=lambda session: lambda widget: self.opened.append(session.id),
            session_opener=lambda key: lambda widget: self.opened.append(key),
            session_closer=lambda key: lambda widget: self.closed.append(key))
        facade.document_button_icons = lambda button, session: button_icons(button, [
            ('storage_remote', 'Cloud'), ('storage_crypt', 'Locked')])
        self.content = toga.Box(style=Pack(direction=COLUMN, margin=16))
        self.groups, self.rows = [], []
        for title, count in (('Recent', 3), ('All open', 2), ('Saved documents', 1)):
            rows = []
            for index in range(count):
                session = NS(id=title + str(index), kind='text')
                details = ['Unsaved changes', 'Draft'] if title == 'All open' and index == 0 else []
                summary = (f'{title} example document {index}.txt', 'text', details)
                row = (HubUI.session_panel(facade, session, summary=summary, close=True)
                       if title == 'All open' else HubUI.recent_row(facade, session, summary))
                rows.append(row)
            group = document_group(rows)
            self.groups.append(group)
            self.rows.extend(rows)
            self.content.add(heading(title), group)
        self.main_window = toga.MainWindow(title='Grouped documents QA')
        self.main_window.content = toga.ScrollContainer(horizontal=False, content=self.content)
        self.main_window.show()

    def on_running(self):
        self.loop.create_task(self.check())

    async def check(self):
        output = Path(self.paths.cache) / 'document-groups'
        output.mkdir(exist_ok=True)
        result = {'success': False, 'geometry': {}}
        try:
            android = type(self._impl).__module__.startswith('toga_android.')
            baseline = None
            for mode in ('regular', 'contrast', 'regular-again') if android else ('light', 'dark', 'light-again'):
                if android:
                    set_eink_enabled(mode == 'contrast')
                else:
                    self.main_window._impl.native.overrideUserInterfaceStyle = 2 if mode == 'dark' else 1
                appearance.refresh_appearance(self)
                await asyncio.sleep(.4)
                geometry = []
                for group in self.groups:
                    if android:
                        assert group._impl.native.getBackground().getCornerRadius() == group._impl.scale_in(16)
                    else:
                        assert group._impl.native.layer.cornerRadius == 16
                for row in self.rows:
                    for button in (row.document_button, getattr(row, 'close_button', None)):
                        if button is None:
                            continue
                        assert not button._impl._surface_eink_outlined
                        native = button._impl.native
                        if android:
                            geometry.append([native.getLeft(), native.getTop(), native.getWidth(), native.getHeight(),
                                             native.getPaddingLeft(), native.getPaddingRight(), float(native.getTextSize())])
                        else:
                            frame, insets = native.frame, native.contentEdgeInsets
                            geometry.append([float(frame.origin.x), float(frame.origin.y), float(frame.size.width),
                                float(frame.size.height), float(insets.left), float(insets.right), float(native.titleLabel.font.pointSize)])
                if baseline is None:
                    baseline = geometry
                assert geometry == baseline, 'contrast changed document-row geometry'
                result['geometry'][mode] = geometry
                await capture_window(self, output / (mode + '.png'))
            for button in (self.rows[0].document_button, self.rows[3].close_button):
                if android:
                    button._impl.native.performClick()
                else:
                    button._impl.native.sendActionsForControlEvents(1 << 6)
            await asyncio.sleep(.2)
            assert self.opened == ['Recent0'] and self.closed == ['All open0']
            result['actions'] = True
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(result, indent=2))
        print('DOCUMENT_GROUPS=' + json.dumps(result), flush=True)


def main():
    DocumentGroupsProbe('Grouped documents QA', 'io.github.ispaure.logisticsmobilespacingqa').main_loop()
