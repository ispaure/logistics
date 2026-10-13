"""Debounced saves owned by a shared IDE buffer; writes run on the host worker."""
from commonUtils.ui import pyside as qt
from commonUtils.persistence.text import decode_bytes, write_text_file


def write_snapshot(snapshot, text):
    content = snapshot.encode(text)
    write_text_file(snapshot.path, content, expected=snapshot.original)
    return decode_bytes(content, path=snapshot.path, encoding=snapshot.encoding)


class AutoSave(qt.QObject):
    def __init__(self, workspace, buffer):
        super().__init__(buffer)
        self.workspace, self.buffer = workspace, buffer
        self.busy = False
        self.error = ''
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.save)
        buffer.text.contentsChanged.connect(self.changed)
        qt.QApplication.instance().focusChanged.connect(self.focus_changed)

    def changed(self):
        if self.workspace.project.autosave == 'after_delay' and not self.error:
            self.timer.start()

    def focus_changed(self, old, new):
        if self.workspace.project.autosave != 'focus_change' or old is None:
            return
        views = self.buffer.views
        if any(v is old or v.isAncestorOf(old) for v in views) and not any(
                v is new or new is not None and v.isAncestorOf(new) for v in views):
            self.save()

    def reset(self):
        self.error = ''
        self.workspace.refresh_autosave_notice()

    def save(self):
        workspace, buffer = self.workspace, self.buffer
        if (self.busy or self.error or workspace.closing or getattr(workspace, '_autosave_paused', False) or not buffer.views
                or workspace.project.autosave == 'off' or not buffer.text.isModified()):
            return
        if any((v if hasattr(v, 'isReadOnly') else v.editor).isReadOnly() for v in buffer.views):
            return
        snapshot = buffer.snapshot
        text = buffer.text.toPlainText()
        self.busy = True
        def done(saved):
            self.busy = False
            buffer.snapshot = saved
            buffer.configure()
            # Syntax/format updates also advance Qt's revision. Only newer
            # source text must remain dirty and receive a subsequent save.
            if buffer.text.toPlainText() == text:
                buffer.text.setModified(False)
            workspace.watch.addPath(str(saved.path))
            workspace.update_buffer_titles(buffer)
            if buffer.text.isModified():
                self.changed()
                focus = qt.QApplication.focusWidget()
                if workspace.project.autosave == 'focus_change' and not any(
                        v is focus or focus is not None and v.isAncestorOf(focus) for v in buffer.views):
                    self.save()
        def failed(error):
            self.busy = False
            self.error = f'Autosave paused for {snapshot.path.name}: {error}. Use Save, Reload or Save As.'
            workspace.refresh_autosave_notice()
        workspace.run(lambda: write_snapshot(snapshot, text), done, failed)


def pause_autosave(method):
    """Modal save/close choices must not trigger background writes via focus loss."""
    from functools import wraps
    @wraps(method)
    def paused(workspace, *args, **kwargs):
        previous = getattr(workspace, '_autosave_paused', False)
        workspace._autosave_paused = True
        try:
            return method(workspace, *args, **kwargs)
        finally:
            workspace._autosave_paused = previous
            if not previous and not workspace.closing:
                for doc in workspace.documents.values():
                    if doc.buffer.text.isModified() and not doc.buffer.autosave.busy:
                        doc.buffer.autosave.changed()
    return paused
