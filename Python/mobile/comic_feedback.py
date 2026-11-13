"""Window-local comic guidance; presentation never becomes part of a page."""
import weakref

HINT_SECONDS = 2.5


def clear(app, *, owner=None):
    feedback = getattr(app, '_comic_boundary_feedback', None)
    if feedback is not None and (owner is None or feedback.owned_by(owner)):
        feedback.close()


def sync(app, body):
    feedback = getattr(app, '_comic_boundary_feedback', None)
    owner = feedback.owner() if feedback is not None and feedback.owner is not None else None
    if owner is None:
        return
    def contains(view):
        return (getattr(view, '_reader_session_id', None) == owner.session.id
                or any(contains(child) for child in view.children))
    if not contains(body):
        feedback.close()
    elif feedback.native is not None:
        feedback.native.relayout()


def physical_swipe(right_to_left, direction=1):
    """Match ImageCanvas's physical swipe and schedule_swipe's manga inversion."""
    movement = (1 if right_to_left else -1) * (1 if direction > 0 else -1)
    return movement, 'left to right' if movement > 0 else 'right to left'


class ComicFeedback:
    def __init__(self, app):
        self.app = weakref.ref(app)
        self.owner = self.direction = None
        self.deadline = 0
        self.timer = self.native = self.subscription = None
        self.message = self.reading_text = self.volume_text = ''
        self.armed = False
        self.movement = -1

    def owned_by(self, owner):
        return self.owner is not None and self.owner() is owner

    def close(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        if self.subscription is not None:
            self.subscription.dispose()
            self.subscription = None
        if self.native is not None:
            self.native.close()
            self.native = None
        self.owner = self.direction = None
        self.deadline = 0
        self.armed = False
        self.message = self.reading_text = self.volume_text = ''

    def show(self, owner, reading, volume='', *, movement=-1):
        app = self.app()
        self.owner = weakref.ref(owner, lambda reference: self.close())
        self.reading_text, self.volume_text = reading, volume
        self.message = '\n'.join(text for text in (reading, volume) if text)
        self.movement = movement
        from .comic_guidance import present
        self.native = present(app, owner, reading, volume, movement=movement)
        if self.native is not None:
            from .layout_participants import participants
            self.subscription = participants(app).register(('comic-guidance', id(self)), self,
                lambda feedback, frame: feedback.native.relayout() if feedback.native is not None else None)
        self.timer = app.loop.call_later(HINT_SECONDS, self.close)


async def boundary(owner, direction, *, right_to_left, available, adjacent):
    app = getattr(owner, 'app', owner)
    feedback = getattr(app, '_comic_boundary_feedback', None)
    if feedback is None:
        feedback = app._comic_boundary_feedback = ComicFeedback(app)
    now = app.loop.time()
    repeat = (feedback.owned_by(owner) and feedback.armed
              and feedback.direction == direction and now < feedback.deadline)
    feedback.close()
    if repeat and available:
        error = await adjacent(direction)
        if isinstance(error, str) and error:
            feedback.show(owner, error, movement=0)
        return
    movement, forward = physical_swipe(right_to_left)
    _, action = physical_swipe(right_to_left, direction)
    reading = f'Swipe {forward} to read'
    if direction > 0:
        reading = 'End of comic · ' + reading
    volume = (f'Swipe {action} again for {"previous" if direction < 0 else "next"} volume'
              if available else '')
    feedback.show(owner, reading, volume, movement=movement)
    feedback.direction = direction
    feedback.armed = bool(available)
    feedback.deadline = now + HINT_SECONDS
