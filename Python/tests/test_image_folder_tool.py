"""WEBP folder workflows keep results visible and enforce policy before modifying files."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from PIL import Image
from commonUtils.ui import pyside as qt
from features.images import actions
from features.images.ui.dialogs import ImageCompressDialog
from features import registry


class ImageFolderToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'sample.png'
        Image.new('RGB', (100,100), 'red').save(self.source)

    def test_batch_reports_success_failure_and_preserves_unrelated_outputs(self):
        bad = self.root / 'broken.png'; bad.write_bytes(b'not an image')
        result, outcomes = actions.compress_folders(self.root, always_keep_compressed=True,
            preserve_animated_and_multipage_originals=False)
        self.assertEqual(result.completed, [self.source])
        self.assertIn(bad, result.failed)
        self.assertEqual(outcomes[self.source], 'Converted to WEBP')
        self.assertFalse(self.source.exists())
        self.assertTrue(self.source.with_suffix('.webp').exists())
        self.assertTrue(bad.exists())

    def test_blocked_folder_never_calls_encoder(self):
        with patch('services.folder_safety.require_safe_folder', side_effect=ValueError('Protected')), patch.object(actions.processing.ImageFile, 'compress') as encode:
            with self.assertRaises(ValueError):
                actions.compress_folders(self.root)
        encode.assert_not_called()
        self.assertTrue(self.source.exists())

    def test_results_window_remains_open_and_debug_action_is_removed(self):
        app = qt.QApplication.instance() or qt.QApplication([])
        dialog = ImageCompressDialog(initial_path=self.root)
        self.addCleanup(dialog.deleteLater)
        dialog.show()
        dialog.always_keep.setChecked(True)
        dialog.preserve_originals.setChecked(False)
        with patch.object(dialog, '_confirm', return_value=True):
            dialog.action_button.click()
        deadline = time.monotonic() + 5
        while dialog.busy:
            self.assertLess(time.monotonic(), deadline)
            app.processEvents(); time.sleep(.005)
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.results.topLevelItemCount(), 1)
        self.assertEqual(dialog.results.topLevelItem(0).text(1), 'Converted to WEBP')
        dialog.close()
        self.assertFalse([item for item in registry.get_debug_actions() if item.contribution.workflow_id == 'debug_images_compress'])
        definition = registry.get_feature_definition('images')
        self.assertEqual(definition.browser.actions[0].label, 'Batch Compress Images to WEBP…')
