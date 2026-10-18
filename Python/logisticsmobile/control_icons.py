"""Named, compact controls using UIKit symbols and Android vector drawables."""
import weakref
import toga
from toga.style import Pack
from .appearance import accessible_name

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
    'compose': ('square.and.pencil', '✎', (((14, 4), (4, 4), (4, 20), (20, 20), (20, 10)), ((10, 14), (11, 10), (19, 2), (22, 5), (14, 13), (10, 14)))),
    'edit': ('pencil', '✎', (((4, 20), (5, 15), (17, 3), (21, 7), (9, 19), (4, 20)), ((14, 6), (18, 10)))),
    'view': ('doc.text', '▤', (((5, 3), (14, 3), (20, 9), (20, 21), (5, 21), (5, 3)), ((14, 3), (14, 9), (20, 9)), ((8, 13), (17, 13)), ((8, 17), (17, 17)))),
    'save': ('square.and.arrow.down', '↓', (((4, 13), (4, 21), (20, 21), (20, 13)), ((12, 2), (12, 16)), ((7, 11), (12, 16), (17, 11)))),
    'down': ('chevron.down', '⌄', (((5, 8), (12, 15), (19, 8)),)),
    'fullscreen': ('arrow.up.left.and.arrow.down.right', '⤢', (((10, 3), (3, 3), (3, 10)), ((3, 3), (10, 10)), ((14, 21), (21, 21), (21, 14)), ((21, 21), (14, 14)))),
    'speaker': ('speaker.wave.2', '🔊', (((3, 9), (7, 9), (12, 5), (12, 19), (7, 15), (3, 15), (3, 9)),
                                      ((16, 8), (18, 10), (18, 14), (16, 16)), ((19, 4), (22, 8), (23, 12), (22, 16), (19, 20)))),
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

_android_controls = weakref.WeakSet()

# One folder silhouette with an integrated lock; use the same geometry on both
# platforms rather than depending on an OS-specific locked-folder symbol.
_folder_outline = ((12, 20), (3, 20), (2, 19), (2, 6), (3, 5), (9, 5), (11, 8), (21, 8), (22, 9), (22, 10))
_folder_lock = ((15, 16), (22, 16), (23, 17), (23, 21), (22, 22), (15, 22), (14, 21), (14, 17), (15, 16))
_folder_shackle = ((16, 16), (16, 13), (16.6, 11.6), (18, 11), (20, 11), (21.4, 11.6), (22, 13))
# A short pair of links keeps the chained state legible without covering the face.
_folder_chains = (
    ((4, 11), (5, 10), (6, 10), (9, 13), (9, 14), (8, 15), (7, 15), (4, 12), (4, 11)),
    ((7, 14), (8, 13), (9, 13), (12, 16), (12, 17), (11, 18), (10, 18), (7, 15), (7, 14)),
)
# Lift the whole arch clear of the body on the open side, rather than just
# removing a short closing stroke from the closed padlock.
_folder_open_shackle = ((16, 16), (16, 12), (16.6, 10.6), (18, 10), (20, 10), (21.4, 10.6), (22, 12))
ICONS.update(
    folder=('folder', '▱', (((2, 20), (22, 20), (22, 8), (11, 8), (9, 5), (2, 5), (2, 20)),)),
    folder_locked=('folder', '▱⚿', (_folder_outline, *_folder_chains, _folder_lock, _folder_shackle + ((22, 16),))),
    folder_unlocked=('folder', '▱🔓', (_folder_outline, _folder_lock, _folder_open_shackle)),
)


def tint_android(impl):
    from android import R
    from android.content.res import ColorStateList
    from .palette import argb, android_palette, eink_enabled
    dark = impl.native.getResources().getConfiguration().uiMode & 0x30 == 0x20
    colors = android_palette(dark)
    if eink_enabled() and getattr(impl, '_surface_eink_selected', False):
        colors = dict(colors, text='#ffffff', muted='#ffffff')
    foreground = getattr(impl, '_surface_roles', ('', 'text', False))[1]
    impl._control_drawable.setTintList(ColorStateList(
        [[-R.attr.state_enabled], []],
        [argb(colors['muted']), argb(colors.get(foreground, colors['text']))]))


def refresh_icons():
    for impl in list(_android_controls):
        tint_android(impl)


def button_icons(button, icons):
    """Keep leading glyphs inside the same native hit target as the title."""
    button.leading_icons = tuple(icons)
    if not icons:
        return button
    backend = type(button._impl).__module__
    width = 28 * len(icons) - 4
    labels = ' · '.join(label for _, label in icons)
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass, Block, objc_id
        from toga_iOS.libs import UIGraphicsImageRenderer, CGSize, CGRect
        renderer = UIGraphicsImageRenderer.alloc().initWithSize(CGSize(width + 8, 24))
        configuration = ObjCClass('UIImageSymbolConfiguration').configurationWithPointSize(22, weight=5)
        images = [ObjCClass('UIImage').systemImageNamed(ICONS[name][0]).imageWithConfiguration(configuration)
                  for name, _ in icons]
        def draw(context):
            for index, image in enumerate(images):
                # Preserve each symbol's aspect ratio inside a shared icon cell.
                scale = min(24 / float(image.size.width), 24 / float(image.size.height))
                w, h = float(image.size.width) * scale, float(image.size.height) * scale
                image.drawInRect(CGRect((28 * index + (24 - w) / 2, (24 - h) / 2), (w, h)))
        image = renderer.imageWithActions(Block(draw, None, objc_id)).imageWithRenderingMode(2)
        native = button._impl.native
        native.setImage(image, forState=0)
        native.accessibilityHint = ' · '.join(filter(None, (getattr(button, 'description', ''), labels)))
    elif backend.startswith('toga_android.'):
        from android.graphics import Path, Paint
        from android.graphics.drawable import ShapeDrawable
        from android.graphics.drawable.shapes import PathShape
        path = Path()
        for index, (name, _) in enumerate(icons):
            for line in ICONS[name][2]:
                path.moveTo(line[0][0] + 28 * index, line[0][1])
                for x, y in line[1:]:
                    path.lineTo(x + 28 * index, y)
        drawable = ShapeDrawable(PathShape(path, width, 24))
        paint = drawable.getPaint()
        paint.setStyle(Paint.Style.STROKE)
        paint.setStrokeWidth(1.8)
        paint.setStrokeCap(Paint.Cap.ROUND)
        paint.setStrokeJoin(Paint.Join.ROUND)
        paint.setAntiAlias(True)
        native = button._impl.native
        density = native.getResources().getDisplayMetrics().density
        drawable.setBounds(0, 0, round(width * density), round(24 * density))
        native.setCompoundDrawablesRelative(drawable, None, None, None)
        native.setCompoundDrawablePadding(round(8 * density))
        native.setContentDescription(' · '.join(filter(None,
            (button.text, getattr(button, 'description', ''), labels))))
        button._impl._control_drawable = drawable
        _android_controls.add(button._impl)
        tint_android(button._impl)
    return button


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
        if name in {'group', 'obsidian', 'skip_back', 'skip_forward', 'folder_locked', 'folder_unlocked'}:
            from math import radians
            from rubicon.objc import Block, objc_id
            from toga_iOS.libs import UIGraphicsImageRenderer, CGSize, CGPoint, CGRect
            renderer = UIGraphicsImageRenderer.alloc().initWithSize(CGSize(24, 24))
            def draw(context):
                ObjCClass('UIColor').blackColor.setStroke()
                path = ObjCClass('UIBezierPath').bezierPath()
                skip = name.startswith('skip_')
                path.lineWidth = 1.6 if name.startswith('folder_') else 1.7 if skip else 1.8
                path.lineCapStyle = 1
                path.lineJoinStyle = 1
                if skip:
                    path.addArcWithCenter(CGPoint(12, 12), radius=9,
                        startAngle=radians(-50), endAngle=radians(-330), clockwise=False)
                for line in lines:
                    path.moveToPoint(CGPoint(*line[0]))
                    for point in line[1:]:
                        path.addLineToPoint(CGPoint(*point))
                path.stroke()
                if skip:
                    from rubicon.objc import ns_from_py
                    paragraph = ObjCClass('NSMutableParagraphStyle').alloc().init()
                    paragraph.alignment = 1
                    font = ObjCClass('UIFont').systemFontOfSize(10)
                    text = ObjCClass('NSString').stringWithString('15')
                    text.drawInRect(CGRect((3, (25 - float(font.lineHeight)) / 2), (18, float(font.lineHeight))),
                        withAttributes=ns_from_py({'NSFont': font,
                            'NSColor': ObjCClass('UIColor').blackColor, 'NSParagraphStyle': paragraph}))
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
            path.addArc(3, 3, 21, 21, -50, -280)
        elif name == 'more':
            for x in (5, 12, 19):
                path.addCircle(x, 12, 1, Path.Direction.CW)
        drawable = ShapeDrawable(PathShape(path, 24, 24))
        paint = drawable.getPaint()
        paint.setStyle(Paint.Style.FILL if name in {'stop', 'play'} else Paint.Style.STROKE)
        paint.setStrokeWidth(1.6 if name.startswith('folder_') else 1.8)
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
        if name in {'skip_back', 'skip_forward'}:
            from android.graphics import Bitmap, Canvas
            from android.graphics.drawable import BitmapDrawable
            bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
            canvas = Canvas(bitmap)
            canvas.scale(size / 24, size / 24)
            paint.setStrokeWidth(1.7)
            canvas.drawPath(path, paint)
            paint.setStyle(Paint.Style.FILL)
            paint.setTextSize(10)
            paint.setTextAlign(Paint.Align.CENTER)
            canvas.drawText('15', 12, 12.5 - (paint.ascent() + paint.descent()) / 2, paint)
            drawable = BitmapDrawable(native.getResources(), bitmap)
            drawable.setBounds(0, 0, size, size)
        native.setCompoundDrawablesRelative(drawable, None, None, None)
        button._impl._control_drawable = drawable
        _android_controls.add(button._impl)
        tint_android(button._impl)
    return button


def icon_button(name, label, *, on_press=None, enabled=True):
    from .appearance import surface
    return surface(apply_icon(toga.Button(on_press=on_press, enabled=enabled,
                                 style=Pack(width=48, height=48)), name, label),
                   background='transparent', foreground='text', outlined=True)
