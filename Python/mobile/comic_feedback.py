"""Window-local, transient comic boundary guidance, outside the exported image."""
import weakref

HINT_SECONDS = 2.5


def clear(app, *, owner=None):
    feedback = getattr(app, '_comic_boundary_feedback', None)
    if (feedback is not None and (owner is None
            or (feedback.owner is not None and feedback.owner() is owner))):
        feedback.close()


def sync(app, body):
    feedback = getattr(app, '_comic_boundary_feedback', None)
    owner = feedback.owner() if feedback is not None and feedback.owner is not None else None
    if owner is None:
        return
    key = owner.session.id
    def contains(view):
        return (getattr(view, '_reader_session_id', None) == key
                or any(contains(child) for child in view.children))
    if not contains(body):
        feedback.close()


class ComicFeedback:
    def __init__(self, app):
        self.app = weakref.ref(app)
        self.owner = None
        self.direction = None
        self.deadline = 0
        self.timer = self.native = None
        self.message = ''

    def close(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        app = self.app()
        if self.native is not None:
            if app is not None and type(app._impl).__module__.startswith('toga_android.'):
                self.native.cancel()
            else:
                self.native.removeFromSuperview()
            self.native = None
        self.owner = self.direction = None
        self.message = ''

    def show(self, message):
        app = self.app()
        self.message = message
        backend = type(app._impl).__module__
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass
            from .screen_privacy import native_value
            window = app.main_window._impl.native
            label = ObjCClass('UILabel').alloc().init()
            label.setText(message)
            label.setNumberOfLines(0)
            label.setTextAlignment(1)
            label.setFont(ObjCClass('UIFont').systemFontOfSize(16))
            label.setTextColor(native_value(ObjCClass('UIColor'), 'whiteColor'))
            label.setBackgroundColor(native_value(ObjCClass('UIColor'), 'blackColor').colorWithAlphaComponent(.9))
            label.layer.setCornerRadius(18)
            label.setClipsToBounds(True)
            label.setUserInteractionEnabled(False)
            label.setAccessibilityLabel(message)
            label.setTranslatesAutoresizingMaskIntoConstraints(False)
            window.addSubview(label)
            safe = window.safeAreaLayoutGuide
            for constraint in (
                label.centerXAnchor.constraintEqualToAnchor(safe.centerXAnchor),
                label.bottomAnchor.constraintEqualToAnchor(safe.bottomAnchor, constant=-56),
                label.widthAnchor.constraintEqualToConstant(min(340, float(window.bounds.size.width) - 32)),
                label.heightAnchor.constraintEqualToConstant(92),
            ):
                constraint.setActive(True)
            self.native = label
        elif backend.startswith('toga_android.'):
            from java import jclass
            self.native = jclass('android.widget.Toast').makeText(app._impl.native, message, 0)
            self.native.show()
        self.timer = app.loop.call_later(HINT_SECONDS, self.close)


async def boundary(owner, direction, *, right_to_left, available, adjacent):
    app = getattr(owner, 'app', owner)
    feedback = getattr(app, '_comic_boundary_feedback', None)
    if feedback is None:
        feedback = app._comic_boundary_feedback = ComicFeedback(app)
    now = app.loop.time()
    repeat = (feedback.owner is not None and feedback.owner() is owner
              and feedback.direction == direction and now < feedback.deadline)
    feedback.close()
    if repeat and available:
        await adjacent(direction)
        return
    forward, backward = ('→', '←') if right_to_left else ('←', '→')
    if direction < 0:
        message = f'{forward} Swipe to read\n'
        message += f'Swipe {backward} again for previous volume' if available else 'Beginning of comic'
    else:
        message = 'End of comic\n'
        message += f'Swipe {forward} again for next volume' if available else 'No next volume in this folder'
    feedback.owner, feedback.direction = weakref.ref(owner), direction
    feedback.deadline = now + HINT_SECONDS
    feedback.show(message)
