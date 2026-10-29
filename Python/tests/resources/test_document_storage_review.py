"""Storage policy follows Save As and rejects stale credential generations."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.rclone import session
from services.documents.ui.private_views import protect_private_view


class StorageTransitionTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_ordinary_editor_follows_private_save_as_on_idle(self):
        class Window(qt.QMainWindow):
            idle = qt.Signal()
        with TemporaryDirectory() as directory:
            context = Path(directory) / 'private.session'
            session.remember(context, {'view': {'type': 'local'}})
            self.addCleanup(session.forget, context)
            window = Window()
            window.choice = SimpleNamespace(provider=SimpleNamespace(private=False))
            protect_private_view(window, window.choice.provider)
            window.show()
            window.choice = SimpleNamespace(provider=SimpleNamespace(private=True, context=context))
            window.idle.emit()
            self.assertIs(window._private_view_guard.provider, window.choice.provider)
            session.forget(context)
            self.app.processEvents()
            self.assertFalse(window.isVisible())
            self.assertFalse(window.isEnabled())
            window.close()

    def test_guard_checks_provider_generation_even_after_credentials_are_replaced(self):
        with TemporaryDirectory() as directory:
            context = Path(directory) / 'replaced.session'
            session.remember(context, {'view': {'type': 'local'}})
            self.addCleanup(session.forget, context)
            provider = SimpleNamespace(private=True, context=context, _check_active=Mock())
            window = qt.QMainWindow()
            protect_private_view(window, provider)
            window.show()
            provider._check_active.side_effect = ValueError('Stale credential generation')
            window._private_view_guard.check_revocation()
            self.assertIsNotNone(session.credentials(context))
            self.assertFalse(window.isEnabled())
            self.assertFalse(window.isVisible())
            window.close()

    def test_registration_after_revocation_retires_the_window_immediately(self):
        with TemporaryDirectory() as directory:
            window = qt.QMainWindow()
            provider = SimpleNamespace(private=True, context=Path(directory) / 'already-locked.session')
            protect_private_view(window, provider)
            self.assertTrue(window._private_view_guard.locked)
            self.assertFalse(window.isEnabled())
            window.close()

    def test_first_notebook_save_installs_the_private_guard(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from features.notebooks.notebook import Notebook, MAX_ARCHIVE
        from features.notebooks.storage import NotebookDocument
        from features.notebooks.ui.workspace import NotebookWorkspace, NotebookWindow
        from services.documents.storage import DocumentResource
        with TemporaryDirectory() as directory:
            provider = LocalFiles(directory)
            provider.private, provider.context = True, Path(directory) / 'first-save.session'
            session.remember(provider.context, {'view': {'type': 'local'}})
            self.addCleanup(session.forget, provider.context)
            window = NotebookWindow()
            panel = NotebookWorkspace(window, library=False)
            window.setCentralWidget(panel)
            panel.editor, panel.operation, panel._pending_choice = SimpleNamespace(checkpoint=None), Mock(), None
            from features.notebooks.bridge import Bridge
            panel.bridge = panel._pending_canvas = Bridge()
            panel._pending_operation = panel.operation
            document = NotebookDocument(Notebook.new(), resource=DocumentResource(provider, 'Saved.rmdoc', max_bytes=MAX_ARCHIVE))
            panel.saved(document, None)
            self.assertIs(window._private_view_guard.provider, provider)
            session.forget(provider.context)
            self.app.processEvents()
            self.assertIsNone(panel.document)
            self.assertFalse(window.isEnabled())
            window.close()

    def test_markdown_save_as_switches_privacy_title_and_revocation_guard(self):
        import time
        from unittest.mock import patch
        from commonUtils.runtime.resources.local import LocalFiles
        from features.rclone import executable
        from tests.local_crypt_fixture import crypt_fixture
        from services.documents.ui.markdown import MarkdownStorage, PrivateMarkdownWindow
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone executable not installed')
        with TemporaryDirectory() as directory, crypt_fixture(directory, binary) as fixture:
            path = fixture.plain / 'note.md'
            storage = MarkdownStorage(LocalFiles(fixture.plain), path, fixture.original, {}, lambda *_: None)
            window = PrivateMarkdownWindow(path, storage)
            window.viewer.edit_mode.setCurrentIndex(window.viewer.edit_mode.findData('source'))
            window.viewer.editor.setPlainText('# Became private')
            window.viewer.editor.document().setModified(True)
            try:
                self.assertFalse(window._session_private)
                with patch('services.documents.ui.markdown.choose_destination',
                           return_value=(fixture.provider, 'became-private.md', lambda: None)):
                    window.viewer.save_as_dialog()
                deadline = time.monotonic() + 30
                while storage.operation.busy and time.monotonic() < deadline:
                    self.app.processEvents()
                    time.sleep(.01)
                self.assertFalse(storage.operation.busy)
                self.assertEqual(fixture.provider.read_bytes('became-private.md'), b'# Became private')
                self.assertTrue(window._session_private)
                self.assertIn('Private', window.windowTitle())
                self.assertIs(window._private_view_guard.provider, fixture.provider)
                session.forget(fixture.context)
                self.app.processEvents()
                self.assertFalse(window.isEnabled())
                self.assertEqual(window.viewer.editor.toPlainText(), '')
                self.assertEqual(window.viewer.formatted_editor.toPlainText(), '')
                self.assertEqual(storage.data, b'')
                self.assertTrue(storage.resource.closed)
                self.assertIsNone(window.viewer.document_state.source_bytes)
            finally:
                window.viewer.editor.document().setModified(False)
                window.close()

    def test_invalid_notebook_open_releases_resource_and_failed_window(self):
        from features.notebooks.ui.workspace import open_workspace, _windows
        before = list(_windows)
        resource = Mock()
        resource.read.return_value = b'Invalid notebook archive'
        with self.assertRaises(ValueError):
            open_workspace(resource=resource)
        resource.close.assert_called_once()
        self.assertEqual(_windows, before)

    def test_late_markdown_save_acknowledgement_cannot_revive_revoked_content(self):
        from services.documents.ui.markdown import MarkdownStorage
        completed = Mock()
        storage = SimpleNamespace(window=SimpleNamespace(viewer=Mock(), idle=Mock(), pending_close=False,
                                  _private_view_guard=SimpleNamespace(locked=True)),
                                  pending_write=(b'Private snapshot', completed), operation=Mock())
        MarkdownStorage._written(storage, None, None)
        self.assertIn('locked', completed.call_args.args[0])
        storage.window.viewer.setEnabled.assert_called_once_with(False)
