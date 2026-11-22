"""Route process-window transfer outcomes through the existing desktop notices."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from dataclasses import replace
from weakref import ref

from shiboken6 import isValid

from commonUtils.ui import pyside as qt
from services.transfer_notifications import start_transfer_notice, transfer_notice
from .notifications import notification_service


def bind_transfer_notice(host, window):
    """Bind before the transfer starts and before the window is presented."""
    completion = start_transfer_notice()
    reference = ref(window)
    host_reference = ref(host)
    revoked = window.context.get('transfer_revoked', lambda: False)

    def locked(job):
        guard = getattr(job, '_private_view_guard', None)
        if guard is not None:
            guard.check_revocation()
        return bool((guard is not None and guard.locked) or revoked())

    def finish(result):
        app = qt.QApplication.instance()
        host = host_reference()
        if (app is None or app.closingDown() or window.closing or host is None
                or not isValid(host) or host.closing):
            return
        protected = locked(window)
        foreground = app.applicationState() == qt.Qt.ApplicationState.ApplicationActive
        observed = foreground and not protected and host._viewed(window)
        outcome = 'cancelled' if result.state == 'cancelled' else 'success' if result.succeeded else 'failure'
        notice = transfer_notice(completion, outcome, observed=observed, locked=protected,
                                 details='Workspace actions')
        if notice is None:
            return

        service = notification_service()
        native = not foreground and service.native_available()

        def details():
            job = reference()
            workspace = host_reference()
            if (job is None or not isValid(job) or locked(job)
                    or workspace is None or not isValid(workspace) or workspace.closing):
                return
            frame = workspace.window()
            frame.showNormal() if frame.isMinimized() else frame.show()
            frame.raise_()
            frame.activateWindow()
            record = workspace.records.get(job)
            # The system tray provides just one click signal for all messages.
            if native or record is None or record['closed']:
                workspace.activate()
            else:
                workspace.present(job)

        notice = replace(notice, activate=None if protected else details, native=native)
        host.records[window]['notice_id'] = notice.id
        service.publish(notice)

    window.runner.completed.connect(finish)
