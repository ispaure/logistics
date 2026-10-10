"""Private editor checkpoints, safe restoration, and application hot exit."""
import base64
import codecs
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
from commonUtils.ui import pyside as qt
from commonUtils.session_store import SessionStore
from commonUtils.text_files import decode_bytes, read_text_file, MAX_BYTES


def document_record(document):
    views = [document.views.primary]
    if document.views.secondary is not None:
        views.append(document.views.secondary)
    return {
        "path": str(document.path) if document.path else None,
        "original": base64.b64encode(document.snapshot.original).decode("ascii"),
        "original_encoding": document.snapshot.encoding,
        "text": document.editor.toPlainText(), "modified": document.modified,
        "encoding": document.encoding, "newline": document.newline_override,
        "bom": document.bom_override.hex() if document.bom_override is not None else None,
        "language": document.language,
        "orientation": "vertical" if document.views.splitter.orientation() == qt.Qt.Orientation.Vertical else "horizontal",
        "views": [{"position": editor.textCursor().position(), "anchor": editor.textCursor().anchor(),
                   "scroll": editor.verticalScrollBar().value(), "horizontal_scroll": editor.horizontalScrollBar().value()}
                  for editor in views],
        "active_view": int(document.views.active is document.views.secondary),
    }


def load_document_record(record):
    if not isinstance(record, dict) or not isinstance(record.get("text"), str):
        raise ValueError("Invalid document checkpoint.")
    text = record["text"]
    original = record.get("original", "")
    if not isinstance(original, str) or len(original) > ((MAX_BYTES + 2) // 3) * 4:
        raise ValueError("Invalid original-file checkpoint.")
    data = base64.b64decode(original, validate=True)
    if len(data) > MAX_BYTES or len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Recovered document exceeds 16 MiB.")
    path = record.get("path")
    if path is not None and (not isinstance(path, str) or not Path(path).is_absolute()):
        raise ValueError("Invalid recovered file path.")
    for key in ("encoding", "original_encoding"):
        if not isinstance(record.get(key), str):
            raise ValueError("Invalid recovered encoding.")
        codecs.lookup(record[key])
    if record.get("newline") not in (None, "\n", "\r", "\r\n", "\u2028", "\u2029"):
        raise ValueError("Invalid recovered line ending.")
    if record.get("bom") not in (None, "", "efbbbf", "fffe", "feff", "fffe0000", "0000feff"):
        raise ValueError("Invalid recovered BOM.")
    if not isinstance(record.get("modified"), bool) or not isinstance(record.get("language", "text"), str):
        raise ValueError("Invalid recovered document metadata.")
    if record.get("active_view", 0) not in (0, 1) or record.get("orientation", "horizontal") not in ("horizontal", "vertical"):
        raise ValueError("Invalid recovered view layout.")
    views = record.get("views", [])
    if not isinstance(views, list) or not 1 <= len(views) <= 2:
        raise ValueError("Invalid recovered views.")
    for view in views:
        if not isinstance(view, dict) or any(not isinstance(view.get(key, 0), int) or view.get(key, 0) < 0
                for key in ("position", "anchor", "scroll", "horizontal_scroll")):
            raise ValueError("Invalid recovered view position.")
    snapshot = decode_bytes(data, path=path, encoding=record["original_encoding"], force=True)
    external = False
    if path:
        try:
            disk = read_text_file(path, encoding=record["original_encoding"], force=True)
            if not record["modified"]:
                snapshot, text = disk, disk.text
            else:
                external = disk.original != snapshot.original
        except (OSError, ValueError):
            external = True
    modified = record["modified"] or external
    return record, snapshot, text, external, modified


class EditorSession(qt.QObject):
    def __init__(self, service, directory):
        super().__init__(service)
        self.service, self.directory = service, Path(directory)
        self.store = SessionStore(self.directory / (uuid4().hex + ".json"))
        self.lock = None
        self.claim = None
        self.executor = None
        self.future = None
        self.revision = 0
        self.persisted = -1
        self.error = ""
        self.suspended = False
        self.restoring = False
        self.retained = []
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.checkpoint)
        self.poll = qt.QTimer(self)
        self.poll.setInterval(25)
        self.poll.timeout.connect(self.finished)

    def start(self):
        if self.executor is None:
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="text-editor-recovery")
        if self.lock is None:
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                self.lock = qt.QLockFile(str(self.store.path.with_suffix(".lock")))
                self.lock.setStaleLockTime(0)
                if not self.lock.tryLock(0):
                    raise OSError("Could not lock the editor checkpoint.")
            except OSError as error:
                self.error = str(error)

    def changed(self, *args):
        if self.restoring or self.suspended or not self.service.windows:
            return
        self.revision += 1
        if not self.timer.isActive():
            self.timer.start(1000)

    def capture(self):
        documents = self.retained + [document_record(window.current) for window in self.service.windows
                     if window.current is not None and not getattr(window, "_suspending", False)]
        if len(documents) > 100:
            raise ValueError("Session recovery is limited to 100 documents.")
        active = self.service.windows.index(self.service.window) if self.service.window in self.service.windows else 0
        return {"version": 1, "documents": documents, "active": active}

    def checkpoint(self):
        if self.restoring or self.suspended or self.future is not None or not self.service.windows:
            return
        self.start()
        if self.lock is None or not self.lock.isLocked():
            return
        try:
            payload = self.capture()
            self.writing_revision = self.revision
            self.future = self.executor.submit(self.store.write, payload)
            self.poll.start()
        except (OSError, ValueError) as error:
            self.report(str(error))

    def report(self, error):
        self.error = error
        for window in tuple(self.service.windows):
            window.statusBar().showMessage("Recovery checkpoint failed: " + error, 10000)

    def finished(self):
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        self.poll.stop()
        try:
            future.result()
            self.persisted = self.writing_revision
            self.error = ""
            if self.claim is not None:
                path, lock = self.claim
                path.unlink(missing_ok=True)
                lock.unlock()
                self.claim = None
        except Exception as error:
            self.report(str(error))
        for window in tuple(self.service.windows):
            if getattr(window, "_recovery_waiting", False):
                window._recovery_waiting = False
                window._close_pending = False
                window.idle.emit()
        self.service.idle.emit()
        for window in tuple(self.service.windows):
            if getattr(window, "_suspend_requested", False) and not self.error:
                from commonUtils.ui.document_host import close_document
                qt.QTimer.singleShot(0, lambda owner=window: close_document(owner))
        if self.revision > self.persisted and not self.error:
            self.changed()

    def ensure_current(self, window):
        if self.error and self.future is None:
            # Preserve ordinary save/discard prompts if durable recovery is unavailable.
            self.report(self.error)
            return None
        if self.persisted >= self.revision and self.future is None:
            return True
        window._recovery_waiting = True
        window._close_pending = True
        self.timer.stop()
        self.checkpoint()
        return False

    def previous(self):
        self.start()
        candidates = sorted(self.directory.glob("*.json"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
        for path in candidates:
            if path == self.store.path:
                continue
            lock = qt.QLockFile(str(path.with_suffix(".lock")))
            lock.setStaleLockTime(0)
            if lock.tryLock(0):
                self.claim = path, lock
                return path
        return None

    def restore(self, window, path, requested=None):
        self.restoring = True
        def work():
            payload = SessionStore(path).read()
            return payload, [load_document_record(record) for record in payload["documents"]]
        def done(result):
            from .document import Document
            from .window import EditorWindow
            from commonUtils.ui.document_host import show_document
            payload, records = result
            restored = []
            seen = {owner.current.path for owner in self.service.windows if owner.current is not None and owner.current.path}
            for metadata, snapshot, text, external, modified in records:
                if snapshot.path and snapshot.path in seen:
                    from dataclasses import replace
                    snapshot = replace(snapshot, path=None)
                    modified = True
                if snapshot.path:
                    seen.add(snapshot.path)
                owner = window if not restored else EditorWindow(service=self.service, create_blank=False,
                    history_path=self.service.history_path, preferences_path=self.service.preferences_path)
                document = Document(snapshot)
                owner._add_document(document)
                document.editor.setPlainText(text)
                document.encoding = metadata["encoding"]
                document.newline_override = metadata.get("newline")
                document.bom_override = bytes.fromhex(metadata["bom"]) if metadata.get("bom") is not None else None
                document.language = metadata.get("language", "text")
                document.highlighter.configure(document.language if not document.simple else "text")
                document.editor.folding.configure(document.language)
                document.external_changed = external
                if external:
                    owner.external_notice.setText("The disk file changed or is unavailable since this session was saved. Compare or Save As before overwriting.")
                if len(metadata["views"]) == 2:
                    owner.split_document(qt.Qt.Orientation.Vertical if metadata.get("orientation") == "vertical" else qt.Qt.Orientation.Horizontal)
                views = [document.views.primary, document.views.secondary]
                for editor, view in zip(views, metadata["views"]):
                    if editor is None:
                        continue
                    limit = editor.document().characterCount() - 1
                    cursor = qt.QTextCursor(editor.document())
                    cursor.setPosition(min(limit, view.get("anchor", 0)))
                    cursor.setPosition(min(limit, view.get("position", 0)), qt.QTextCursor.MoveMode.KeepAnchor)
                    editor.setTextCursor(cursor)
                    editor.verticalScrollBar().setValue(view.get("scroll", 0))
                    editor.horizontalScrollBar().setValue(view.get("horizontal_scroll", 0))
                document.views.activate(views[min(int(metadata.get("active_view", 0)), len(metadata["views"]) - 1)])
                document.editor.document().setModified(modified)
                owner._watch_paths()
                owner._active_changed()
                show_document(owner)
                from shiboken6 import isValid
                for editor, view in zip(views, metadata["views"]):
                    if editor is None:
                        continue
                    def restore_scroll(editor=editor, view=view):
                        if isValid(editor):
                            editor.verticalScrollBar().setValue(view.get("scroll", 0))
                            editor.horizontalScrollBar().setValue(view.get("horizontal_scroll", 0))
                    qt.QTimer.singleShot(0, restore_scroll)
                restored.append(owner)
            self.restoring = False
            if not restored:
                window.new_document()
            active = payload.get("active", 0)
            active = active if isinstance(active, int) else 0
            self.service.window = restored[min(max(active, 0), len(restored) - 1)] if restored else window
            show_document(self.service.window)
            self.changed()
            self.checkpoint()
            if requested is not None:
                self.service.open(requested)
        def failed(error):
            self.restoring = False
            if self.claim is not None:
                self.claim[1].unlock()
                self.claim = None
            self.report(error)
            if window.current is None:
                window.new_document()
            if requested is not None:
                self.service.open(requested)
        window._run(work, done, failed, message="Restoring editor session…")

    def last_window_closed(self, suspended):
        self.timer.stop()
        self.poll.stop()
        if self.future is not None:
            try:
                self.future.result()
            except Exception:
                pass
            self.finished()
        self.timer.stop()
        if self.executor is not None:
            self.executor.shutdown(wait=True)
            self.executor = None
        if suspended or self.retained:
            self.suspended = True
        else:
            try:
                self.store.write({"version": 1, "documents": [], "active": 0})
            except (OSError, ValueError):
                pass
        if self.lock is not None:
            self.lock.unlock()
            self.lock = None

    def retain_window(self, window):
        if window.current is not None:
            self.retained.append(document_record(window.current))

    def restore_selected(self, window):
        if self.restoring or window.task.busy:
            return
        path, _ = qt.QFileDialog.getOpenFileName(window, "Restore Editor Session", str(self.directory), "Editor sessions (*.json)")
        if not path:
            return
        lock = qt.QLockFile(str(Path(path).with_suffix(".lock")))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            window.show_error("This session is in use by another editor instance.")
            return
        # Existing documents remain owned by their panes; restoration gets its own window.
        from .window import EditorWindow
        owner = EditorWindow(service=self.service, create_blank=False,
                             history_path=self.service.history_path, preferences_path=self.service.preferences_path)
        self.claim = Path(path), lock
        self.restore(owner, Path(path))
