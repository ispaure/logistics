"""Image dialog forwards selected options and keeps completed results visible."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from threading import Event
from unittest.mock import patch

from PIL import Image
from commonUtils.integrations.wrappers import piexifWrapper
from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from features.images import actions
from features.images.ui.dialogs import ExifCommentsDialog, ImageCompressDialog

TEST_STAGE = TestStage.REGRESSION


class ImageFolderDialogTests(QtTestCase):
    def test_exif_dialog_reports_success_before_corrupt_file(self):
        root = Path(self.temporary_directory().name).resolve()
        good = root / '01.jpg'
        Image.new('RGB', (8, 8), 'red').save(good)
        original = good.read_bytes()
        bad = root / '02.jpg'
        bad.write_bytes(b'not a JPEG')
        dialog = ExifCommentsDialog(initial_path=root)
        dialog.comments.setText('New comment')
        dialog.show()

        with patch.object(dialog, '_confirm', return_value=True):
            dialog._execute()
            self.wait_until(lambda: not dialog.busy)

        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.results.topLevelItemCount(), 2)
        self.assertEqual(dialog.results.topLevelItem(0).text(1), 'Changed')
        self.assertEqual(dialog.results.topLevelItem(1).text(1), 'Failed')
        self.assertIn('1 changed', dialog.task.message.text())
        self.assertIn('1 failed', dialog.task.message.text())
        self.assertNotEqual(good.read_bytes(), original)
        self.assertEqual((root / '01.jpg.before-comments').read_bytes(), original)
        self.assertEqual(bad.read_bytes(), b'not a JPEG')
        self.assertFalse((root / '02.jpg.before-comments').exists())

    def test_closing_exif_dialog_finishes_current_edit_and_reports_remaining(self):
        root = Path(self.temporary_directory().name).resolve()
        first, second = root / '01.jpg', root / '02.jpg'
        for path in (first, second):
            Image.new('RGB', (8, 8), 'red').save(path)
        originals = {path: path.read_bytes() for path in (first, second)}
        dialog = ExifCommentsDialog(initial_path=root)
        dialog.comments.setText('New comment')
        dialog.show()
        started, release = Event(), Event()
        edit = piexifWrapper.jpg_set_exif_comments

        def edit_current(path, comments):
            started.set()
            if not release.wait(10):
                raise TimeoutError('Test did not release the JPEG writer')
            return edit(path, comments)

        with patch.object(dialog, '_confirm', return_value=True), \
                patch.object(piexifWrapper, 'jpg_set_exif_comments', side_effect=edit_current) as writer:
            try:
                dialog.action_button.click()
                self.wait_until(started.is_set, message='JPEG writer did not start')
                self.assertFalse(dialog.close())
                self.assertTrue(dialog.isVisible())
                self.assertTrue(dialog.busy)
                self.assertTrue(dialog.task.cancelled.is_set())
            finally:
                release.set()
                self.wait_until(lambda: not dialog.busy)
        writer.assert_called_once_with(first, 'New comment')
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.results.topLevelItemCount(), 2)
        self.assertEqual(dialog.results.topLevelItem(0).text(1), 'Changed')
        self.assertEqual(dialog.results.topLevelItem(1).text(0), str(second))
        self.assertEqual(dialog.results.topLevelItem(1).text(1), 'Not processed')
        self.assertIn('1 not processed', dialog.task.message.text())
        self.assertIn('Cancelled', dialog.task.message.text())
        self.assertNotEqual(first.read_bytes(), originals[first])
        self.assertEqual((root / '01.jpg.before-comments').read_bytes(), originals[first])
        self.assertEqual(second.read_bytes(), originals[second])
        self.assertFalse((root / '02.jpg.before-comments').exists())
        self.assertTrue(dialog.close())

    def test_invalid_options_show_feedback_before_confirmation_or_background_work(self):
        root = Path(self.temporary_directory().name).resolve()
        source = root / 'sample.png'
        Image.new('RGB', (32, 32), 'red').save(source)
        original = source.read_bytes()
        for invalid in ('conflicting preservation', 'invalid quality'):
            with self.subTest(invalid=invalid):
                dialog = ImageCompressDialog(initial_path=root)
                if invalid == 'conflicting preservation':
                    dialog.always_keep.setChecked(True)
                else:
                    dialog.quality_color.setText('0')
                with patch('features.images.ui.dialogs.ui.display_msg_box_ok') as feedback, \
                        patch.object(dialog, '_confirm') as confirm, \
                        patch.object(dialog, '_run_background') as background, \
                        patch.object(actions, 'compress_folders') as compress:
                    dialog.action_button.click()
                feedback.assert_called_once()
                confirm.assert_not_called()
                background.assert_not_called()
                compress.assert_not_called()
                self.assertFalse(dialog.busy)
                self.assertEqual(dialog.results.topLevelItemCount(), 0)
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(list(root.iterdir()), [source])
                dialog.close()

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
