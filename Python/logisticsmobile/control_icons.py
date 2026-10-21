"""Named, compact controls using UIKit symbols and Android vector drawables."""
from commonUtils.ui.native.icons import IconRenderer, IconSpec
import toga
from toga.style import Pack

# Paths use a shared 24-point grid. Keep the fallback readable on desktop/test hosts.
ICONS = {
    'folder_hub': ('folder', '▱', (((3, 6), (9, 6), (11, 9), (21, 9), (21, 20), (3, 20), (3, 6)),)),
    'books': ('books.vertical', '▥', (((3, 4), (8, 4), (8, 21), (3, 21), (3, 4)),
                                     ((10, 4), (15, 4), (15, 21), (10, 21), (10, 4)),
                                     ((17, 5), (21, 4), (24, 20), (20, 21), (17, 5)))),
    'group': ('list.bullet.indent', '⑂', (
        ((4, 2), (10, 2), (10, 8), (4, 8), (4, 2)),
        ((7, 8), (7, 20), (15, 20)), ((7, 12), (15, 12)),
        ((15, 9), (21, 9), (21, 15), (15, 15), (15, 9)),
        ((15, 17), (21, 17), (21, 23), (15, 23), (15, 17)))),
    'obsidian': ('diamond', '◈', (((13, 2), (20, 7), (18, 18), (10, 23), (4, 17), (5, 8), (13, 2)),
                               ((13, 2), (10, 10), (4, 17)), ((20, 7), (10, 10), (18, 18)), ((10, 10), (10, 23)))),
    'storage_remote': ('cloud', '☁', (((6, 18), (3, 17), (2, 14), (3, 11), (6, 10), (7, 6), (11, 4), (15, 5), (17, 9), (20, 10), (22, 13), (21, 17), (18, 18), (6, 18)),)),
    'storage_local': ('internaldrive', '▣', (((5, 5), (19, 5), (22, 15), (22, 20), (2, 20), (2, 15), (5, 5)), ((2, 15), (22, 15)), ((16, 18), (19, 18)))),
    'storage_crypt': ('lock', '⚿', (((5, 10), (19, 10), (19, 21), (5, 21), (5, 10)), ((8, 10), (8, 6), (9, 3), (15, 3), (16, 6), (16, 10)), ((12, 14), (12, 17)))),
    'storage_unlocked': ('lock.open', '🔓', (((5, 10), (19, 10), (19, 21), (5, 21), (5, 10)), ((8, 10), (8, 6), (9, 3), (15, 3), (16, 6)), ((12, 14), (12, 17)))),
    'back': ('chevron.left', '‹', (((15, 5), (8, 12), (15, 19)),)),
    'forward': ('chevron.right', '›', (((9, 5), (16, 12), (9, 19)),)),
    'previous_comic': ('backward.end', '|≪', (((4, 5), (4, 19)), ((13, 5), (7, 12), (13, 19)), ((21, 5), (15, 12), (21, 19)))),
    'next_comic': ('forward.end', '≫|', (((20, 5), (20, 19)), ((3, 5), (9, 12), (3, 19)), ((11, 5), (17, 12), (11, 19)))),
    'up': ('arrow.up', '↑', (((5, 11), (12, 4), (19, 11)), ((12, 4), (12, 21)))),
    'find': ('magnifyingglass', '⌕', (((15, 15), (21, 21)),)),
    'contents': ('list.bullet', '≡', tuple(((7, y), (21, y)) for y in (6, 12, 18))),
    'appearance': ('textformat.size', 'Aa', (((3, 19), (9, 5), (15, 19)), ((5, 14), (13, 14)), ((16, 19), (19, 12), (22, 19)), ((17, 17), (21, 17)))),
    'more': ('ellipsis', '•••', ()),
    'overflow': ('ellipsis.circle', '⋮', ()),
    'compose': ('square.and.pencil', '✎', (((14, 4), (4, 4), (4, 20), (20, 20), (20, 10)), ((10, 14), (11, 10), (19, 2), (22, 5), (14, 13), (10, 14)))),
    'edit': ('pencil', '✎', (((4, 20), (5, 15), (17, 3), (21, 7), (9, 19), (4, 20)), ((14, 6), (18, 10)))),
    'view': ('doc.text', '▤', (((5, 3), (14, 3), (20, 9), (20, 21), (5, 21), (5, 3)), ((14, 3), (14, 9), (20, 9)), ((8, 13), (17, 13)), ((8, 17), (17, 17)))),
    'save': ('square.and.arrow.down', '↓', (((4, 13), (4, 21), (20, 21), (20, 13)), ((12, 2), (12, 16)), ((7, 11), (12, 16), (17, 11)))),
    'down': ('chevron.down', '⌄', (((5, 8), (12, 15), (19, 8)),)),
    'fullscreen': ('arrow.up.left.and.arrow.down.right', '⤢', (((10, 3), (3, 3), (3, 10)), ((3, 3), (10, 10)), ((14, 21), (21, 21), (21, 14)), ((21, 21), (14, 14)))),
    'fit': ('arrow.down.right.and.arrow.up.left', 'Fit', (((3, 3), (10, 10)), ((4, 10), (10, 10), (10, 4)), ((21, 21), (14, 14)), ((14, 20), (14, 14), (20, 14)))),
    'speaker': ('speaker.wave.2', '🔊', (((3, 9), (7, 9), (12, 5), (12, 19), (7, 15), (3, 15), (3, 9)),
                                      ((16, 8), (18, 10), (18, 14), (16, 16)), ((19, 4), (22, 8), (23, 12), (22, 16), (19, 20)))),
    'reset': ('arrow.counterclockwise', '↺', (((4, 9), (7, 5), (13, 3), (19, 6), (21, 12), (19, 18), (13, 21), (7, 19)), ((4, 3), (4, 9), (10, 9)))),
    'play': ('play.fill', '▶', (((7, 4), (20, 12), (7, 20), (7, 4)),)),
    'pause': ('pause.fill', 'Ⅱ', (((8, 4), (8, 20)), ((16, 4), (16, 20)))),
    # Match commonUtils.ui.readers.reader_chrome.ReaderIcon's back15/forward15:
    # 18-point circular arc, direction arrow, and a centred 10-point "15".
    'skip_back': ('gobackward.15', '↶15', (((8, 2), (3, 5), (7, 8)),)),
    'skip_forward': ('goforward.15', '15↷', (((16, 2), (21, 5), (17, 8)),)),
    'stop': ('stop.fill', '■', (((6, 6), (18, 6), (18, 18), (6, 18), (6, 6)),)),
    'close': ('xmark', '×', (((6, 6), (18, 18)), ((18, 6), (6, 18)))),
}
# Settings categories use recognizable symbols rather than unrelated commands.
_settings_circle = ((12, 2), (17, 3.3), (20.7, 7), (22, 12), (20.7, 17),
                    (17, 20.7), (12, 22), (7, 20.7), (3.3, 17), (2, 12),
                    (3.3, 7), (7, 3.3), (12, 2))
ICONS.update(
    preferences=('slider.horizontal.3', '☷', (((3, 6), (21, 6)), ((3, 12), (21, 12)),
                  ((3, 18), (21, 18)), ((8, 3), (8, 9)), ((16, 9), (16, 15)), ((8, 15), (8, 21)))),
    chat=('bubble.left.and.bubble.right', '☏', (((3, 3), (18, 3), (18, 14), (9, 14), (4, 19), (4, 14), (3, 14), (3, 3)),
          ((18, 8), (22, 8), (22, 19), (20, 19), (20, 22), (16, 19), (11, 19)))),
    help=('questionmark.circle', '?', (_settings_circle, ((8, 8), (9, 6), (14, 6), (16, 8), (16, 10), (12, 13), (12, 14)), ((12, 17), (12, 18)))),
    info=('info.circle', 'ⓘ', (_settings_circle, ((12, 10), (12, 18)), ((12, 6), (12, 7)))),
)


# One folder silhouette with an integrated lock; use the same geometry on both
# platforms rather than depending on an OS-specific locked-folder symbol.
from services.folders.appearance import FOLDER_FILLS, FOLDER_PATHS, FOLDER_STROKE_WIDTH
ICONS.update((name, ('folder', {'folder_locked': '▱⚿', 'folder_unlocked': '▱🔓'}.get(name, '▱'), paths))
             for name, paths in FOLDER_PATHS.items())


def tint_android(impl):
    from commonUtils.ui.native.appearance import android_color_states
    from .palette import argb, android_palette, eink_enabled
    dark = impl.native.getResources().getConfiguration().uiMode & 0x30 == 0x20
    colors = android_palette(dark)
    if eink_enabled() and getattr(impl, '_surface_eink_selected', False):
        colors = dict(colors, text='#ffffff', muted='#ffffff')
    foreground = getattr(impl, '_surface_roles', ('', 'text', False))[1]
    disabled, enabled = argb(colors['muted']), argb(colors.get(foreground, colors['text']))
    key = (disabled, enabled)
    if (getattr(impl, '_control_tint_drawable', None) is impl._control_drawable
            and getattr(impl, '_control_tint_key', None) == key):
        return
    impl._control_drawable.setTintList(android_color_states(disabled, enabled))
    impl._control_tint_drawable, impl._control_tint_key = impl._control_drawable, key


def _spec(name, artwork):
    symbol, fallback, lines = artwork
    skip = name in {'skip_back', 'skip_forward'}
    circles = ((10, 10, 6),) if name == 'find' else tuple((3, y, .6) for y in (6, 12, 18)) if name == 'contents' else tuple((x, 12, 1) for x in (5, 12, 19)) if name == 'more' else tuple((12, y, 1) for y in (5, 12, 19)) if name == 'overflow' else ()
    return IconSpec(symbol, fallback, lines, circles=circles,
        arcs=((3, 3, 21, 21, -50, -280),) if skip else (),
        fills=FOLDER_FILLS.get(name, ()),
        stroke_width=FOLDER_STROKE_WIDTH if name in FOLDER_PATHS else 1.7 if skip else 1.8,
        filled=name in {'stop', 'play'}, text='15' if skip else None,
        apple_vector=name in {'group', 'obsidian'} or skip or name in FOLDER_PATHS)


_renderer = IconRenderer({name: _spec(name, value) for name, value in ICONS.items()}, tint_android=tint_android)
refresh_icons = _renderer.refresh
button_icons = _renderer.leading
apply_icon = _renderer.apply


def icon_button(name, label, *, on_press=None, enabled=True):
    from .appearance import surface
    return surface(apply_icon(toga.Button(on_press=on_press, enabled=enabled,
                                 style=Pack(width=48, height=48)), name, label),
                   background='surface', foreground='text', outlined=False)
