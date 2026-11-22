"""Mobile routing for path-free terminal notices."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from collections import deque
import logging

from . import transfer_notification_native as native

PREFERENCE = 'transfer_system_notifications'


def for_app(app):
    service = getattr(app, '_transfer_notifications', None)
    if service is None:
        service = app._transfer_notifications = TransferNotices(app)
    return service


def sync(app):
    service = getattr(app, '_transfer_notifications', None)
    if service is not None:
        service.refresh()


def foreground(app):
    privacy = getattr(app, 'screen_privacy', None)
    return bool(app.active_host and getattr(app, 'scene_active', True)
                and not getattr(privacy, 'inactive', False)
                and not getattr(privacy, 'interrupted', False))


def covered(app):
    privacy = getattr(app, 'screen_privacy', None)
    return bool(getattr(privacy, 'lock_view', None) is not None
                or getattr(privacy, 'resume_locked', False))


class TransferNotices:
    """Deliver once, falling back to an in-app banner on the next active view."""

    def __init__(self, app):
        self.app = app
        self.pending = deque(maxlen=32)
        self.close_banner = None
        self.timer = None

    def publish(self, notice, action):
        app = self.app
        if not app.active_host:
            return
        if not foreground(app) and app.preferences.values.get(PREFERENCE) == 'true':
            try:
                native.post(app, notice, allow=lambda: app.active_host and not foreground(app)
                            and app.preferences.values.get(PREFERENCE) == 'true',
                            done=lambda posted: None if posted else self.defer(notice, action))
                return
            except Exception:
                logging.getLogger(__name__).warning('Could not submit a transfer notification.')
        self.defer(notice, action)

    def defer(self, notice, action):
        if self.app.active_host:
            self.pending.append((notice, action))
            self.refresh()

    def close(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None
        close, self.close_banner = self.close_banner, None
        if close is not None:
            close()

    def dispose(self):
        self.close()
        self.pending.clear()

    def refresh(self):
        if not foreground(self.app) or covered(self.app):
            self.close()
            return
        if self.close_banner is not None or not self.pending:
            return
        notice, action = self.pending.popleft()

        def details():
            self.close()
            if foreground(self.app) and not covered(self.app):
                action()
            self.refresh()

        try:
            self.close_banner = native.banner(self.app, notice, details)
        except Exception:
            logging.getLogger(__name__).warning('Could not display a transfer banner.')
        if self.close_banner is not None:
            self.timer = self.app.loop.call_later(6, self.advance)

    def advance(self):
        self.close()
        self.refresh()
