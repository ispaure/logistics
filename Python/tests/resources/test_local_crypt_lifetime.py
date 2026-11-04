"""Ciphertext mirror, streaming readers/editors, private UI and credential lifetime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from features.rclone import executable
from features.rclone.localcrypt import backend as local_crypt
from features.rclone.localcrypt import mapping as copy_mapping
from features.rclone import session
from tests.local_crypt_fixture import crypt_fixture


from tests.resources.localcrypt_cases import LocalCryptCase


class LocalCryptLifetimeTests(LocalCryptCase):
    def test_service_open_views_close_independently_and_lock_together(self):
        from features.rclone.desktop_service import service
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f, patch.object(
                executable, 'get_rclone_path', return_value=self.binary):
            first = service.localcrypt.open(f.item)
            second = service.localcrypt.open(f.item)
            self.addCleanup(first.close)
            self.addCleanup(second.close)
            browser_release = first.acquire()
            reader_release = first.acquire()
            browser_release()
            self.assertFalse(first.closed)
            self.assertEqual(first.read_bytes('note.md'), f.original)
            reader_release()
            self.assertTrue(first.closed)
            self.assertEqual(second.read_bytes('note.md'), f.original)
            service.credentials.lock(f.context)
            self.assertTrue(second.closed)
            with self.assertRaisesRegex(ValueError, 'locked'):
                second.read_bytes('note.md')

    def test_revocation_retires_private_window_and_blocks_reshow(self):
        from services.documents.ui.private_views import protect_private_view
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            window = qt.QMainWindow()
            window.setWindowTitle('Secret document sentinel')
            protect_private_view(window, f.provider)
            window.show()
            self.app.processEvents()
            session.forget(f.context)
            self.app.processEvents()
            self.assertFalse(window.isVisible())
            self.assertFalse(window.isEnabled())
            self.assertNotIn('sentinel', window.windowTitle())
            window.show()
            self.app.processEvents()
            self.assertFalse(window.isVisible())
            window.close()

    def test_private_view_guard_follows_save_as_provider(self):
        from types import SimpleNamespace
        from services.documents.ui.private_views import protect_private_view
        with TemporaryDirectory() as directory:
            first = SimpleNamespace(private=True, context=Path(directory) / 'first.session')
            second = SimpleNamespace(private=True, context=Path(directory) / 'second.session')
            for provider in (first, second):
                session.remember(provider.context, {'view': {'type': 'local'}})
                from features.rclone.document_protection import DesktopDocumentProtection
                provider.document_protection = DesktopDocumentProtection(provider)
                self.addCleanup(session.forget, provider.context)
            window = qt.QMainWindow()
            window.choice = SimpleNamespace(provider=first)
            protect_private_view(window, first)
            window.show()
            # ResourceTextWindow releases the old choice before publishing the
            # new choice. Its pending Save As destination owns the displayed draft.
            window.pending_choice = SimpleNamespace(provider=second)
            session.forget(first.context)
            self.app.processEvents()
            self.assertTrue(window.isVisible())
            window.choice, window.pending_choice = window.pending_choice, None
            session.forget(second.context)
            self.app.processEvents()
            self.assertFalse(window.isVisible())
            window.close()

    def test_forgetting_parent_removes_private_keys_and_reunlock_requires_new_provider(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            private_context = f.provider.context
            self.assertIsNotNone(session.credentials(private_context))
            session.forget(f.context)
            self.assertIsNone(session.credentials(private_context))
            copy_mapping.unlock(f.item, 'synthetic-package-password')
            with self.assertRaisesRegex(ValueError, 'Reopen'):
                f.provider.read_bytes('note.md')
            with_provider = local_crypt.CryptResources(f.item, binary=self.binary)
            try:
                self.assertEqual(with_provider.read_bytes('note.md'), f.original)
            finally:
                with_provider.close()

    def test_provider_owners_release_keys_only_after_last_document(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            browser = f.provider.acquire()
            document = f.provider.acquire()
            browser()
            browser()  # Closing plus destruction is safe.
            self.assertEqual(f.provider.read_bytes('note.md'), f.original)
            document()
            self.assertIsNone(session.credentials(f.provider.context))
            self.assertTrue(f.provider.closed)

    def test_cancelled_open_never_presents_a_document(self):
        from threading import Event
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        with self.temporary_directory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            with patch('features.rclone.localcrypt.ui.views.executable.get_rclone_path', return_value=self.binary):
                view = CryptBrowserView(f.item)
                self.wait_until(lambda: not view.file_browser.operation.busy)
                entered, finish = Event(), Event()
                def prepare(provider, path):
                    entered.set()
                    finish.wait(5)
                    return f.original, {}
                with patch('features.rclone.localcrypt.ui.views.prepare_markdown', side_effect=prepare), \
                     patch('features.rclone.localcrypt.ui.views.show_document') as show:
                    view.open_document(f.item.data / 'note.md')
                    self.wait_until(entered.is_set)
                    view.open_operation.request_cancel()
                    finish.set()
                    self.wait_until(lambda: not view.open_operation.busy)
                    show.assert_not_called()
                context = view.provider.context
                # Closing may be deferred while an owned preview/listing worker
                # retires. Exercise that state deliberately instead of racing
                # the machine's completion speed and assuming close succeeded.
                pending, cancelled = Event(), Event()
                pending.set()
                view.file_browser.operations.own(pending, busy=pending.is_set, cancel=cancelled.set)
                try:
                    self.assertFalse(view.close())
                    self.assertTrue(cancelled.is_set())
                    self.assertIsNotNone(session.credentials(context))
                finally:
                    pending.clear()
                self.wait_until(view.close, message='Private browser did not finish cooperative close')
                self.assertIsNone(session.credentials(context))
