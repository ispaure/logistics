"""Image dialog forwards selected options and keeps completed results visible."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from features.images import actions
from features.images.ui.dialogs import ImageCompressDialog

TEST_STAGE = TestStage.REGRESSION


class ImageFolderDialogTests(QtTestCase):
    def test_selected_options_reach_folder_workflow_and_results_remain_visible(self):
        root = Path(self.temporary_directory().name).resolve()
        source = root / 'sample.png'
        Image.new('RGB', (100, 100), 'red').save(source)
        nested = root / 'nested'
        nested.mkdir()
        untouched = nested / 'other.png'
        Image.new('RGB', (32, 32), 'blue').save(untouched)
        original = untouched.read_bytes()
        dialog = ImageCompressDialog(initial_path=root)
        dialog.show()
        dialog.recursive.setChecked(False)
        dialog.exclude_webp.setChecked(False)
        dialog.always_keep.setChecked(True)
        dialog.preserve_originals.setChecked(False)
        dialog.quality_color.setText('63')
        dialog.quality_grayscale.setText('29')
        dialog.max_long_edge.setText('24')
        dialog.enable_max_height.setChecked(True)
        dialog.max_height.setText('18')
        with patch.object(dialog, '_confirm', return_value=True), \
                patch.object(actions, 'compress_folders', wraps=actions.compress_folders) as compress:
            dialog.action_button.click()
            self.wait_until(lambda: not dialog.busy, message='Image folder workflow did not finish')
        compress.assert_called_once()
        self.assertEqual(compress.call_args.args, ((root,),))
        options = dict(compress.call_args.kwargs)
        self.assertTrue(callable(options.pop('report')))
        self.assertTrue(callable(options.pop('cancelled')))
        self.assertEqual(options, dict(
            recursive=False, exclude_webp=False, always_keep_compressed=True,
            preserve_animated_and_multipage_originals=False,
            quality_color=63, quality_grayscale=29, max_long_edge=24, max_height=18))
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.results.topLevelItemCount(), 1)
        self.assertEqual(dialog.results.topLevelItem(0).text(1), 'Converted to WEBP')
        self.assertIn('1 processed', dialog.summary.text())
        self.assertFalse(source.exists())
        with Image.open(source.with_suffix('.webp')) as converted:
            self.assertEqual(converted.size, (18, 18))
        self.assertEqual(untouched.read_bytes(), original)
        self.assertFalse(untouched.with_suffix('.webp').exists())
        dialog.close()
