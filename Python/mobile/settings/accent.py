"""Native hue/saturation controls with transient preview and release-to-save."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from .forms import SettingsLabel
from ..appearance import accessible_name, surface, refresh_appearance
from ..palette import DEFAULT_ACCENT, accent_colors, set_accent
from ..reading.reader_progress import style_slider


class AccentControls(toga.Box):
    def __init__(self, app):
        super().__init__(style=Pack(direction=COLUMN, margin_bottom=20))
        self._settings_managed_content = True
        # Toga clears Widget.app when a cached category is detached.
        self._settings_app = app
        self._dragging = False
        self.add(SettingsLabel('Accent color', style=Pack(font_weight='bold', margin_bottom=12)))
        self.hue_label = SettingsLabel('Hue')
        self.hue = toga.Slider(min=0, max=359,
            value=float(app.preferences.values['accent_hue']), style=Pack(height=64))
        self.saturation_label = SettingsLabel('Saturation')
        self.saturation = toga.Slider(min=0, max=100,
            value=float(app.preferences.values['accent_saturation']), style=Pack(height=64))
        self.spectrum = toga.Canvas(on_resize=self.draw_spectrum, style=Pack(height=6, margin_top=8))
        self._spectrum_width = 100
        self.add(self.hue_label, self.spectrum, self.hue, self.saturation_label, self.saturation)
        for slider, name in ((self.hue, 'Accent hue'), (self.saturation, 'Accent saturation')):
            accessible_name(slider, name)
            slider._accent_thumb_extent = 32
            style_slider(slider)
            slider.on_press = self.begin_drag
            slider.on_change = self.changed
            slider.on_release = self.save
        self.add(surface(toga.Button('Reset to Default Accent Color', on_press=self.reset, style=Pack(height=48)),
                         foreground='accent'))
        self.preview_color()

    def update_labels(self):
        for label, text in ((self.hue_label, f'Hue · {self.hue.value:.0f}°'),
                            (self.saturation_label, f'Saturation · {self.saturation.value:.0f}%')):
            if label.text != text:
                label.text = text

    def preview_color(self, widget=None, **kwargs):
        self.update_labels()
        self.draw_spectrum(width=self._spectrum_width)
        light, dark = accent_colors(self.hue.value, self.saturation.value)
        # The filled tracks and thumbs preview the exact same opaque accent
        # as app controls, even before the saved app color changes.
        backend = type(self._settings_app._impl).__module__
        for slider in (self.hue, self.saturation):
            slider._accent_preview = (light, dark)
            if self._dragging and backend.startswith('toga_android.'):
                # Preserve the native thumb/track while SeekBar owns the gesture.
                from android.content.res import ColorStateList
                from ..palette import argb, android_palette, DARK, eink_enabled
                color = android_palette()['accent'] if eink_enabled() else dark if android_palette() is DARK else light
                tint = ColorStateList.valueOf(argb(color))
                slider._impl.native.setThumbTintList(tint)
                slider._impl.native.setProgressTintList(tint)
            else:
                style_slider(slider)

    def begin_drag(self, widget=None, **kwargs):
        self._dragging = True

    def changed(self, widget=None, **kwargs):
        self.preview_color()
        # VoiceOver, TalkBack and keyboard adjustments have no touch release.
        if not self._dragging:
            self.save()

    def draw_spectrum(self, widget=None, *, width, **kwargs):
        from ..palette import eink_enabled
        self._spectrum_width = width
        key = (width, self.saturation.value, eink_enabled())
        if getattr(self, '_spectrum_key', None) == key:
            return
        self._spectrum_key = key
        self.spectrum.root_state.drawing_actions.clear()
        for step in range(72):
            color = '#000000' if eink_enabled() else accent_colors((step * 360 / 71) % 360,
                self.saturation.value)[0]
            with self.spectrum.fill(color=color):
                self.spectrum.rect(step * width / 72, 0, width / 72 + 1, 6)
        self.spectrum.redraw()

    def save(self, widget=None, **kwargs):
        self._dragging = False
        try:
            self._settings_app.preferences.save(accent_hue=str(self.hue.value),
                                      accent_saturation=str(self.saturation.value))
        except (OSError, ValueError) as error:
            self.set_values(float(self._settings_app.preferences.values['accent_hue']),
                            float(self._settings_app.preferences.values['accent_saturation']))
            self._settings_app.settings_status.text = str(error)
            return
        set_accent(self.hue.value, self.saturation.value)
        refresh_appearance(self._settings_app)
        self.preview_color()
        self._settings_app.settings_status.text = ''

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
