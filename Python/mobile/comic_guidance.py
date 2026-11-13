"""Passive native comic cue, drawn by the app outside image/export surfaces."""
import weakref

# Original vector outline: a raised index finger and curled hand, in 56 × 64 points.
# Native drawing avoids artwork downloads, emoji/font differences and page pixels.
HAND = (
    ('M', 20, 60), ('L', 9, 44), ('C', 3, 36, 8, 30, 14, 35), ('L', 20, 41),
    ('L', 20, 9), ('C', 20, 1, 30, 1, 30, 9), ('L', 30, 28),
    ('C', 30, 22, 39, 22, 39, 29), ('L', 39, 32),
    ('C', 39, 26, 48, 27, 48, 34), ('L', 48, 37),
    ('C', 50, 33, 54, 35, 53, 42), ('L', 51, 51),
    ('C', 50, 56, 46, 58, 46, 61), ('L', 20, 61),
)
STROKE_SECONDS = .95


def reduced_motion(app):
    if getattr(getattr(app, 'preferences', None), 'values', {}).get('android_eink') == 'true':
        return True
    backend = type(app._impl).__module__
    if backend.startswith('toga_iOS.'):
        from ctypes import CDLL, c_bool
        query = CDLL(None).UIAccessibilityIsReduceMotionEnabled
        query.restype = c_bool
        return bool(query())
    if backend.startswith('toga_android.'):
        from android.provider import Settings
        return Settings.Global.getFloat(app._impl.native.getContentResolver(),
                                        Settings.Global.ANIMATOR_DURATION_SCALE, 1.0) == 0
    return True


def cue_layout(width, height, volume, movement):
    """Frames stay within the reading pane; the volume line has its own bottom row."""
    width, height = max(1, width), max(1, height)
    card_width = min(340, max(1, width - 16))
    bottom_height = min(64, height / 3) if volume else 0
    card_height = min(152 if movement else 80, max(1, height - bottom_height - 24))
    left = (width - card_width) / 2
    card = (left, max(8, (height - bottom_height - card_height) / 2), card_width, card_height)
    bottom = (left, max(0, height - bottom_height - 8), card_width, bottom_height)
    _, _, _, start, end, _ = cue_contents(card_width, card_height, movement)
    return card, bottom, start, end


def cue_contents(width, height, movement):
    if not movement:
        return (8, 4, width - 16, height - 8), None, None, 0, 0, 16
    # Shallow landscape/fold panes use text beside the demonstration, so fixed
    # vertical rows cannot collide with one another or the separate volume line.
    compact = height < 140
    lane_x, lane_width = (width * .55, width * .45 - 8) if compact else (8, width - 16)
    hand_width = min(40 if compact else 56, lane_width * .42, max(16, height - 28) * 56 / 64)
    hand_height = hand_width * 64 / 56
    span = min(144, max(0, lane_width - hand_width - 12))
    middle = lane_x + (lane_width - hand_width) / 2
    start, end = middle - span * movement / 2, middle + span * movement / 2
    reading = (8, 4, lane_x - 12, height - 8) if compact else (8, 4, width - 16, 48)
    hand = (start, max(2, (height - 22 - hand_height) / 2) if compact else 54, hand_width, hand_height)
    track = (lane_x, height - 22, lane_width, 20)
    font = (12 if height < 70 else 14) if compact else 16
    return reading, hand, track, start, end, font


def present(app, owner, reading, volume, *, movement):
    backend = type(app._impl).__module__
    presenter = AppleCue if backend.startswith('toga_iOS.') else AndroidCue if backend.startswith('toga_android.') else None
    return presenter(app, owner, reading, volume, movement) if presenter is not None else None


class Cue:
    def __init__(self, app, owner, reading, volume, movement):
        self.app, self.owner = weakref.ref(app), weakref.ref(owner)
        self.movement = movement
        self.motion_enabled = bool(movement and not reduced_motion(app))
        self.volume_text = volume
        self.geometry = None
        self.closed = False
        self.build(app, reading, volume)
        self.relayout()
        if self.motion_enabled:
            self.animate()
        self.announce('\n'.join(text for text in (reading, volume) if text))

    def content(self):
        owner = self.owner()
        return (getattr(owner, 'book_content', None) or getattr(owner, 'crypt_content', None)) if owner is not None else None

    def region(self, content, rectangle):
        """Protect active fold regions using the reader's existing geometry owner."""
        from .fold_layout import division
        fold = division(self.owner(), content)
        x, y, width, height = rectangle
        if fold is not None:
            if fold.vertical:
                # Keep the whole cue on one side of a physical crease.
                width = min(width, fold.x)
            else:
                height = min(height, fold.y)
        return x, y, width, height

    def frames(self):
        return cue_layout(*self.geometry[2:], self.volume_text, self.movement)


class AppleCue(Cue):
    def announce(self, text):
        from ctypes import CDLL, c_uint, c_void_p
        from rubicon.objc import ns_from_py
        library = CDLL(None)
        post = library.UIAccessibilityPostNotification
        post.argtypes, post.restype = [c_uint, c_void_p], None
        notification = c_uint.in_dll(library, 'UIAccessibilityAnnouncementNotification').value
        post(notification, ns_from_py(text).ptr)

    def build(self, app, reading, volume):
        from rubicon.objc import ObjCClass, Block, objc_id, CGSize, CGPoint
        from commonUtils.ui.native.keyboard import native_value
        self.window = app.main_window._impl.native
        self.root = ObjCClass('UIView').alloc().init()
        self.root.userInteractionEnabled = False
        self.card = ObjCClass('UIView').alloc().init()
        self.card.backgroundColor = native_value(ObjCClass('UIColor').blackColor).colorWithAlphaComponent(.94)
        self.card.layer.cornerRadius = 14
        self.root.addSubview(self.card)
        self.reading = self.label(reading, self.card)
        self.volume = self.label(volume, self.root, background=True) if volume else None
        self.hand = self.track = None
        if self.movement:
            self.track = self.label('Start    →    End' if self.movement > 0 else 'End    ←    Start', self.card)
            self.track.accessibilityElementsHidden = True
            renderer = ObjCClass('UIGraphicsImageRenderer').alloc().initWithSize(CGSize(56, 64))
            def draw(context):
                path = ObjCClass('UIBezierPath').bezierPath()
                for op, *p in HAND:
                    if op == 'M':
                        path.moveToPoint(CGPoint(*p))
                    elif op == 'L':
                        path.addLineToPoint(CGPoint(*p))
                    else:
                        path.addCurveToPoint(CGPoint(*p[4:]), controlPoint1=CGPoint(*p[:2]), controlPoint2=CGPoint(*p[2:4]))
                path.closePath()
                native_value(ObjCClass('UIColor').whiteColor).setFill()
                native_value(ObjCClass('UIColor').blackColor).setStroke()
                path.lineWidth = 2
                path.fill()
                path.stroke()
            self.hand = ObjCClass('UIImageView').alloc().initWithImage(renderer.imageWithActions(Block(draw, None, objc_id)))
            self.hand.accessibilityElementsHidden = True
            self.card.addSubview(self.hand)
        self.window.addSubview(self.root)

    def label(self, text, parent, *, background=False):
        from rubicon.objc import ObjCClass
        from commonUtils.ui.native.keyboard import native_value
        label = ObjCClass('UILabel').alloc().init()
        label.text, label.numberOfLines, label.textAlignment = text, 0, 1
        label.font = ObjCClass('UIFont').systemFontOfSize(16)
        label.textColor = native_value(ObjCClass('UIColor').whiteColor)
        label.userInteractionEnabled = False
        label.isAccessibilityElement = True
        label.accessibilityLabel = text
        if background:
            label.backgroundColor = native_value(ObjCClass('UIColor').blackColor).colorWithAlphaComponent(.94)
            label.layer.cornerRadius = 14
            label.clipsToBounds = True
        parent.addSubview(label)
        return label

    def relayout(self):
        if self.closed:
            return
        content = self.content()
        if content is None:
            self.close()
            return
        from rubicon.objc import CGRect
        native = content._impl.native
        rect = native.convertRect(native.bounds, toView=self.window)
        raw = self.region(content, (float(rect.origin.x), float(rect.origin.y), float(rect.size.width), float(rect.size.height)))
        safe, size = self.window.safeAreaInsets, self.window.bounds.size
        x, y = max(raw[0], float(safe.left)), max(raw[1], float(safe.top))
        right = min(raw[0] + raw[2], float(size.width - safe.right))
        bottom = min(raw[1] + raw[3], float(size.height - safe.bottom))
        # A folded reader can retain a larger content box than its page's
        # touch surface. Keep every cue over the actual gesture viewport.
        from .external_display import comic_canvas
        canvas = comic_canvas(content)
        if canvas is not None:
            view = canvas._impl.native
            viewport = view.convertRect(view.bounds, toView=self.window)
            x, y = max(x, float(viewport.origin.x)), max(y, float(viewport.origin.y))
            right = min(right, float(viewport.origin.x + viewport.size.width))
            bottom = min(bottom, float(viewport.origin.y + viewport.size.height))
        geometry = (x, y, max(1, right - x), max(1, bottom - y))
        if self.geometry == geometry:
            return
        if self.geometry is not None and self.hand is not None:
            self.hand.layer.removeAllAnimations()
            self.motion_enabled = False
        self.geometry = geometry
        self.root.frame = CGRect(geometry[:2], geometry[2:])
        card, bottom, start, end = self.frames()
        self.card.frame = CGRect(card[:2], card[2:])
        if self.volume is not None:
            self.volume.frame = CGRect(bottom[:2], bottom[2:])
        reading, hand, track, _, _, font = cue_contents(*card[2:], self.movement)
        from rubicon.objc import ObjCClass
        self.reading.font = ObjCClass('UIFont').systemFontOfSize(font)
        self.reading.frame = CGRect(reading[:2], reading[2:])
        if self.hand is not None:
            self.hand.frame = CGRect(hand[:2], hand[2:])
            self.track.font = ObjCClass('UIFont').systemFontOfSize(12 if card[3] < 140 else 16)
            self.track.frame = CGRect(track[:2], track[2:])
        if self.volume is not None:
            self.volume.font = ObjCClass('UIFont').systemFontOfSize(14 if bottom[3] < 48 else 16)
        self.window.bringSubviewToFront(self.root)

    def animate(self):
        from rubicon.objc import ObjCClass
        _, _, start, end = self.frames()
        animation = ObjCClass('CABasicAnimation').animationWithKeyPath('transform.translation.x')
        animation.fromValue, animation.toValue = 0.0, end - start
        animation.duration = STROKE_SECONDS
        animation.repeatCount = 2  # Two finite physical strokes; no timer-driven repaint loop.
        animation.fillMode, animation.removedOnCompletion = 'forwards', False
        self.hand.layer.addAnimation(animation, forKey='comic.finger')

    def hand_position(self):
        from commonUtils.ui.native.keyboard import native_value
        layer = native_value(self.hand.layer.presentationLayer) or self.hand.layer
        return float(layer.frame.origin.x)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.hand is not None:
            self.hand.layer.removeAllAnimations()
            self.hand.image = None
        self.root.removeFromSuperview()


class AndroidCue(Cue):
    def announce(self, text):
        self.root.announceForAccessibility(text)

    def build(self, app, reading, volume):
        from android.widget import FrameLayout, ImageView
        from android.graphics import Bitmap, Canvas, Paint, Path
        self.window = app._impl.native.getWindow().getDecorView()
        self.context = self.window.getContext()
        self.scale = float(self.context.getResources().getDisplayMetrics().density)
        self.root, self.card = FrameLayout(self.context), FrameLayout(self.context)
        self.passive(self.root)
        self.passive(self.card)
        self.background(self.card)
        self.root.addView(self.card)
        self.reading = self.label(reading, self.card)
        self.volume = self.label(volume, self.root, background=True) if volume else None
        self.hand = self.track = None
        if self.movement:
            self.track = self.label('Start    →    End' if self.movement > 0 else 'End    ←    Start', self.card)
            self.track.setImportantForAccessibility(2)
            bitmap = Bitmap.createBitmap(112, 128, Bitmap.Config.ARGB_8888)
            drawing = Canvas(bitmap)
            drawing.scale(2.0, 2.0)
            path = Path()
            for op, *p in HAND:
                if op == 'M':
                    path.moveTo(*p)
                elif op == 'L':
                    path.lineTo(*p)
                else:
                    path.cubicTo(*p)
            path.close()
            paint = Paint(1)
            paint.setARGB(255, 255, 255, 255)
            drawing.drawPath(path, paint)
            paint.setARGB(255, 0, 0, 0)
            paint.setStyle(Paint.Style.STROKE)
            paint.setStrokeWidth(2.0)
            drawing.drawPath(path, paint)
            self.hand = ImageView(self.context)
            self.passive(self.hand)
            self.hand.setImportantForAccessibility(2)
            self.hand.setImageBitmap(bitmap)
            self.card.addView(self.hand)
        self.window.addView(self.root, FrameLayout.LayoutParams(1, 1))

    @staticmethod
    def passive(view):
        view.setClickable(False)
        view.setLongClickable(False)
        view.setFocusable(False)

    def background(self, view):
        from android.graphics.drawable import GradientDrawable
        shape = GradientDrawable()
        shape.setColor(-16777216)
        shape.setCornerRadius(14 * self.scale)
        view.setBackground(shape)

    def label(self, text, parent, *, background=False):
        from android.widget import TextView
        label = TextView(self.context)
        self.passive(label)
        label.setText(text)
        label.setTextColor(-1)
        label.setTextSize(16.0)
        label.setGravity(17)
        label.setContentDescription(text)
        label.setImportantForAccessibility(1)
        label.setPadding(round(8 * self.scale), 0, round(8 * self.scale), 0)
        if background:
            self.background(label)
        parent.addView(label)
        return label

    def frame(self, view, rect):
        from android.widget import FrameLayout
        x, y, width, height = (round(value * self.scale) for value in rect)
        params = FrameLayout.LayoutParams(max(1, width), max(1, height))
        params.leftMargin, params.topMargin = x, y
        view.setLayoutParams(params)

    def relayout(self):
        if self.closed:
            return
        content = self.content()
        if content is None:
            self.close()
            return
        from android.graphics import Rect
        from java import jarray, jint
        native = content._impl.native
        location, origin = jarray(jint)([0, 0]), jarray(jint)([0, 0])
        native.getLocationOnScreen(location)
        self.window.getLocationOnScreen(origin)
        safe = Rect()
        native.getWindowVisibleDisplayFrame(safe)
        x, y = max(location[0], safe.left), max(location[1], safe.top)
        right, bottom = min(location[0] + native.getWidth(), safe.right), min(location[1] + native.getHeight(), safe.bottom)
        geometry = ((x - origin[0]) / self.scale, (y - origin[1]) / self.scale,
                    max(1, right - x) / self.scale, max(1, bottom - y) / self.scale)
        geometry = self.region(content, geometry)
        if geometry == self.geometry:
            return
        if self.geometry is not None and self.hand is not None:
            self.hand.clearAnimation()
            self.motion_enabled = False
        self.geometry = geometry
        self.frame(self.root, geometry)
        card, bottom, start, end = self.frames()
        self.frame(self.card, card)
        reading, hand, track, _, _, font = cue_contents(*card[2:], self.movement)
        self.reading.setTextSize(float(font))
        self.frame(self.reading, reading)
        if self.volume is not None:
            self.frame(self.volume, bottom)
            self.volume.setTextSize(14.0 if bottom[3] < 48 else 16.0)
        if self.hand is not None:
            self.frame(self.hand, hand)
            self.track.setTextSize(12.0 if card[3] < 140 else 16.0)
            self.frame(self.track, track)
        self.root.bringToFront()

    def animate(self):
        from android.view.animation import TranslateAnimation
        _, _, start, end = self.frames()
        animation = TranslateAnimation(0.0, (end - start) * self.scale, 0.0, 0.0)
        animation.setDuration(round(STROKE_SECONDS * 1000))
        animation.setRepeatCount(1)
        animation.setFillAfter(True)
        self.hand.startAnimation(animation)

    def hand_position(self):
        from android.view.animation import Transformation, AnimationUtils
        transform = Transformation()
        animation = self.hand.getAnimation()
        if animation is not None:
            animation.getTransformation(AnimationUtils.currentAnimationTimeMillis(), transform)
        from java import jarray, jfloat
        values = jarray(jfloat)([0.0] * 9)
        transform.getMatrix().getValues(values)
        return (float(self.hand.getLeft()) + values[2]) / self.scale

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.hand is not None:
            self.hand.clearAnimation()
            self.hand.setImageDrawable(None)
        parent = self.root.getParent()
        if parent is not None:
            parent.removeView(self.root)
