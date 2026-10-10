"""Retained folder-operation tabs, unread completion state and native notices."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from .documents import DocumentsPage


class FolderActionsPage(DocumentsPage):
    def __init__(self, activate, parent=None):
        super().__init__(activate, parent)
        self.workspace._drop_target.widget().setText('Folder actions appear here when you start a sync.')
        self.workspace.active_changed.connect(lambda pane: self.acknowledge_current())
        self.window().installEventFilter(self)

    @property
    def unread_count(self):
        return sum(record.get('unseen', False) and not record['closed'] for record in self.records.values())

    def present(self, window):
        fresh = window not in self.records
        if fresh:
            context = window.context
            source, destination = context.get('source', ''), context.get('destination', '')
            if source and destination:
                window.setWindowTitle(f"{context.get('operation', 'Sync')}: "
                    f'{Path(source).name or source} → {Path(destination).name or destination}')
        super().present(window)
        if fresh:
            self.records[window].update(name=window.windowTitle(), unseen=False)
            window.runner.completed.connect(lambda result, job=window: self._completed(job, result))

    def _viewed(self, window):
        record = self.records.get(window)
        if record is None or record['closed'] or record['dock'] is None:
            return False
        dock = record['dock']
        if dock.isFloating():
            return dock.isVisible() and dock.isActiveWindow()
        pane = self.workspace.active_view
        return (self.isVisible() and self.window().isActiveWindow() and not self.window().isMinimized()
                and pane is not None and pane.document is window)

    def _completed(self, window, result):
        record = self.records.get(window)
        if record is None or record['closed']:
            return
        label = 'Complete' if result.succeeded else 'Cancelled' if result.state == 'cancelled' else 'Failed'
        record['unseen'] = not self._viewed(window)
        window.setWindowTitle(f"{record['name']} · {label}")
        self.changed.emit()
        if not self.closing:
            notice = self.notify(f"{record['name']} · {label}", result.error or 'Open Folder Actions for details.',
                        failed=result.state != 'cancelled' and not result.succeeded,
                        outcome='cancelled' if result.state == 'cancelled' else None)
            if notice is not None:
                record['notice_id'] = notice.id
                if not record['unseen']:
                    from .notifications import notification_service
                    notification_service().acknowledge(notice.id)

    @property
    def tray(self):
        from .notifications import notification_service
        return notification_service().tray

    @tray.setter
    def tray(self, value):
        from .notifications import notification_service
        notification_service().tray = value

    def notify(self, title, message, *, failed=False, outcome=None):
        from .notifications import notify
        return notify('folder_actions', title, message,
                      outcome=outcome or ('failure' if failed else 'success'),
                      activate=self.activate, native=True)

    def acknowledge_current(self):
        changed = False
        for window, record in self.records.items():
            if record.get('unseen') and self._viewed(window):
                record['unseen'] = False
                if record.get('notice_id'):
                    from .notifications import notification_service
                    notification_service().acknowledge(record['notice_id'])
                changed = True
        if changed:
            self.changed.emit()

    def showEvent(self, event):
        super().showEvent(event)
        qt.QTimer.singleShot(0, self, self.acknowledge_current)

    def eventFilter(self, watched, event):
        if event.type() == qt.QEvent.Type.WindowActivate:
            qt.QTimer.singleShot(0, self, self.acknowledge_current)
        return super().eventFilter(watched, event)
