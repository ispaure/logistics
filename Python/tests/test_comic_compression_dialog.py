"""Selection compression retains normal options without another file picker."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from features.comics.ui.dialogs import CompressCbzDialog
from features.comics.compression_stats import CompressionStats


class CompressionDialogTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_selected_targets_replace_picker_and_pass_normal_options(self):
        targets = (self.root / 'first.cbz', self.root / 'folder')
        dialog = CompressCbzDialog(targets=targets)
        self.assertIsNone(dialog.target_dir)
        self.assertFalse(dialog.findChildren(qt.QLineEdit))
        self.assertTrue(dialog.recursive.isChecked())
        self.assertTrue(dialog.preserve_originals.isChecked())
        self.assertFalse(dialog.always_keep.isChecked())
        dialog.recursive.setChecked(False)
        with patch.object(dialog, '_confirm', return_value=True), patch(
                'features.comics.cbz.compress_selected_cbz', return_value=CompressionStats()) as compress:
            dialog._execute()
        compress.assert_called_once_with(targets, recursive=False, always_keep_compressed=False,
                                         preserve_animated_and_multipage_originals=True)
        self.assertEqual(dialog.result(), qt.QDialog.DialogCode.Accepted)

    def test_validation_and_partial_failure_keep_dialog_open(self):
        dialog = CompressCbzDialog(targets=[self.root])
        dialog.always_keep.setChecked(True)
        with patch('features.comics.ui.dialogs.ui.display_msg_box_ok') as message, patch(
                'features.comics.cbz.compress_selected_cbz') as compress:
            dialog._execute()
            message.assert_called_once()
            compress.assert_not_called()
        dialog.always_keep.setChecked(False)
        stats = CompressionStats()
        stats.error_during_compression = 1
        with patch.object(dialog, '_confirm', return_value=True), patch(
                'features.comics.ui.dialogs.ui.display_msg_box_ok') as message, patch(
                'features.comics.cbz.compress_selected_cbz', return_value=stats):
            dialog._execute()
            self.assertIn('1 failed', message.call_args.args[1])
        self.assertEqual(dialog.result(), qt.QDialog.DialogCode.Rejected)

    def test_regular_dialog_keeps_folder_picker(self):
        dialog = CompressCbzDialog(initial_path=self.root)
        self.assertIsNone(dialog.targets)
        self.assertEqual(dialog.target_dir.text(), str(self.root))
