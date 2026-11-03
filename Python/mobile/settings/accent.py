"""Native hue/saturation controls with transient preview and release-to-save."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from .forms import SettingsLabel
from ..appearance import accessible_name, surface, refresh_appearance
from ..palette import DEFAULT_ACCENT, accent_colors, set_accent
from ..reader_progress import style_slider


class AccentControls(toga.Box):
    def __init__(self, app):
        super().__init__(style=Pack(direction=COLUMN, margin_bottom=20))
        self._settings_managed_content = True
        self.app = app
        self._dragging = False
        self.add(SettingsLabel('Accent color', style=Pack(font_weight='bold', margin_bottom=12)))
        self.preview = surface(toga.Box(style=Pack(direction=ROW, margin_bottom=12)), radius=12)
        self.preview.add(surface(toga.Label('Workspaces', style=Pack(flex=1, margin=12)),
                                 radius=0, background='transparent', foreground='muted'))
        self.selected = toga.Label('Documents', style=Pack(flex=1, margin=12, font_weight='bold'))
        self.preview.add(self.selected)
        self.add(self.preview)
        self.hue_label = SettingsLabel('Hue')
        self.hue = toga.Slider(min=0, max=359,
            value=float(app.preferences.values['accent_hue']), style=Pack(height=48))
        self.saturation_label = SettingsLabel('Saturation')
        self.saturation = toga.Slider(min=0, max=100,
            value=float(app.preferences.values['accent_saturation']), style=Pack(height=48))
        self.spectrum = toga.Canvas(on_resize=self.draw_spectrum, style=Pack(height=6, margin_top=8))
        self._spectrum_width = 100
        self.add(self.hue_label, self.spectrum, self.hue, self.saturation_label, self.saturation)
        for slider, name in ((self.hue, 'Accent hue'), (self.saturation, 'Accent saturation')):
            accessible_name(slider, name)
            style_slider(slider)
            slider.on_press = self.begin_drag
            slider.on_change = self.changed
            slider.on_release = self.save
        self.add(SettingsLabel('Release to save. Brightness adjusts for readable light and dark colors.',
                               style=Pack(font_size=12, margin_bottom=8)))
        self.add(surface(toga.Button('Reset to blue', on_press=self.reset, style=Pack(height=48)),
                         foreground='accent'))
        self.add(SettingsLabel('Colors tabs, selections and controls. File, folder and workspace lock icons keep their colors.',
                               style=Pack(font_size=12, margin_top=8)))
        self.preview_color()

    def update_labels(self):
        self.hue_label.text = f'Hue · {self.hue.value:.0f}°'
        self.saturation_label.text = f'Saturation · {self.saturation.value:.0f}%'

    def preview_color(self, widget=None, **kwargs):
        self.update_labels()
        self.draw_spectrum(width=self._spectrum_width)
        light, dark = accent_colors(self.hue.value, self.saturation.value)
        # The filled tracks and thumbs preview the exact same opaque accent
        # as the selected tab, even before the saved app color changes.
        for slider in (self.hue, self.saturation):
            slider._accent_preview = (light, dark)
            style_slider(slider)
        from ..palette import eink_enabled, android_palette, DARK
        backend = type(self.app._impl).__module__
        if backend.startswith('toga_iOS.'):
            from commonUtils.ui.native.appearance import DynamicAppleColors
            self._preview_colors = DynamicAppleColors(lambda is_dark: {'accent': dark if is_dark else light})
            self.selected._impl.native.textColor = self._preview_colors.color('accent')
        else:
            # Android palette tracks application configuration, including E Ink.
            self.selected.style.color = '#000000' if eink_enabled() else dark if android_palette() is DARK else light

    def begin_drag(self, widget=None, **kwargs):
        self._dragging = True

    def changed(self, widget=None, **kwargs):
        self.preview_color()
        # VoiceOver, TalkBack and keyboard adjustments have no touch release.
        if not self._dragging:
            self.save()

    def draw_spectrum(self, widget=None, *, width, **kwargs):
        import colorsys
        from ..palette import eink_enabled
        self._spectrum_width = width
        self.spectrum.root_state.drawing_actions.clear()
        for step in range(72):
            rgb = colorsys.hls_to_rgb(step / 71, .5, .8)
            color = '#000000' if eink_enabled() else '#' + ''.join(f'{round(channel * 255):02x}' for channel in rgb)
            with self.spectrum.fill(color=color):
                self.spectrum.rect(step * width / 72, 0, width / 72 + 1, 6)
        self.spectrum.redraw()

    def save(self, widget=None, **kwargs):
        self._dragging = False
        try:
            self.app.preferences.save(accent_hue=str(self.hue.value),
                                      accent_saturation=str(self.saturation.value))
        except (OSError, ValueError) as error:
            self.set_values(float(self.app.preferences.values['accent_hue']),
                            float(self.app.preferences.values['accent_saturation']))
            self.app.settings_status.text = str(error)
            return
        set_accent(self.hue.value, self.saturation.value)
        refresh_appearance(self.app)
        self.preview_color()
        self.app.settings_status.text = 'Accent color saved on this device.'

    def set_values(self, hue, saturation):
        # Programmatic changes must not preview half of a restored pair.
        self.hue.on_change = self.saturation.on_change = None
        try:
            self.hue.value, self.saturation.value = hue, saturation
        finally:
            self.hue.on_change = self.saturation.on_change = self.changed
        self.preview_color()

    def reset(self, widget=None, **kwargs):
        self.set_values(*DEFAULT_ACCENT)
        self.save()
