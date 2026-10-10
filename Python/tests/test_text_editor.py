"""Editor document lifecycle and independence from optional reading features."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import unittest
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from features.text_editor.window import EditorWindow


class TextEditorTests(unittest.TestCase):
    def test_editor_contributes_settings_and_browser_actions_without_a_navigation_tab(self):
        from features.text_editor.contributions import register
        feature = register()
        self.assertEqual(feature.pages, [])
        self.assertTrue(feature.settings)
        self.assertTrue(feature.browser.actions)

    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.window = EditorWindow(
            history_path=self.root / "recent.json",
            preferences_path=self.root / "preferences.ini",
        )
        self.service = self.window.service
        self.addCleanup(self.cleanup)

    def cleanup(self):
        service = self.service
        for window in tuple(service.windows):
            self.window = window
            self.wait()
            for doc in window.documents:
                doc.editor.document().setModified(False)
            window.close()
            window.deleteLater()
        self.app.processEvents()

    def wait(self):
        deadline = monotonic() + 5
        while self.window.task.busy or self.window._queue:
            self.assertLess(monotonic(), deadline)
            self.app.processEvents()
            sleep(0.005)
        self.app.processEvents()

    def open(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        self.window.open_path(path)
        self.window = self.window.service.window
        self.wait()
        return path, self.window.current

    def test_open_save_round_trip_and_duplicate_documents(self):
        for name, data in [
            ("script.py", b"print(1)\r\n"),
            (".env", b"VAR=1\r"),
            ("bom", b"\xef\xbb\xbfcaf\xc3\xa9"),
        ]:
            path, doc = self.open(name, data)
            count = self.window.document_stack.count()
            self.window.open_path(path)
            self.wait()
            self.assertEqual(self.window.document_stack.count(), count)
            self.window.save_document()
            self.wait()
            self.assertEqual(path.read_bytes(), data)
            doc.editor.moveCursor(qt.QTextCursor.MoveOperation.End)
            doc.editor.insertPlainText(" more")
            self.window.save_document()
            self.wait()
            self.assertTrue(path.read_bytes().endswith(b" more"))

    def test_open_file_replaces_blank_and_new_keeps_existing_dirty_document(self):
        path, document = self.open('only.txt', b'Only file')
        self.assertEqual(self.window.documents, [document])
        self.assertEqual(document.path, path.resolve())
        self.assertEqual(self.window.findChildren(qt.QTabWidget), [])
        document.editor.insertPlainText('keep ')
        original = self.window
        new_window = original.new_document()
        self.assertIsNot(new_window, original)
        self.assertEqual(original.current.editor.toPlainText(), 'keep Only file')
        self.assertIsNone(new_window.current.path)
        self.assertEqual(len(original.service.windows), 2)
        self.window = new_window

    def test_repeated_open_during_loading_does_not_queue_a_second_buffer(self):
        path = self.root / 'loading.txt'; path.write_text('One buffer')
        self.window.open_path(path)
        self.assertIsNone(self.window.current)
        self.assertNotIn('Untitled', self.window.windowTitle())
        self.window.open_path(path)
        self.assertEqual(self.window._queue, [])
        self.wait()
        self.assertEqual(len(self.window.documents), 1)
        self.assertEqual(self.window.current.path, path.resolve())
        self.assertFalse(self.window.current.editor.isReadOnly())

    def test_save_all_and_close_all_apply_to_separate_editor_panes(self):
        first_path, first = self.open('first.txt', b'first')
        first_window = self.window
        second_path, second = self.open('second.txt', b'second')
        second_window = self.window
        first.editor.insertPlainText('new ')
        second.editor.insertPlainText('new ')
        service = self.window.service
        self.window.actions['save_all'].trigger()
        deadline = monotonic() + 5
        while any(window.task.busy for window in service.windows):
            self.assertLess(monotonic(), deadline)
            self.app.processEvents(); sleep(.005)
        self.assertEqual(first_path.read_text(), 'new first')
        self.assertEqual(second_path.read_text(), 'new second')
        first.editor.moveCursor(qt.QTextCursor.MoveOperation.Start)
        first.editor.insertPlainText('dirty ')
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
            self.window.actions['close_all'].trigger()
            self.assertEqual(service.windows, [first_window, second_window])
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Save):
            self.window.actions['close_all'].trigger()
            while service.windows:
                self.assertLess(monotonic(), deadline)
                self.app.processEvents(); sleep(.005)
        self.assertEqual(first_path.read_text(), 'dirty new first')
        # Both windows have accepted close and will be deleted; cleanup has no buffers left.

    def test_save_all_waits_for_another_editor_already_saving(self):
        first_path, first = self.open('first.txt', b'first')
        first_window = self.window
        second_path, second = self.open('second.txt', b'second')
        first.editor.insertPlainText('new ')
        second.editor.insertPlainText('new ')
        first_window.save_document()
        self.window.save_all()
        deadline = monotonic() + 5
        while any(window.task.busy for window in self.service.windows):
            self.assertLess(monotonic(), deadline)
            self.app.processEvents(); sleep(.005)
        self.assertEqual(first_path.read_text(), 'new first')
        self.assertEqual(second_path.read_text(), 'new second')

    def test_status_counts_unicode_characters_consistently_with_go_to(self):
        editor = self.window.current.editor
        editor.setPlainText('😀 text')
        cursor = editor.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(2, qt.QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        self.window._active_changed()
        self.assertIn('Col 2', self.window.position.text())
        self.assertIn('1 selected', self.window.position.text())

    def test_readonly_save_buffer_blocks_programmatic_undo(self):
        editor = self.window.current.editor
        editor.setPlainText("original")
        editor.moveCursor(qt.QTextCursor.MoveOperation.End)
        editor.textCursor().insertText(" changed")
        editor.setReadOnly(True)
        self.window.edit("undo")
        self.window.edit("cut")
        self.window.edit("paste")
        self.assertEqual(editor.toPlainText(), "original changed")
        editor.setReadOnly(False)
        self.window.edit("undo")
        self.assertEqual(editor.toPlainText(), "original")

    def test_unsaved_close_cancel_discard_save(self):
        doc = self.window.current
        doc.editor.insertPlainText("untitled")
        with patch.object(
            qt.QMessageBox,
            "question",
            return_value=qt.QMessageBox.StandardButton.Cancel,
        ):
            self.assertFalse(self.window.close_tab(0))
            self.assertTrue(doc.modified)
        path = self.root / "saved.txt"
        with (
            patch.object(
                qt.QMessageBox,
                "question",
                return_value=qt.QMessageBox.StandardButton.Save,
            ),
            patch.object(
                qt.QFileDialog, "getSaveFileName", return_value=(str(path), "")
            ),
        ):
            self.window.close_tab(0)
            self.wait()
        self.assertEqual(path.read_text(), "untitled")
        self.assertEqual(self.window.document_stack.count(), 0)

    def test_conflict_readonly_missing_and_binary_keep_buffer(self):
        path, doc = self.open("file", b"original")
        doc.editor.insertPlainText("edit")
        path.write_bytes(b"external")
        with patch.object(self.window, "show_error") as error:
            self.window.save_document()
            self.wait()
            error.assert_called_once()
        self.assertEqual(path.read_bytes(), b"external")
        self.assertTrue(doc.modified)
        doc.snapshot = __import__(
            "commonUtils.text_files", fromlist=["read_text_file"]
        ).read_text_file(path)
        path.chmod(0o444)
        with patch.object(self.window, "show_error") as error:
            self.window.save_document()
            self.wait()
            self.assertIn("read-only", error.call_args.args[0])
        path.chmod(0o644)
        path.unlink()
        with patch.object(self.window, "show_error") as error:
            self.window.save_document()
            self.wait()
            self.assertIn("deleted", error.call_args.args[0])
        binary = self.root / "binary"
        binary.write_bytes(b"a\0b")
        count = self.window.document_stack.count()
        with patch.object(
            qt.QMessageBox, "warning", return_value=qt.QMessageBox.StandardButton.Cancel
        ):
            owner = self.window
            self.window.open_path(binary)
            failed_window = self.window.service.window
            self.window = failed_window; self.wait()
            self.window = owner
        self.assertEqual(self.window.document_stack.count(), count)
        self.window.open_path(binary, force=True)
        self.window = self.window.service.window
        self.wait()
        self.assertEqual(self.window.current.editor.toPlainText(), "a\0b")

    def test_feature_has_no_dependencies_and_preserves_markdown_activation(self):
        from features import registry, text_editor
        from features.text_editor.contributions import activate_text
        from commonUtils.features import ActionContext
        from commonUtils.fileTypes.markdownType import MarkdownFile
        from commonUtils.fileUtils import File

        self.assertEqual(registry.get_feature_dependencies(text_editor), ())
        path = self.root / "note.md"
        path.write_text("# note")
        self.assertFalse(
            activate_text(ActionContext(None, None, None, (MarkdownFile(path),)))
        )
        self.assertTrue(activate_text(ActionContext(None, None, None, (File(path),))))
        with (
            patch.object(registry, "load_features", return_value=[text_editor]),
            patch.object(registry, "_disabled_features", set()),
            patch.object(registry, "_initialized_features", set()),
        ):
            registry.set_feature_enabled("text_editor", False)
            self.assertFalse(registry.is_feature_enabled("text_editor"))
            registry.set_feature_enabled("text_editor", True)
            self.assertTrue(registry.is_feature_enabled("text_editor"))

    def test_status_conversions_preferences_and_themes_preserve_source(self):
        path, doc = self.open("config.py", b"value = 1\r\n")
        self.assertEqual(doc.language, "python")
        self.assertEqual(self.window.endings_button.text(), "CRLF")
        palette = doc.editor.palette()
        palette.setColor(qt.QPalette.ColorRole.Base, qt.QColor("#111111"))
        doc.editor.setPalette(palette)
        self.app.processEvents()
        self.assertFalse(doc.modified)
        self.window.actions["wrap"].setChecked(True)
        self.window.toggle_option("wrap")
        doc.editor.set_font_size(16)
        self.window._save_preferences()
        from features.text_editor.preferences import Preferences

        loaded = Preferences(self.root / "preferences.ini").load()
        self.assertEqual(loaded["font_size_int"], 16)
        self.assertTrue(loaded["word_wrap_bool"])
        with patch.object(qt.QInputDialog, "getItem", return_value=("LF", True)):
            self.window.choose_endings()
        self.window.save_document()
        self.wait()
        self.assertEqual(path.read_bytes(), b"value = 1\n")
        with patch.object(qt.QInputDialog, "getItem", return_value=("utf-8-sig", True)):
            self.window.choose_encoding()
        self.window.save_document()
        self.wait()
        self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
        with patch.object(qt.QInputDialog, "getText", return_value=("1:3", True)):
            self.window.go_to()
        self.assertEqual(doc.editor.textCursor().positionInBlock(), 2)
        before = doc.editor.toPlainText()
        doc.editor.setReadOnly(True)
        self.window.edit("duplicate")
        self.assertEqual(doc.editor.toPlainText(), before)

    def test_files_have_independent_editor_panes_and_reopening_reuses_the_document(self):
        service = self.window.service
        first = self.root / 'first'; first.write_text('first')
        second = self.root / 'second'; second.write_text('second')
        first_window = service.open(first)
        second_window = service.open(second)
        self.assertIsNot(first_window, second_window)
        for window in (first_window, second_window):
            self.window = window; self.wait()
            self.assertEqual(len(window.documents), 1)
            self.assertEqual(window.findChildren(qt.QTabWidget), [])
        self.assertIs(service.open(first), first_window)
        self.assertEqual(len(service.windows), 2)
        self.assertEqual(first_window.current.editor.toPlainText(), 'first')
        self.assertEqual(second_window.current.editor.toPlainText(), 'second')
        second_window._external_change(str(second.resolve()))
        self.assertTrue(second_window.current.external_changed)
        self.assertFalse(first_window.current.external_changed)
        first_window.current.editor.insertPlainText('keep')
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
            self.assertFalse(service.prepare_close())
            self.assertIn(first_window, service.windows)
            self.assertEqual(first_window.current.editor.toPlainText(), 'keepfirst')
        self.window = first_window

    def test_legacy_decoding_force_and_unicode_separator_save(self):
        path = self.root / "legacy"
        path.write_bytes(b"caf\xe9\r\n")
        with patch.object(qt.QInputDialog, "getItem", return_value=("cp1252", True)):
            self.window.open_path(path)
            self.wait()
        self.assertEqual(self.window.current.editor.toPlainText(), "café\n")
        self.window.save_document()
        self.wait()
        self.assertEqual(path.read_bytes(), b"caf\xe9\r\n")
        path, doc = self.open("paragraphs", "one\u2029two".encode())
        self.window.save_document()
        self.wait()
        self.assertEqual(path.read_bytes(), "one\u2029two".encode())
        self.assertTrue(qt.QFontInfo(doc.editor.font()).fixedPitch())

    def test_real_browser_activation_and_disable_reenable_reuse_buffers(self):
        from features.text_editor import register
        from features.text_editor.service import EditorService
        from commonUtils.fileUtils import File
        from commonUtils.fileTypes.markdownType import MarkdownFile
        from ui_new.file_browser import FileBrowserWindow
        from features import registry

        service = self.window.service
        with patch.object(registry, "get_browser_extensions", return_value=[]):
            host = FileBrowserWindow(self.root)
        definition = register()
        with patch("features.text_editor.service.editor_service", return_value=service):
            binding = definition.install_browser(host.file_browser, host=host)
        path = self.root / "script.py"
        path.write_text("print(1)")
        self.assertTrue(binding._activate(File(path), None))
        self.wait()
        doc = self.window.current
        doc.editor.insertPlainText("# keep\n")
        definition.set_enabled(False)
        self.assertFalse(binding._activate(File(path), None))
        self.assertTrue(doc.modified)
        definition.set_enabled(True)
        self.assertTrue(binding._activate(File(path), None))
        self.wait()
        self.assertIs(self.window.current, doc)
        markdown = self.root / "note.md"
        markdown.write_text("# note")
        self.assertFalse(binding._activate(MarkdownFile(markdown), None))
        deadline = monotonic() + 5
        while not host.prepare_close():
            self.assertLess(monotonic(), deadline)
            self.app.processEvents()
            sleep(0.005)
        host.close()
        host.deleteLater()
        self.app.processEvents()

    def test_bom_removal_and_optional_history_failure(self):
        path, doc = self.open("bom.txt", b"\xef\xbb\xbftext")
        with patch.object(qt.QInputDialog, "getItem", return_value=("utf-8", True)):
            self.window.choose_encoding()
        with patch.object(
            self.window.recent, "add", side_effect=OSError("history unavailable")
        ):
            self.window.save_document()
            self.wait()
        self.assertEqual(path.read_bytes(), b"text")
        self.assertFalse(doc.modified)
