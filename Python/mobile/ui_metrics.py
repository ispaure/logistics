"""Native logical sizes for workspace and file navigation.

Geometry uses UIKit points / Android dp. Explicit Toga fonts use CSS points;
both pinned mobile backends multiply those by 96/72. Keep that conversion at
the presentation boundary, rather than treating a Toga font as native sp/pt.
Android still applies the user's system font scale after this conversion.
"""

TOUCH_TARGET = 48
BODY_TEXT = 17
CONTROL_TEXT = 16
CAPTION_TEXT = 13


def toga_font_size(native_size):
    """Convert a native pt/sp design size to the pinned Toga font units."""
    # Pack accepts integer CSS points only; round instead of silently truncating.
    return round(native_size * 72 / 96)
