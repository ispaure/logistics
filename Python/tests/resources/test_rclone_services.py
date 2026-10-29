"""Credential service scope, generation isolation and requested-lock edit guards."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from features.rclone import session
from features.rclone.desktop_service import service
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from services.documents.ui.private_views import prepare_credential_lock, protect_private_view


class RcloneServiceTests(QtTestCase):
    def test_package_lock_revokes_children_but_not_other_package_or_saved_zip(self):
        with TemporaryDirectory() as root:
            root = Path(root)
            package = root / 'Personal.zip'
            package.write_bytes(b'opaque fixture')
            key, other, child = (root / name for name in ('Personal.session', 'Other.session', 'reader.session'))
            session.remember(key, {}, package_path=package)
            session.remember(other, {})
            session.remember(child, {}, parent=key, private=True)
            self.addCleanup(session.forget, other)
            grant = service.credentials.capture(child)
            self.assertTrue(session.registry.depends_on(child, key))
            service.credentials.lock(key)
            with self.assertRaisesRegex(ValueError, 'locked'):
                grant.check()
            self.assertIsNotNone(session.credentials(other))
            self.assertEqual(package.read_bytes(), b'opaque fixture')
            session.remember(key, {}, package_path=package)
            self.addCleanup(session.forget, key)
            with self.assertRaises(ValueError):
                grant.check()

    def test_requested_lock_honors_dirty_editor_cancel_and_discard(self):
        with TemporaryDirectory() as root:
            key, child = Path(root) / 'account.session', Path(root) / 'reader.session'
            session.remember(key, {})
            session.remember(child, {}, parent=key, private=True)
            self.addCleanup(session.forget, key)
            window = qt.QMainWindow()
            window.save = lambda: self.fail('Unexpected save request')
            window.editor = qt.QPlainTextEdit()
            window.editor.document().setModified(True)
            provider = type('Provider', (), dict(private=True, context=child))()
            protect_private_view(window, provider)
            window.show()
            self.addCleanup(window.deleteLater)
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
                self.assertFalse(prepare_credential_lock([key]))
            self.assertIsNotNone(session.credentials(key))
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Discard):
                self.assertTrue(prepare_credential_lock([key]))
                service.credentials.lock(key)
            qt.QApplication.instance().processEvents()
            self.assertFalse(window.isVisible())
            self.assertTrue(window._private_view_guard.locked)

    def test_unrelated_dirty_document_does_not_block_package_lock(self):
        with TemporaryDirectory() as root:
            key, other = Path(root) / 'account.session', Path(root) / 'other.session'
            session.remember(key, {})
            session.remember(other, {})
            self.addCleanup(session.forget, key)
            self.addCleanup(session.forget, other)
            window = qt.QMainWindow()
            window.save = lambda: self.fail('Unexpected save request')
            window.editor = qt.QPlainTextEdit()
            window.editor.document().setModified(True)
            provider = type('Provider', (), dict(private=True, context=other))()
            protect_private_view(window, provider)
            self.addCleanup(window.deleteLater)
            with patch.object(qt.QMessageBox, 'question', side_effect=AssertionError('Unrelated prompt')):
                self.assertTrue(prepare_credential_lock([key]))
