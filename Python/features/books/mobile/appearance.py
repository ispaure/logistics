"""Shared native Books & Comics appearance form; hosts persist preferences."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN


class ReaderAppearance(toga.ScrollContainer):
    def __init__(self, values, on_apply, *, kind='epub'):
        self.kind = kind
        def select(key, items):
            return toga.Selection(items=items, value=values[key], style=Pack(height=44))
        if kind == 'comic':
            self.layout_choice = select('comic_layout', ['single', 'auto', 'double'])
            self.split_wide = toga.Switch('Split wide pages in portrait',
                value=values.get('comic_split_wide', 'true') == 'true', style=Pack(height=48))
            self.status = toga.Label('Layout changes keep your current page.')
            content = toga.Box(children=[toga.Label('Comic page layout'), self.layout_choice,
                toga.Label('Auto: one page in portrait; two pages when the reading area is wider than tall. Comic metadata controls reading direction.'),
                self.split_wide, toga.Label('Swipe through overlapping halves in reading order. Landscape shows the whole wide page.'),
                self.status, toga.Button('Apply and return', on_press=on_apply, style=Pack(height=44))],
                style=Pack(direction=COLUMN, margin=12))
            super().__init__(horizontal=False, content=content, style=Pack(flex=1))
            return
        from .typography import FONT_SIZES
        self.font_choice = select('epub_font_size', list(FONT_SIZES))
        self.margin_choice = select('reading_margin', ['8', '16', '24', '32'])
        from .typography import font_families, THEMES, DEFAULTS
        values = dict(DEFAULTS, **values)
        self.justify_choice = toga.Switch('Justify text', value=values['epub_justify'] == 'true', style=Pack(height=48))
        self.family_choice = select('reading_font', sorted(set(font_families()) | {values['reading_font']}))
        self.family_choice.style.width = 250
        self.spacing_choice = toga.NumberInput(min=100, max=220, step=5, value=int(values['line_spacing']), style=Pack(height=44))
        self.width_choice = toga.NumberInput(min=0, max=1400, step=20, value=0 if values['reading_width'] == 'auto' else int(values['reading_width']), style=Pack(height=44))
        self.theme_choice = select('reading_theme', list(THEMES))
        self.status = toga.Label('Appearance changes keep your current passage.')
        content = toga.Box(children=[toga.Label('Reading font'), self.family_choice,
            toga.Label('Reading font size'), self.font_choice,
            self.justify_choice,
            toga.Label('Line spacing (%)'), self.spacing_choice, toga.Label('Maximum width (0 = automatic)'), self.width_choice,
            toga.Label('Page margins'), self.margin_choice, toga.Label('Theme (system follows device)'), self.theme_choice,
            self.status,
            toga.Button('Apply and return', on_press=on_apply, style=Pack(height=44))],
            style=Pack(direction=COLUMN, margin=12))
        super().__init__(horizontal=False, content=content, style=Pack(flex=1))

    def typography(self):
        from .typography import validate
        if self.spacing_choice.value is None or self.width_choice.value is None:
            raise ValueError('Enter line spacing and maximum reading width.')
        if self.spacing_choice.value != int(self.spacing_choice.value) or self.width_choice.value != int(self.width_choice.value):
            raise ValueError('Use whole numbers for spacing and reading width.')
        values = dict(reading_font=self.family_choice.value, line_spacing=str(int(self.spacing_choice.value)),
            reading_width='auto' if self.width_choice.value == 0 else str(int(self.width_choice.value)),
            epub_justify='true' if self.justify_choice.value else 'false')
        validate(dict(values, reading_theme=self.theme_choice.value))
        return values

    def settings(self):
        if self.kind == 'comic':
            return dict(comic_layout=self.layout_choice.value, comic_split_wide='true' if self.split_wide.value else 'false')
        return dict(epub_font_size=self.font_choice.value, reading_margin=self.margin_choice.value,
                    reading_theme=self.theme_choice.value, **self.typography())
