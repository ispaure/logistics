"""Logistics slider palette, explicit reading direction and live refresh registry."""
import weakref
from commonUtils.ui.native.sliders import style_slider as native_style_slider
from .appearance import apple_color
from .palette import android_palette

_sliders = weakref.WeakSet()


def refresh_progress():
    for slider in list(_sliders):
        style_slider(slider)


def style_slider(slider):
    _sliders.add(slider)
    # Manga reverses values explicitly; do not also reverse the native track.
    native_style_slider(slider, apple_color=apple_color, palette=android_palette, force_ltr=True)
