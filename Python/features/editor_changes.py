"""Application-owned optional baseline discovery and asynchronous gutter updates."""
from concurrent.futures import ThreadPoolExecutor
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor.markers import line_changes

# Jobs contain only immutable Python snapshots, never Qt objects. Destruction may
# abandon a read result safely; each controller submits at most one job at a time.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='editor-diff')


def compare(snapshot, text):
    before, label = snapshot.text, 'Last saved file (unsaved changes)'
    if max(len(before), len(text)) > 250_000:
        return (), 'Change markers unavailable for large documents'
    if snapshot.path:
        try:
            from features.git.editor_baseline import index_baseline
            before, label = index_baseline(snapshot.path, snapshot.encoding)
        except (ImportError, OSError, ValueError, RuntimeError):
            pass
    if len(before) > 250_000:
        return (), 'Change markers unavailable for large baselines'
    return line_changes(before, text), label


class ChangeMarkers(qt.QObject):
    def __init__(self, owner, document, snapshot, views):
        super().__init__(owner)
        self.document, self.snapshot, self.views = document, snapshot, views
        self.future = None
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.refresh)
        self.poll = qt.QTimer(self)
        self.poll.setInterval(100)
        self.poll.timeout.connect(self.finished)
        self.refresh_timer = qt.QTimer(self)
        self.refresh_timer.setInterval(2000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()
        document.contentsChanged.connect(self.changed)
        self.changed()

    def changed(self):
        for view in self.views():
            if hasattr(view, 'set_line_changes'):
                view.set_line_changes(())
        self.timer.start(250)

    def refresh(self):
        if self.future is not None:
            return
        self.request = (self.snapshot(), self.document.revision())
        self.future = _executor.submit(compare, self.request[0], self.document.toPlainText())
        self.poll.start()

    def finished(self):
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        self.poll.stop()
        try:
            changes, label = future.result()
        except Exception:
            changes, label = (), 'Change markers unavailable'
        if self.request != (self.snapshot(), self.document.revision()):
            self.timer.start(250)
            return
        for view in self.views():
            if hasattr(view, 'set_line_changes'):
                view.set_line_changes(changes, label)
