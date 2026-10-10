"""Retain one editor per document and reuse already-open files across browsers."""

from commonUtils.ui import pyside as qt


class EditorService(qt.QObject):
    idle = qt.Signal()
    saved = qt.Signal(object)

    def __init__(self, parent, *, history_path=None, preferences_path=None):
        super().__init__(parent)
        self.windows = []
        self.window = None
        self.history_path = history_path
        self.preferences_path = preferences_path
        from pathlib import Path
        from commonUtils.storage import cache_directory
        from .session import EditorSession
        directory = Path(preferences_path).parent if preferences_path else cache_directory(create=False) / "TextEditor"
        self.session = EditorSession(self, directory / "sessions")
        self._restore_checked = False

    def register(self, window):
        self.windows.append(window)
        if self.session.suspended:
            self.session.retained = []
        self.session.suspended = False
        self.session.start()
        self.session.changed()
        self.window = window
        window.destroyed.connect(lambda obj=None, owner=window: self._window_destroyed(owner))
        window.closed.connect(lambda owner=window: self._window_destroyed(owner))
        window.idle.connect(self.idle)
        window.saved.connect(self.saved)

    def open(self, path=None, *, force=False, encoding=None):
        from pathlib import Path
        from .window import EditorWindow
        from commonUtils.ui.document_host import show_document
        path = Path(path).resolve() if path is not None else None
        if not self._restore_checked:
            self._restore_checked = True
            if not self.windows:
                previous = self.session.previous()
                if previous is not None:
                    window = EditorWindow(service=self, create_blank=False,
                        history_path=self.history_path, preferences_path=self.preferences_path)
                    self.session.restore(window, previous, requested=path)
                    show_document(window)
                    return window
        window = None
        if path is not None:
            window = next((owner for owner in self.windows
                if owner._opening_path == path or owner.current is not None
                and owner.current.path == path), None)
            if window is None:
                window = next((owner for owner in self.windows
                    if not owner.task.busy and (owner.current is None or
                    owner.current.path is None and not owner.current.modified
                    and not owner.current.editor.toPlainText())), None)
        if window is None:
            window = EditorWindow(service=self, create_blank=path is None,
                history_path=self.history_path, preferences_path=self.preferences_path)
        self.window = window
        if path is not None and window._opening_path != path:
            window.open_path(path, force=force, encoding=encoding)
        show_document(window)
        return window

    def _window_destroyed(self, window):
        if window not in self.windows:
            return
        suspended = getattr(window, "_suspending", False)
        if window in self.windows:
            self.windows.remove(window)
        if self.window is window:
            self.window = self.windows[-1] if self.windows else None
        if not suspended:
            self.session.changed()
        if not self.windows:
            self.session.last_window_closed(suspended)
            if self.session.suspended:
                from commonUtils.session_store import SessionStore
                from uuid import uuid4
                self.session.store = SessionStore(self.session.directory / (uuid4().hex + ".json"))
                self.session.persisted = -1
                self._restore_checked = False

    def save_all(self):
        pending = [(window, window.current) for window in self.windows
                   if window.current is not None and
                   (window.current.modified or window.current.path is None)]

        def step():
            if pending:
                window, document = pending.pop(0)
                if window in self.windows and document is window.current:
                    if window.task.busy:
                        pending.insert(0, (window, document))

                        def ready():
                            window.idle.disconnect(ready)
                            step()
                        window.idle.connect(ready)
                    else:
                        window.save_document(document, after=step)
                else:
                    step()
        step()

    def close_all(self):
        pending = list(self.windows)

        def step():
            if not pending:
                return
            window = pending.pop(0)
            if window not in self.windows:
                step()
                return

            def closed():
                window.closed.disconnect(closed)
                step()
            window.closed.connect(closed)
            if not window.close() and not window._close_pending:
                window.closed.disconnect(closed)
        step()

    def suspend(self):
        from commonUtils.ui.document_host import close_document
        for window in tuple(self.windows):
            window._suspend_requested = True
            close_document(window)

    def prepare_close(self):
        ready = True
        for window in tuple(self.windows):
            if window.prepare_close():
                window.close()
            else:
                ready = False
        return ready


def editor_service():
    app = qt.QApplication.instance()
    if not hasattr(app, "_logistics_text_editor"):
        app._logistics_text_editor = EditorService(app)
    return app._logistics_text_editor


class BrowserController(qt.QObject):
    idle = qt.Signal()

    def __init__(self, host):
        super().__init__(host)
        self.service = editor_service()
        browser = getattr(host, "file_browser", host)
        refresh = getattr(browser, "refresh_item", None)
        if refresh:
            self.service.saved.connect(refresh)

    def open(self, path, *, force=False):
        return self.service.open(path, force=force)

    def prepare_close(self):
        return True
