"""Native palette adaptation over shared Logistics appearance policy."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from functools import partial
from services import appearance_palette
from services.appearance_palette import (
    MOBILE_LIGHT as LIGHT, MOBILE_DARK as DARK, EINK, argb, DEFAULT_ACCENT, validate_accent,
    set_accent, set_eink_enabled, eink_enabled,
)

accent_colors = partial(appearance_palette.accent_colors, mobile=True)
css_variables = partial(appearance_palette.css_variables, mobile=True)
themed_chapter = partial(appearance_palette.themed_chapter, mobile=True)


# Android wraps controls in themed contexts. On older AppCompat versions
# those wrappers can keep the configuration they had at construction.
_android_system_dark = None


def set_android_system_dark(dark):
    global _android_system_dark
    _android_system_dark = dark


def android_palette(dark=False):
    if _android_system_dark is not None:
        dark = _android_system_dark
    return EINK if eink_enabled() else DARK if dark else LIGHT


EINK_CSS = (':root{color-scheme:light!important}'
    'html,body,body *:not(canvas):not(img):not(svg):not(svg *){background-color:#fff!important;color:#000!important;'
    'text-shadow:none!important;box-shadow:none!important;animation:none!important;transition:none!important}'
    'a{text-decoration:underline!important}button:not([role=menuitem]),input,textarea,select{border:1px solid #000!important}'
    '::selection{background:#000!important;color:#fff!important}')


def eink_html(content):
    """Add reversible presentation CSS without altering document pixels or data."""
    if not eink_enabled():
        return content
    style = '<style id="logistics-eink">' + EINK_CSS + '</style>'
    if '</head>' in content:
        return content.replace('</head>', style + '</head>', 1)
    return style + content


def eink_script():
    import json
    return ('(()=>{const old=document.getElementById("logistics-eink");if(old)old.remove();'
        + ('const style=document.createElement("style");style.id="logistics-eink";style.textContent='
           + json.dumps(EINK_CSS) + ';(document.head||document.documentElement).appendChild(style);' if eink_enabled() else '')
        + '})()')
