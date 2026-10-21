"""Slim native reader tracks and circular thumbs with full-size touch areas."""
import weakref

_sliders = weakref.WeakSet()


def refresh_progress():
    for slider in list(_sliders):
        style_slider(slider)


def style_slider(slider):
    _sliders.add(slider)
    backend = type(slider._impl).__module__
    if backend.startswith('toga_iOS.'):
        _apple(slider._impl.native)
    elif backend.startswith('toga_android.'):
        _android(slider._impl.native)


def _apple(native):
    from rubicon.objc import ObjCClass, Block, objc_id, UIEdgeInsets
    from toga_iOS.libs import UIGraphicsImageRenderer, CGSize, CGRect
    from .appearance import apple_color

    def image(size, role, *, circle=False):
        renderer = UIGraphicsImageRenderer.alloc().initWithSize(CGSize(size, size))
        def draw(context):
            apple_color(role).setFill()
            rect = CGRect((0, 0), (size, size))
            path = (ObjCClass('UIBezierPath').bezierPathWithOvalInRect(rect) if circle else
                    ObjCClass('UIBezierPath').bezierPathWithRoundedRect(rect, cornerRadius=size / 2))
            path.fill()
        return renderer.imageWithActions(Block(draw, None, objc_id))

    native.semanticContentAttribute = 3  # Manga reverses values explicitly.
    native.setMinimumTrackImage(image(4, 'accent').resizableImageWithCapInsets(UIEdgeInsets(0, 1, 0, 1), resizingMode=1), forState=0)
    native.setMaximumTrackImage(image(4, 'border').resizableImageWithCapInsets(UIEdgeInsets(0, 1, 0, 1), resizingMode=1), forState=0)
    native.setThumbImage(image(16, 'accent', circle=True), forState=0)


def _android(native):
    from android import R
    from android.graphics import Color
    from android.graphics.drawable import GradientDrawable, LayerDrawable, ClipDrawable
    from android.view import Gravity
    from .palette import android_palette
    density = native.getResources().getDisplayMetrics().density
    dark = native.getResources().getConfiguration().uiMode & 0x30 == 0x20
    colors = android_palette(dark)
    def dp(value):
        return round(value * density)
    def shape(role, *, circle=False):
        drawable = GradientDrawable()
        drawable.setColor(Color.parseColor(colors[role]))
        drawable.setShape(GradientDrawable.OVAL if circle else GradientDrawable.RECTANGLE)
        if circle:
            drawable.setSize(dp(16), dp(16))
        else:
            drawable.setCornerRadius(dp(2))
        return drawable
    track = LayerDrawable([shape('border'), ClipDrawable(shape('accent'), Gravity.LEFT, ClipDrawable.HORIZONTAL)])
    for index, identifier in enumerate((R.id.background, R.id.progress)):
        track.setId(index, identifier)
        track.setLayerHeight(index, dp(4))
        track.setLayerGravity(index, Gravity.CENTER_VERTICAL)
    native.setLayoutDirection(0)
    native.setProgressTintList(None)
    native.setProgressBackgroundTintList(None)
    native.setThumbTintList(None)
    native.setProgressDrawable(track)
    native.setThumb(shape('accent', circle=True))
    native.setThumbOffset(dp(8))
    native.setSplitTrack(False)
    native.setPadding(dp(8), 0, dp(8), 0)
