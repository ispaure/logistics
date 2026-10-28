"""Application-owned reflow subscriptions; controls register with their owners."""
from dataclasses import dataclass
import weakref


@dataclass(frozen=True)
class LayoutFrame:
    width: float
    content_width: object


class LayoutSubscription:
    def __init__(self, participants, key, entry):
        self.participants, self.key, self.entry = participants, key, entry

    def dispose(self):
        if self.participants.entries.get(self.key) is self.entry:
            self.participants.entries.pop(self.key)


class LayoutParticipants:
    def __init__(self):
        self.entries = {}
        self.disposed = False

    def register(self, key, owner, reflow, *, order=0):
        """Callbacks receive (owner, frame), never capture a retained bound owner."""
        if self.disposed:
            raise RuntimeError('The layout owner has retired.')
        entry = (order, weakref.ref(owner), reflow)
        self.entries[key] = entry
        return LayoutSubscription(self, key, entry)

    def reflow(self, frame):
        for key, entry in sorted(tuple(self.entries.items()), key=lambda item: item[1][0]):
            if self.disposed:
                break
            if self.entries.get(key) is not entry:
                continue
            _, reference, callback = entry
            owner = reference()
            if owner is None:
                self.entries.pop(key, None)
            else:
                callback(owner, frame)

    def dispose(self):
        self.disposed = True
        self.entries.clear()


def participants(app):
    owner = getattr(app, '_layout_participants', None)
    if owner is None:
        app._layout_participants = owner = LayoutParticipants()
    return owner


def reflow_settings_section(owner, frame):
    from .settings.forms import fit_section
    fit_section(owner, max(280, frame.content_width('settings')))
