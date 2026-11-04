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
