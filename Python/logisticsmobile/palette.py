"""Logistics Slate roles, independent of Qt and native widget imports.

Matches the desktop Slate defaults (including its 6% blue dark tint). Light
cards use a near-white surface so large mobile screens avoid a stark white fill.
"""
LIGHT = dict(window='#f0f2f6', surface='#fafbfc', alternate='#f5f7fa',
             text='#202838', muted='#606b7c', border='#c5cedb', primary='#2563eb', accent='#2563eb', hover='#e3eaf7')
DARK = dict(window='#23262c', surface='#2d3035', alternate='#34373c',
            text='#eef1f7', muted='#a6b0c0', border='#52555a', primary='#2563eb', accent='#75a7ff', hover='#3d4045')
LIGHT.update(control_border='#7b8493', destructive='#c62828')
DARK.update(control_border='#858c99', destructive='#ff8a80')
LIGHT.update(tree_guide='#a8b2c1')
DARK.update(tree_guide='#737f90')

# Blue/orange plus open/closed lock shapes keep folder states distinguishable
# with red-green colour deficiencies. Both roles follow native appearance.
from services.folders.appearance import LOCK_LIGHT, LOCK_DARK
LIGHT.update(LOCK_LIGHT)
DARK.update(LOCK_DARK)


# Chat uses neutral layers like the conversation drawer, independent of Slate's
# blue tint elsewhere. Keep a light counterpart and dynamic platform colours.
LIGHT.update(chat_background='#ffffff', chat_panel='#f7f7f7', chat_selected='#e9e9e9',
             chat_input='#f0f0f0', chat_bubble='#e9e9e9', chat_primary='#202020', chat_on_primary='#ffffff')
DARK.update(chat_background='#000000', chat_panel='#141414', chat_selected='#222222',
            chat_input='#141414', chat_bubble='#353535', chat_primary='#f3f3f3', chat_on_primary='#111111')


# Grouped settings share the surrounding app palette at every appearance.
for colors in (LIGHT, DARK):
    colors.update(settings_background=colors['window'], settings_group=colors['surface'],
                  settings_separator=colors['border'])


def argb(value):
    value = 0xff000000 | int(value.lstrip('#'), 16)
    return value - 2**32


def css_variables(mode='system'):
    if mode not in ('system', 'light', 'dark'):
        raise ValueError('Unknown appearance mode.')
    def variables(colors):
        return ';'.join(f'--{key}:{value}' for key, value in colors.items())
    base = (':root{color-scheme:' + ('light dark' if mode == 'system' else mode) + ';'
            + variables(DARK if mode == 'dark' else LIGHT) + '}')
    return base + ('@media(prefers-color-scheme:dark){:root{' + variables(DARK) + '}}'
                   if mode == 'system' else '')


def themed_chapter(content, mode):
    """Style the sanitized chapter without changing its offline content policy."""
    return content.replace('</style>', css_variables(mode)
        + 'body{background:var(--surface);color:var(--text)}</style>', 1)


EINK = dict(window='#ffffff', surface='#ffffff', alternate='#ffffff',
            text='#000000', muted='#000000', border='#000000',
            primary='#000000', accent='#000000', hover='#ffffff')
EINK.update(folder='#000000', folder_unlocked='#000000', folder_locked='#000000')
EINK.update(settings_background='#ffffff', settings_group='#ffffff', settings_separator='#000000')
EINK.update(control_border='#000000', destructive='#000000')
EINK.update(tree_guide='#000000')
_eink_enabled = False


def set_eink_enabled(enabled):
    global _eink_enabled
    _eink_enabled = bool(enabled)


def eink_enabled():
    return _eink_enabled


def android_palette(dark=False):
    return EINK if eink_enabled() else DARK if dark else LIGHT


EINK_CSS = (':root{color-scheme:light!important}'
    'html,body,body *:not(img):not(svg):not(svg *){background-color:#fff!important;color:#000!important;'
    'text-shadow:none!important;box-shadow:none!important;animation:none!important;transition:none!important}'
    'a{text-decoration:underline!important}button,input,textarea,select{border:1px solid #000!important}'
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
