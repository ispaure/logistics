import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import unittest
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from commonUtils.session_store import SessionStore
from commonUtils.text_files import decode_bytes
from features.text_editor.document import Document
from features.text_editor.service import EditorService
from features.text_editor.session import document_record, load_document_record


class EditorRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.services = []

    def service(self):
        service = EditorService(self.app, history_path=self.root / "recent.json",
                                preferences_path=self.root / "preferences.ini")
        self.services.append(service)
        return service

    def wait(self, predicate):
        end = monotonic() + 8
        while not predicate():
            self.assertLess(monotonic(), end)
            self.app.processEvents()
            sleep(.005)
        self.app.processEvents()

    def tearDown(self):
        for service in self.services:
            service.session.timer.stop()
            for window in tuple(service.windows):
                self.wait(lambda: not window.task.busy)
                window._suspend_requested = False
                window._suspending = False
                for document in window.documents:
                    document.editor.document().setModified(False)
                window.close()
            service.session.timer.stop()
            service.deleteLater()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def test_late_checkpoint_after_last_window_closes_does_not_reopen_session_lock(self):
        service = self.service()
        service.open()
        service.open()
        service.close_all()
        self.wait(lambda: not service.windows)
        session = service.session
        try:
            # Deferred document/scroll signals and an already queued timeout can
            # arrive after close. They must not create an orphan recovery writer.
            session.changed()
            session.checkpoint()
            self.assertIsNone(session.lock)
            self.assertIsNone(session.executor)
            self.assertFalse(session.timer.isActive())
            self.assertFalse(session.store.path.with_suffix('.lock').exists())
            service.open()
            self.assertTrue(session.lock.isLocked())
        finally:
            if not service.windows:
                session.last_window_closed(False)

    def test_suspend_restore_unsaved_views_cursor_and_original_disk_conflict(self):
        service = self.service()
        path = self.root / "bom.txt"
        path.write_bytes(b"\xef\xbb\xbforiginal\r\n")
        owner = service.open(path)
        self.wait(lambda: not owner.task.busy)
        document = owner.current
        document.editor.insertPlainText("unsaved ")
        owner.split_document(qt.Qt.Orientation.Vertical)
        document.editor.moveCursor(qt.QTextCursor.MoveOperation.End)
        position = document.editor.textCursor().position()
        blank = service.open()
        blank.current.editor.insertPlainText("scratch 😀")
        checkpoint = service.session.store.path
        service.suspend()
        self.wait(lambda: not service.windows)
        self.assertEqual(path.read_bytes(), b"\xef\xbb\xbforiginal\r\n")
        self.assertTrue(checkpoint.exists())
        path.write_text("external version")
        resumed = self.service()
        owner = resumed.open()
        self.wait(lambda: not owner.task.busy and len(resumed.windows) == 2)
        recovered = next(w for w in resumed.windows if w.current.path == path)
        document = recovered.current
        self.assertEqual(document.editor.toPlainText(), "unsaved original\n")
        self.assertTrue(document.modified)
        self.assertTrue(document.external_changed)
        self.assertEqual(document.snapshot.original, b"\xef\xbb\xbforiginal\r\n")
        self.assertEqual(document.editor.textCursor().position(), position)
        self.assertIsNotNone(document.views.secondary)
        self.assertEqual(document.views.splitter.orientation(), qt.Qt.Orientation.Vertical)
        self.assertEqual(next(w.current.editor.toPlainText() for w in resumed.windows if w.current.path is None), "scratch 😀")
        with patch.object(recovered, "show_error") as error:
            recovered.save_document()
            self.wait(lambda: not recovered.task.busy)
            error.assert_called_once()
        self.assertEqual(path.read_text(), "external version")
        self.wait(lambda: resumed.session.future is None and resumed.session.persisted >= 0)
        self.assertFalse(checkpoint.exists())

    def test_live_session_lock_and_corrupt_session_preservation(self):
        first = self.service()
        first.open().current.editor.insertPlainText("live")
        first.session.checkpoint()
        self.wait(lambda: first.session.future is None and first.session.persisted >= 0)
        second = self.service()
        self.assertIsNone(second.session.previous())
        corrupt = first.session.directory / "corrupt.json"
        corrupt.write_text('{broken')
        second.open()
        self.wait(lambda: not second.window.task.busy)
        self.assertIn("Recovery checkpoint failed", second.window.statusBar().currentMessage())
        self.assertEqual(corrupt.read_text(), '{broken')

    def test_clean_file_changes_missing_file_and_invalid_metadata(self):
        path = self.root / "a.txt"
        path.write_text("old")
        document = Document(decode_bytes(b"old", path=path))
        record = document_record(document)
        path.write_text("new")
        self.assertEqual(load_document_record(record)[2], "new")
        path.unlink()
        restored = load_document_record(record)
        self.assertEqual(restored[2], "old")
        self.assertTrue(restored[4])
        for key, value in (("views", []), ("active_view", "bad"), ("newline", "bad"), ("encoding", "unknown-codec")):
            invalid = dict(record, **{key: value})
            with self.assertRaises((ValueError, LookupError)):
                load_document_record(invalid)
        document.deleteLater()

    def test_failed_checkpoint_falls_back_to_normal_close_prompts(self):
        service = self.service()
        owner = service.open()
        owner.current.editor.insertPlainText("keep me")
        owner._suspend_requested = True
        with patch.object(service.session.store, "write", side_effect=OSError("disk full")):
            self.assertFalse(owner.close())
            self.wait(lambda: service.session.future is None)
            with patch("commonUtils.ui.pyside.QMessageBox.question", return_value=qt.QMessageBox.StandardButton.Cancel) as question:
                self.assertFalse(owner.close())
                question.assert_called_once()
        self.assertEqual(owner.current.editor.toPlainText(), "keep me")

    def test_host_shutdown_keeps_session_without_saving_original(self):
        from ui_new.documents import DocumentsPage
        from commonUtils.ui.document_host import register_document_host
        host = DocumentsPage(lambda: None)
        register_document_host(host)
        try:
            service = self.service()
            owner = service.open()
            owner.current.editor.insertPlainText("recover hosted")
            saved_path = service.session.store.path
            host.closing = True
            self.assertFalse(owner.prepare_close())
            self.wait(lambda: owner.prepare_close())
            self.assertTrue(owner._suspending)
            owner.close()
            self.assertEqual(SessionStore(saved_path).read()["documents"][0]["text"], "recover hosted")
        finally:
            if hasattr(self.app, "_commonutils_document_host"):
                del self.app._commonutils_document_host
            host.deleteLater()

    def test_crash_checkpoint_restore_and_normal_discard_removes_buffer(self):
        service = self.service()
        owner = service.open()
        owner.current.editor.insertPlainText("crash buffer")
        service.session.checkpoint()
        self.wait(lambda: service.session.future is None and service.session.persisted >= 0)
        # A released process lock represents termination after a completed checkpoint.
        service.session.lock.unlock()
        resumed = self.service()
        restored = resumed.open()
        self.wait(lambda: not restored.task.busy and restored.current is not None)
        self.assertEqual(restored.current.editor.toPlainText(), "crash buffer")
        self.assertTrue(restored.current.modified)
        with patch("commonUtils.ui.pyside.QMessageBox.question", return_value=qt.QMessageBox.StandardButton.Discard):
            restored.close()
        self.assertEqual(SessionStore(resumed.session.store.path).read()["documents"], [])
        service.session.lock.tryLock(0)

    def test_checkpoint_retains_already_suspended_panes_while_others_change(self):
        service = self.service()
        first = service.open()
        first.current.editor.insertPlainText("first")
        second = service.open()
        second.current.editor.insertPlainText("second")
        first._suspend_requested = True
        first.close()
        self.wait(lambda: first not in service.windows)
        second.current.editor.insertPlainText(" changed")
        service.session.checkpoint()
        self.wait(lambda: service.session.future is None)
        payload = service.session.store.read()
        self.assertEqual([record["text"] for record in payload["documents"]], ["first", "second changed"])
        service.suspend()
        self.wait(lambda: not service.windows)

    def test_scroll_positions_restore_after_layout(self):
        service = self.service()
        owner = service.open()
        owner.current.editor.setPlainText("\n".join(f"line {i}" for i in range(1000)))
        owner.split_document(qt.Qt.Orientation.Vertical)
        self.app.processEvents()
        primary = owner.current.views.primary
        secondary = owner.current.views.secondary
        primary.verticalScrollBar().setValue(100)
        secondary.verticalScrollBar().setValue(70)
        service.suspend()
        self.wait(lambda: not service.windows)
        resumed = self.service()
        owner = resumed.open()
        self.wait(lambda: not owner.task.busy and owner.current is not None)
        self.app.processEvents()
        self.assertEqual(owner.current.views.primary.verticalScrollBar().value(), 100)
        self.assertEqual(owner.current.views.secondary.verticalScrollBar().value(), 70)
