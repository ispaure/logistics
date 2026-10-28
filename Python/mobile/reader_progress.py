"""Logistics slider palette, explicit reading direction and live refresh registry."""
import weakref
import toga
from commonUtils.ui.native.sliders import style_slider as native_style_slider
from .appearance import apple_color
from .palette import android_palette

_sliders = weakref.WeakSet()


def refresh_progress():
    for slider in list(_sliders):
        style_slider(slider)


def style_slider(slider):
    _sliders.add(slider)
    if isinstance(slider, VerticalPageSlider):
        slider.paint_track()
        return
    # Manga reverses values explicitly; do not also reverse the native track.
    native_style_slider(slider, apple_color=apple_color, palette=android_palette, force_ltr=True,
                        reverse_fill=getattr(slider, '_reading_reverse_fill', False))


class VerticalPageSlider(toga.Canvas):
    """Top-to-bottom page scrubbing with the same release contract as Slider."""
    def __init__(self, *, on_release, **kwargs):
        self.min, self.max = 0, 1
        self._value = 0
        self._height, self._width = 100, 44
        self.commit = on_release
        super().__init__(on_resize=self.resize_track, on_press=self.drag_track,
                         on_drag=self.drag_track, on_release=self.release_track, **kwargs)
        _sliders.add(self)
        self.paint_track()

    @property
    def enabled(self):
        # Toga Canvas is always enabled. Keep the slider contract explicitly
        # so its event handlers and PageFooter can reject disabled scrubs.
        return getattr(self, '_reading_enabled', True)

    @enabled.setter
    def enabled(self, value):
        self._reading_enabled = bool(value)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = min(self.max, max(self.min, value))
        self.paint_track()

    def resize_track(self, widget, width, height, **kwargs):
        self._width, self._height = width, height
        self.paint_track()

    def drag_track(self, widget, x, y, **kwargs):
        if self.enabled:
            fraction = min(1, max(0, (y - 12) / max(1, self._height - 24)))
            self.value = self.min + fraction * (self.max - self.min)

    async def release_track(self, widget, x, y, **kwargs):
        if self.enabled:
            self.drag_track(widget, x, y)
            await self.commit(self)

    def paint_track(self):
        self.root_state.drawing_actions.clear()
        from .palette import android_palette
        backend = type(self._impl).__module__
        dark = False
        if backend.startswith('toga_iOS.'):
            dark = self._impl.native.traitCollection.userInterfaceStyle == 2
        elif backend.startswith('toga_android.'):
            dark = self._impl.native.getResources().getConfiguration().uiMode & 0x30 == 0x20
        colors = android_palette(dark)
        x = self._width / 2
        length = max(1, self._height - 24)
        y = 12 + length * (self.value - self.min) / max(1, self.max - self.min)
        with self.fill(color=colors['border']):
            self.rect(x - 2, 12, 4, length)
        with self.fill(color=colors['accent']):
            self.rect(x - 2, 12, 4, y - 12)
            self.ellipse(x, y, 8, 8)
        self.redraw()
