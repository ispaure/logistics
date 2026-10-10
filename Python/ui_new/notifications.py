"""Application notification routing; features publish outcomes rather than tray widgets."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.notifications import Notice, NotificationCenter, Toast
from uuid import uuid4
from weakref import WeakMethod
from shiboken6 import isValid


class ApplicationNotifications(NotificationCenter):
    def __init__(self, parent):
        super().__init__(parent)
        self.tray = None
        self.native_notice = None
        self.published.connect(self._native)

    def _native(self, notice):
        if not notice.native or not qt.QSystemTrayIcon.isSystemTrayAvailable() or not qt.QSystemTrayIcon.supportsMessages():
            return
        if self.tray is None:
            from .sidebar import DestinationIcon
            from commonUtils.ui.icons import set_painted_icon
            self.tray = qt.QSystemTrayIcon(self)
            set_painted_icon(self.tray, DestinationIcon, 'actions')
            self.tray.setToolTip('Logistics')
            self.tray.messageClicked.connect(self._open_native)
            self.tray.show()
        self.native_notice = notice
        icon = qt.QSystemTrayIcon.MessageIcon.Warning if notice.outcome == 'failure' else qt.QSystemTrayIcon.MessageIcon.Information
        self.tray.showMessage(notice.title, notice.message, icon, 5000)

    def _open_native(self):
        notice = self.native_notice
        if notice:
            if callable(notice.activate):
                notice.activate()
            self.acknowledge(notice.id)


def notification_service():
    app = qt.QApplication.instance()
    if not hasattr(app, '_logistics_notifications'):
        app._logistics_notifications = ApplicationNotifications(app)
    return app._logistics_notifications


def notify(source, title, message, *, outcome='success', activate=None, native=False, identifier=None):
    if callable(activate) and isinstance(getattr(activate, '__self__', None), qt.QObject):
        reference = WeakMethod(activate)
        def alive_action():
            method = reference()
            if method is not None and isValid(method.__self__):
                method()
        activate = alive_action
    notice = Notice(identifier or uuid4().hex, source, title, message, outcome, activate, native)
    notification_service().publish(notice)
    return notice
