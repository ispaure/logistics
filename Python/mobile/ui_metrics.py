"""Mobile design sizes use native points/sp, including explicit Pack fonts.

Install the font adapter before creating application widgets. Toga 0.5.7's
mobile backends use CSS points, multiplying explicit fonts by 96/72. Convert
once when a style reaches the native renderer; leave styles in design units.
Android's subsequent system sp scaling remains the backend's responsibility.
"""

from functools import wraps

from commonUtils.ui.native.text_size import native_backend

TOUCH_TARGET = 48
BODY_TEXT = 17
CONTROL_TEXT = 16
CAPTION_TEXT = 13


def install_font_units():
    """Adapt all explicit mobile widget fonts, including later style changes.

    This app-process adapter targets the pinned Toga style applicator, so shared
    and feature-owned widgets use the same convention without special imports.
    System default sizes, non-mobile backends, WebView CSS and direct native
    font APIs are unaffected. Repeated app/scene construction must not stack it.
    """
    from toga.fonts import Font, SYSTEM_DEFAULT_FONT_SIZE
    from toga.style import TogaApplicator

    original = TogaApplicator.set_font
    if getattr(original, '_logistics_native_font_units', False):
        return

    @wraps(original)
    def set_font(applicator, font):
        if (font.size != SYSTEM_DEFAULT_FONT_SIZE
                and native_backend(applicator.widget).startswith(('toga_iOS.', 'toga_android.'))):
            # Toga's Font requires integral CSS points. Round only here, after
            # layout and application code have retained their logical size.
            font = Font(font.family, max(1, round(font.size * 72 / 96)),
                        weight=font.weight, style=font.style, variant=font.variant)
        original(applicator, font)

    set_font._logistics_native_font_units = True
    TogaApplicator.set_font = set_font
