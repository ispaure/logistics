"""Application-owned optional baseline discovery and asynchronous gutter updates."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor.markers import line_changes

# Jobs contain only immutable Python snapshots, never Qt objects. Destruction may
# abandon a read result safely; each controller submits at most one job at a time.
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='editor-diff')


def compare(snapshot, text, details=False, cancel=None):
    if cancel is not None and cancel.is_set():
        return ((), '', '') if details else ((), '')
    before, label = snapshot.text, 'Last saved file (unsaved changes)'
    if max(len(before), len(text)) > 250_000:
        result = (), 'Change markers unavailable for large documents'
        return (*result, '') if details else result
    if snapshot.path:
        try:
            from features.git.editor_baseline import index_baseline
            before, label = index_baseline(snapshot.path, snapshot.encoding, cancel=cancel)
        except (ImportError, OSError, ValueError, RuntimeError):
            pass
    if len(before) > 250_000:
        result = (), 'Change markers unavailable for large baselines'
        return (*result, '') if details else result
    if cancel is not None and cancel.is_set():
        return ((), '', '') if details else ((), '')
    result = line_changes(before, text), label
    return (*result, before) if details else result


class ChangeMarkers(qt.QObject):
    def __init__(self, owner, document, snapshot, views):
        super().__init__(owner)
        self.document, self.snapshot, self.views = document, snapshot, views
        self.future = None
        self.run = None
        self.baseline = ('', '')
        self.cancel = Event()
        self.pending = []
        cancel, pending = self.cancel, self.pending
        def stop():
            cancel.set()
            if pending:
                pending[0].cancel()
        self.destroyed.connect(stop)
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
        try:
            self.future = _executor.submit(compare, self.request[0], self.document.toPlainText(), True, self.cancel)
        except (OSError, RuntimeError):
            self._publish((), 'Change markers unavailable', '')
            return
        self.pending[:] = [self.future]
        self.poll.start()

    def finished(self):
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        self.pending.clear()
        self.poll.stop()
        try:
            changes, label, before = future.result()
        except Exception:
            changes, label, before = (), 'Change markers unavailable', ''
        if self.request != (self.snapshot(), self.document.revision()):
            self.timer.start(250)
            return
        self._publish(changes, label, before)

    def _publish(self, changes, label, before):
        self.baseline = before, label
        for view in self.views():
            if hasattr(view, 'set_line_changes'):
                view.set_line_changes(changes, label + ('\nClick a colored marker to review the change.' if self.run else ''))
                view.gutter.installEventFilter(self)

    def eventFilter(self, watched, event):
        if (self.run is not None and event.type() == qt.QEvent.Type.MouseButtonPress
                and event.button() == qt.Qt.MouseButton.LeftButton and event.position().x() < 8
                and self.request == (self.snapshot(), self.document.revision())):
            view = next((v for v in self.views() if getattr(v, 'gutter', None) is watched), None)
            if view is not None:
                row = view.cursorForPosition(qt.QPoint(0, int(event.position().y()))).blockNumber()
                block = view.document().findBlockByNumber(row)
                top = round(view.blockBoundingGeometry(block).translated(view.contentOffset()).top())
                height = round(view.blockBoundingRect(block).height())
                # An EOF deletion can share a row with a modification. Match
                # the red boundary before the vertical added/modified band.
                change = next((c for c in view.line_changes if c.kind == 'delete'
                    and row == min(c.start, view.blockCount() - 1)
                    and (top if c.start < view.blockCount() else top + height - 3)
                        <= event.position().y()
                        < (top + 3 if c.start < view.blockCount() else top + height)), None)
                if change is None:
                    change = next((c for c in view.line_changes if c.start <= row < c.end), None)
                if change is not None:
                    from services.editors.ui.hunks import HunkReview
                    review = HunkReview(self, view, change)
                    review.show()
                    return True
        return super().eventFilter(watched, event)
