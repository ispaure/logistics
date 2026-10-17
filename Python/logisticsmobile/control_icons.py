"""Named, compact controls using UIKit symbols and Android vector drawables."""
import weakref
import toga
from toga.style import Pack
from .appearance import accessible_name

# Paths use a shared 24-point grid. Keep the fallback readable on desktop/test hosts.
ICONS = {
    'obsidian': ('diamond', '◈', (((13, 2), (20, 7), (18, 18), (10, 23), (4, 17), (5, 8), (13, 2)),
                               ((13, 2), (10, 10), (4, 17)), ((20, 7), (10, 10), (18, 18)), ((10, 10), (10, 23)))),
    'storage_remote': ('cloud', '☁', (((6, 18), (3, 17), (2, 14), (3, 11), (6, 10), (7, 6), (11, 4), (15, 5), (17, 9), (20, 10), (22, 13), (21, 17), (18, 18), (6, 18)),)),
    'storage_local': ('internaldrive', '▣', (((5, 5), (19, 5), (22, 15), (22, 20), (2, 20), (2, 15), (5, 5)), ((2, 15), (22, 15)), ((16, 18), (19, 18)))),
    'storage_crypt': ('lock', '⚿', (((5, 10), (19, 10), (19, 21), (5, 21), (5, 10)), ((8, 10), (8, 6), (9, 3), (15, 3), (16, 6), (16, 10)), ((12, 14), (12, 17)))),
    'back': ('chevron.left', '‹', (((15, 5), (8, 12), (15, 19)),)),
    'forward': ('chevron.right', '›', (((9, 5), (16, 12), (9, 19)),)),
    'previous_comic': ('backward.end', '|≪', (((4, 5), (4, 19)), ((13, 5), (7, 12), (13, 19)), ((21, 5), (15, 12), (21, 19)))),
    'next_comic': ('forward.end', '≫|', (((20, 5), (20, 19)), ((3, 5), (9, 12), (3, 19)), ((11, 5), (17, 12), (11, 19)))),
    'up': ('arrow.up', '↑', (((5, 11), (12, 4), (19, 11)), ((12, 4), (12, 21)))),
    'find': ('magnifyingglass', '⌕', (((15, 15), (21, 21)),)),
    'contents': ('list.bullet', '≡', tuple(((7, y), (21, y)) for y in (6, 12, 18))),
    'appearance': ('textformat.size', 'Aa', (((3, 19), (9, 5), (15, 19)), ((5, 14), (13, 14)), ((16, 19), (19, 12), (22, 19)), ((17, 17), (21, 17)))),
    'more': ('ellipsis', '•••', ()),
    'compose': ('square.and.pencil', '✎', (((14, 4), (4, 4), (4, 20), (20, 20), (20, 10)), ((10, 14), (11, 10), (19, 2), (22, 5), (14, 13), (10, 14)))),
    'down': ('chevron.down', '⌄', (((5, 8), (12, 15), (19, 8)),)),
    'fullscreen': ('arrow.up.left.and.arrow.down.right', '⤢', (((10, 3), (3, 3), (3, 10)), ((3, 3), (10, 10)), ((14, 21), (21, 21), (21, 14)), ((21, 21), (14, 14)))),
    'speaker': ('speaker.wave.2', '🔊', (((3, 9), (7, 9), (12, 5), (12, 19), (7, 15), (3, 15), (3, 9)),
                                      ((16, 8), (18, 10), (18, 14), (16, 16)), ((19, 4), (22, 8), (23, 12), (22, 16), (19, 20)))),
    'play': ('play.fill', '▶', (((7, 4), (20, 12), (7, 20), (7, 4)),)),
    'pause': ('pause.fill', 'Ⅱ', (((8, 4), (8, 20)), ((16, 4), (16, 20)))),
    'skip_back': ('gobackward.15', '↶15', (((8, 3), (3, 7), (8, 11)), ((3, 7), (14, 7), (20, 12), (18, 20), (9, 22)))),
    'skip_forward': ('goforward.15', '15↷', (((16, 3), (21, 7), (16, 11)), ((21, 7), (10, 7), (4, 12), (6, 20), (15, 22)))),
    'stop': ('stop.fill', '■', (((6, 6), (18, 6), (18, 18), (6, 18), (6, 6)),)),
    'close': ('xmark', '×', (((6, 6), (18, 18)), ((18, 6), (6, 18)))),
}
_android_controls = weakref.WeakSet()


def tint_android(impl):
    from android import R
    from android.content.res import ColorStateList
    from .palette import argb, android_palette
    dark = impl.native.getResources().getConfiguration().uiMode & 0x30 == 0x20
    colors = android_palette(dark)
    foreground = getattr(impl, '_surface_roles', ('', 'text', False))[1]
    impl._control_drawable.setTintList(ColorStateList(
        [[-R.attr.state_enabled], []],
        [argb(colors['muted']), argb(colors.get(foreground, colors['text']))]))


def refresh_icons():
    for impl in list(_android_controls):
        tint_android(impl)


def apply_icon(button, name, label):
    """Preserve callbacks, enabled state and native menus on an existing button."""
    symbol, fallback, lines = ICONS[name]
    button.text = fallback
    button.style.width = button.style.height = 48
    button.control_icon = name
    accessible_name(button, label)
    backend = type(button._impl).__module__
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        button.text = ''
        image = ObjCClass('UIImage').systemImageNamed(symbol)
        if name == 'obsidian':
            from rubicon.objc import Block, objc_id
            from toga_iOS.libs import UIGraphicsImageRenderer, CGSize, CGPoint
            renderer = UIGraphicsImageRenderer.alloc().initWithSize(CGSize(24, 24))
            def draw(context):
                ObjCClass('UIColor').blackColor.setStroke()
                path = ObjCClass('UIBezierPath').bezierPath()
                path.lineWidth = 1.8
                path.lineJoinStyle = 1
                for line in lines:
                    path.moveToPoint(CGPoint(*line[0]))
                    for point in line[1:]:
                        path.addLineToPoint(CGPoint(*point))
                path.stroke()
            image = renderer.imageWithActions(Block(draw, None, objc_id)).imageWithRenderingMode(2)
        config = ObjCClass('UIImageSymbolConfiguration').configurationWithPointSize(22, weight=5)
        button._impl.native.setImage(image, forState=0)
        button._impl.native.setPreferredSymbolConfiguration(config, forImageInState=0)
    elif backend.startswith('toga_android.'):
        from android.graphics import Path, Paint
        from android.graphics.drawable import ShapeDrawable
        from android.graphics.drawable.shapes import PathShape
        path = Path()
        for line in lines:
            path.moveTo(*line[0])
            for point in line[1:]:
                path.lineTo(*point)
        if name == 'find':
            path.addCircle(10, 10, 6, Path.Direction.CW)
        elif name == 'contents':
            for y in (6, 12, 18):
                path.addCircle(3, y, .6, Path.Direction.CW)
        elif name in {'skip_back', 'skip_forward'}:
            path.moveTo(9, 13);path.lineTo(10, 12);path.lineTo(10, 18)
            path.moveTo(16, 12);path.lineTo(13, 12);path.lineTo(13, 15);path.lineTo(16, 15);path.lineTo(16, 18);path.lineTo(13, 18)
        elif name == 'more':
            for x in (5, 12, 19):
                path.addCircle(x, 12, 1, Path.Direction.CW)
        drawable = ShapeDrawable(PathShape(path, 24, 24))
        paint = drawable.getPaint()
        paint.setStyle(Paint.Style.FILL if name in {'stop', 'play'} else Paint.Style.STROKE)
        paint.setStrokeWidth(1.8)
        paint.setStrokeCap(Paint.Cap.ROUND)
        paint.setStrokeJoin(Paint.Join.ROUND)
        paint.setAntiAlias(True)
        native = button._impl.native
        density = native.getResources().getDisplayMetrics().density
        size, padding = round(24 * density), round(12 * density)
        drawable.setBounds(0, 0, size, size)
        button.text = ''
        native.setMinimumWidth(0)
        native.setMinimumHeight(0)
        native.setPadding(padding, padding, padding, padding)
        native.setCompoundDrawablesRelative(drawable, None, None, None)
        button._impl._control_drawable = drawable
        _android_controls.add(button._impl)
        tint_android(button._impl)
    return button


def icon_button(name, label, *, on_press=None, enabled=True):
    return apply_icon(toga.Button(on_press=on_press, enabled=enabled,
                                 style=Pack(width=48, height=48)), name, label)
