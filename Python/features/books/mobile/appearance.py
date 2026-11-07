"""Native comic appearance form. Hosts persist the selected layout."""
import sys

import toga
from toga.style import Pack
from toga.style.pack import COLUMN


class ReaderAppearance(toga.ScrollContainer):
    def __init__(self, values, on_apply):
        self.volume_pages = None
        volume_controls = []
        if sys.platform == 'android':
            self.volume_pages = toga.Switch('Volume buttons turn pages',
                value=values['comic_volume_pages'] == 'true', style=Pack(height=48))
            volume_controls = [self.volume_pages,
                toga.Label('Volume down: next page. Volume up: previous page. Only while reading.')]
        self.layout_choice = toga.Selection(items=['single', 'auto', 'double'],
            value=values['comic_layout'], style=Pack(height=44))
        self.split_wide = toga.Switch('Split wide pages in portrait',
            value=values['comic_split_wide'] == 'true', style=Pack(height=48))
        self.status = toga.Label('Layout changes keep your current page.')
        content = toga.Box(children=[toga.Label('Comic page layout'), self.layout_choice,
            toga.Label('Auto: one page in portrait; two pages when the reading area is wider than tall. Comic metadata controls reading direction.'),
            self.split_wide, toga.Label('Swipe through overlapping halves in reading order. Landscape shows the whole wide page.'),
            *volume_controls, self.status, toga.Button('Apply and return', on_press=on_apply, style=Pack(height=44))],
            style=Pack(direction=COLUMN, margin=12))
        super().__init__(horizontal=False, content=content, style=Pack(flex=1))

    def settings(self):
        values = dict(comic_layout=self.layout_choice.value,
                      comic_split_wide='true' if self.split_wide.value else 'false')
        if self.volume_pages is not None:
            values['comic_volume_pages'] = 'true' if self.volume_pages.value else 'false'
        return values
