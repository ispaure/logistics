"""Ciphertext mirror, streaming readers/editors, private UI and credential lifetime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from tests.local_crypt_fixture import crypt_fixture


from tests.resources.localcrypt_cases import LocalCryptCase
from threading import Event
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock


class MarkdownCompletionTests(TestCase):
    """Use real resource ownership with fake media; never start a transport."""

    def setUp(self):
        from services.documents.markdown import MarkdownResources
        from features.rclone.localcrypt.ui import views
        self.views = views
        self.resources = MarkdownResources()
        self.media = Mock()
        self.resources.media = self.media
        self.resources['synthetic-image'] = b'synthetic image bytes'
        self.resources.videos['synthetic-video'] = 'synthetic handle'
        self.resources.errors['synthetic-error'] = 'synthetic message'
        self.addCleanup(self.resources.close)
        self.result = 'markdown', (b'# Synthetic private document', self.resources)
        self.release = Mock()
        self.host = SimpleNamespace(closing=False, open_operation=SimpleNamespace(cancelled=Event(), hide=Mock()),
                                    idle=Mock(), pending_document=(Path('/synthetic/note.md'), '', None),
                                    pending_markdown_edit=False, provider=Mock(acquire=Mock(return_value=self.release)),
                                    _open_link=Mock())
        self.storage = self.enterContext(patch.object(views, 'MarkdownStorage'))
        self.window = self.enterContext(patch.object(views, 'PrivateMarkdownWindow'))
        self.show = self.enterContext(patch.object(views, 'show_document'))
        self.enterContext(patch.object(views, '_windows', []))

    def complete(self, error=''):
        self.views.CryptBrowserView._opened(self.host, self.result, error)

    def assert_retired(self):
        self.media.close.assert_called_once_with()
        self.assertIsNone(self.resources.media)
        self.assertFalse(self.resources)
        self.assertFalse(self.resources.videos)
        self.assertFalse(self.resources.errors)
        self.show.assert_not_called()

    def test_cancelled_completion_closes_media_once(self):
        self.host.open_operation.cancelled.set()
        self.complete()
        self.assert_retired()
        self.host.idle.emit.assert_called_once_with()
        self.storage.assert_not_called()
        self.complete()  # Retained operation results can be discarded again safely.
        self.media.close.assert_called_once_with()

    def test_closing_completion_closes_media(self):
        self.host.closing = True
        self.complete()
        self.assert_retired()
        self.host.idle.emit.assert_called_once_with()

    def test_failed_completion_closes_unpublished_media(self):
        self.complete('synthetic opening failure')
        self.assert_retired()
        self.storage.assert_not_called()

    def test_failed_storage_handoff_closes_media(self):
        self.storage.side_effect = ValueError('synthetic storage failure')
        with self.assertRaisesRegex(ValueError, 'synthetic storage failure'):
            self.complete()
        self.assert_retired()
        self.host.provider.acquire.assert_not_called()

    def test_revoked_acquire_closes_media(self):
        self.host.provider.acquire.side_effect = ValueError('synthetic locked provider')
        with self.assertRaisesRegex(ValueError, 'synthetic locked provider'):
            self.complete()
        self.assert_retired()
        self.window.assert_not_called()

    def test_failed_window_handoff_closes_media_and_releases_provider(self):
        self.window.side_effect = ValueError('synthetic window failure')
        with self.assertRaisesRegex(ValueError, 'synthetic window failure'):
            self.complete()
        self.assert_retired()
        self.release.assert_called_once_with()

    def test_successful_window_handoff_preserves_media_and_lease(self):
        self.complete()
        self.storage.assert_called_once_with(self.host.provider, self.host.pending_document[0],
                                            self.result[1][0], self.resources, self.host._open_link)
        self.media.close.assert_not_called()
        self.release.assert_not_called()
        self.assertIs(self.resources.media, self.media)
        self.assertTrue(self.resources)
        self.show.assert_called_once_with(self.window.return_value)
        self.window.return_value.destroyed.connect.assert_any_call(self.release)
        self.host.open_operation.hide.assert_called_once_with()

    def test_cleanup_failure_does_not_replace_handoff_failure(self):
        failure = ValueError('synthetic window failure')
        cleanup_failure = RuntimeError('synthetic media cleanup failure')
        self.window.side_effect = failure
        with patch.object(self.resources, 'close', side_effect=cleanup_failure) as close:
            with self.assertRaises(ValueError) as raised:
                self.complete()
        self.assertIs(raised.exception, failure)
        self.assertIs(raised.exception.__cause__, cleanup_failure)
        close.assert_called_once_with()
        self.release.assert_called_once_with()

    def test_cleanup_failure_without_handoff_failure_remains_visible(self):
        self.host.closing = True
        with patch.object(self.resources, 'close', side_effect=RuntimeError('synthetic media cleanup failure')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic media cleanup failure'):
                self.complete()

    def test_cancelled_completion_without_payload_needs_no_cleanup(self):
        self.host.open_operation.cancelled.set()
        for result in (None, ('markdown', (b'synthetic', {}))):
            self.result = result
            self.complete()
        self.show.assert_not_called()


class LocalCryptLifetimeTests(LocalCryptCase):
    def test_private_markdown_save_as_retargets_local_and_crypt_without_overwrite(self):
        from features.rclone.localcrypt.ui.views import MarkdownStorage, PrivateMarkdownWindow
        from commonUtils.runtime.resources.local import LocalFiles
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            path = f.item.data / 'note.md'
            storage = MarkdownStorage(f.provider, path, f.original, {}, lambda *_: None)
            window = PrivateMarkdownWindow(path, storage)
            window.viewer.edit_mode.setCurrentIndex(window.viewer.edit_mode.findData('source'))
            try:
                local_root = Path(directory) / 'save-as-local'
                local_root.mkdir()
                local = LocalFiles(local_root)
                window.viewer.editor.setPlainText('# Save As draft')
                window.viewer.editor.document().setModified(True)
                self.assertTrue(window.viewer.save_as_action.isEnabled())
                with patch('services.documents.ui.markdown.choose_destination', return_value=(local, 'exported.md', lambda: None)), \
                        patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes):
                    window.viewer.save_as_dialog()
                self.wait(lambda: not storage.operation.busy)
                self.assertEqual((local_root / 'exported.md').read_bytes(), b'# Save As draft')
                self.assertEqual(window.windowTitle(), '🕵️ Private - exported.md — Markdown')
                with patch('services.documents.ui.editors.open_editor_choice') as linked:
                    window.viewer.storage.open_link(local_root / 'linked.md', 'anchor')
                    selected = linked.call_args.args[0]
                    self.assertIs(selected.provider, local)
                    self.assertEqual(selected.path, 'linked.md')
                    self.assertEqual(linked.call_args.kwargs['fragment'], 'anchor')
                    selected.close()

                self.assertEqual(f.provider.read_bytes('note.md'), f.original)
                window.viewer.editor.setPlainText('# Saved locally again')
                window.viewer.editor.document().setModified(True)
                window.viewer.save_document()
                self.wait(lambda: not storage.operation.busy)
                self.assertEqual((local_root / 'exported.md').read_bytes(), b'# Saved locally again')
                with patch('services.documents.ui.markdown.choose_destination', return_value=(f.provider, 'another.md', lambda: None)):
                    window.viewer.save_as_dialog()
                self.wait(lambda: not storage.operation.busy)
                self.assertEqual(f.provider.read_bytes('another.md'), b'# Saved locally again')
                window.viewer.editor.setPlainText('# Collision must retain draft')
                window.viewer.editor.document().setModified(True)
                with patch('services.documents.ui.markdown.choose_destination', return_value=(f.provider, 'note.md', lambda: None)):
                    window.viewer.save_as_dialog()
                self.wait(lambda: not storage.operation.busy)
                self.assertEqual(f.provider.read_bytes('note.md'), f.original)
                self.assertTrue(window.viewer.is_modified)
            finally:
                window.viewer.editor.document().setModified(False)
                window.viewer.formatted_editor.document().setModified(False)
                window.close()
