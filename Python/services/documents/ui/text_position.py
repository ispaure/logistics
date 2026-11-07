"""Qt text cursor and viewport checkpoints without document text or drafts."""

from hashlib import sha256

from commonUtils.filesystem.storage import cache_directory
from commonUtils.ui import pyside as qt

from services.documents.progress import open_progress
from .position_notice import position_notice


class TextPosition(qt.QObject):
    def __init__(self, owner, views, *, active=None, set_mode=None, current_path=None, notice=None):
        super().__init__(owner)
        self.owner = owner
        self.views = views
        self.active = active or (lambda: next(iter(views)))
        self.set_mode = set_mode
        self.current_path = current_path
        self.notice = notice
        self.progress = self.identity = None
        self.saved = {}
        self.ready = False
        self.accepted = None
        self.timer = qt.QTimer(self)
        self.timer.setInterval(400)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.flush)
        owner.installEventFilter(self)
        for widget in views.values():
            widget.verticalScrollBar().valueChanged.connect(self.observe)
            if not isinstance(widget, qt.QTextBrowser):
                widget.cursorPositionChanged.connect(self.observe)

    def bind(self, provider, path, data, *, kind, restore=True):
        revision = sha256(data).hexdigest() if path is not None else None
        identity = provider, path, revision
        if identity == self.identity:
            return
        self.retire()
        self.identity = identity
        if path is None:
            return
        self.progress = open_progress(provider, path, cache_directory(create=False),
                                      kind=kind, revision=revision)
        self.saved = self.progress.load()
        self.report(self.progress.load_status)
        if not restore:
            self.saved = {}
        current = self.progress
        qt.QTimer.singleShot(0, self, lambda: self.restore(current))

    def restore(self, progress):
        if progress is not self.progress or not self.owner.isVisible() or self.ready:
            return
        mode = self.saved.get('mode')
        if self.set_mode is not None and mode in self.views:
            self.set_mode(mode)
        widget = self.views[self.active()]
        cursor = self.saved.get('cursor')
        if not isinstance(widget, qt.QTextBrowser) and type(cursor) is int:
            position = widget.textCursor()
            position.setPosition(max(0, min(cursor, widget.document().characterCount() - 1)))
            widget.setTextCursor(position)
        scroll = self.saved.get('scroll')
        if type(scroll) in (float, int) and 0 <= scroll <= 1:
            bar = widget.verticalScrollBar()
            bar.setValue(round(scroll * bar.maximum()))
        self.accepted = self.payload()
        self.ready = True

    def payload(self):
        mode = self.active()
        widget = self.views[mode]
        bar = widget.verticalScrollBar()
        value = dict(mode=mode, scroll=bar.value() / max(1, bar.maximum()))
        if not isinstance(widget, qt.QTextBrowser):
            value['cursor'] = widget.textCursor().position()
        return value

    def observe(self, *_):
        if (self.ready and self.progress is not None and self.owner.isVisible()
                and (self.current_path is None or self.current_path() == self.identity[1])):
            value = self.payload()
            if value != self.accepted and self.progress.observe(value) is not None:
                self.accepted = value
                self.timer.start()

    def flush(self):
        self.timer.stop()
        if self.progress is not None:
            self.report(self.progress.flush())

    def report(self, status):
        if self.notice is not None:
            message = position_notice(self.progress, status)
            if message:
                self.notice(message)

    def retire(self):
        self.ready = False
        if self.progress is not None:
            self.flush()
            self.progress.retire()
            self.progress = None

    def eventFilter(self, watched, event):
        if event.type() == qt.QEvent.Type.Show and self.progress is not None:
            progress = self.progress
            qt.QTimer.singleShot(0, self, lambda: self.restore(progress))
        elif event.type() == qt.QEvent.Type.Hide:
            self.flush()
        return False
