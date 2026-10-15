"""Logistics Slate roles, independent of Qt and native widget imports.

Matches the desktop Slate defaults (including its 6% blue dark tint). Light
cards use a near-white surface so large mobile screens avoid a stark white fill.
"""
LIGHT = dict(window='#f0f2f6', surface='#fafbfc', alternate='#f5f7fa',
             text='#202838', muted='#606b7c', border='#c5cedb', accent='#2563eb', hover='#e3eaf7')
DARK = dict(window='#23262c', surface='#2d3035', alternate='#34373c',
            text='#eef1f7', muted='#a6b0c0', border='#52555a', accent='#75a7ff', hover='#3d4045')


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
