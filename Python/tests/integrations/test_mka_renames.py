"""CSV-driven media renames preserve sources on invalid plans and publication failures."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from commonUtils.filesystem import rename as renameUtils
from commonUtils.filesystem.directories import Directory
from commonUtils.tests.qt_test_case import QtTestCase
from features.media import mka


class MkaRenameTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        patcher = patch.object(mka, 'log')
        patcher.start(); self.addCleanup(patcher.stop)

    def rows(self, *titles):
        return [SimpleNamespace(get_cells=lambda i=i, title=title: [
            SimpleNamespace(txt=str(i)), SimpleNamespace(txt=title)])
            for i, title in enumerate(titles, 1)]

    def test_duplicate_chapter_numbers_and_path_characters_are_rejected(self):
        (self.root/'Chapter_1.mka').write_bytes(b'first')
        for title in ('folder/title', r'folder\title', '../../escape', 'title:*', '', '   '):
            with self.subTest(title=title):
                self.assertIsNone(mka._build_rename_plan(Directory(self.root), self.rows(title)))
        (self.root/'Chapter_01.mka').write_bytes(b'second')
        self.assertIsNone(mka._build_rename_plan(Directory(self.root), self.rows('Title')))
        self.assertEqual((self.root/'Chapter_1.mka').read_bytes(), b'first')

    def test_success_and_failed_publication_rolls_back_the_whole_batch(self):
        for number in (1, 2):
            (self.root/f'Chapter_{number}.mka').write_bytes(bytes([number]))
        (self.root/'names.csv').write_text('1,First\n2,Second\n')
        rename = renameUtils._rename_exclusive
        partial_publications = []
        def fail_second(source, target):
            if target.name == '2 - Second.mka':
                partial_publications.append((self.root/'1 - First.mka').read_bytes())
                raise OSError('simulated publication failure')
            return rename(source, target)
        with patch.object(renameUtils, '_rename_exclusive', side_effect=fail_second):
            self.assertFalse(mka.rename_from_csv(self.root))
        self.assertEqual(partial_publications, [b'\x01'])
        for number in (1, 2):
            self.assertEqual((self.root/f'Chapter_{number}.mka').read_bytes(), bytes([number]))
        self.assertFalse(list(self.root.glob('.bulk-rename-*')))
        self.assertTrue(mka.rename_from_csv(self.root))
        self.assertEqual((self.root/'1 - First.mka').read_bytes(), b'\x01')
        self.assertEqual((self.root/'2 - Second.mka').read_bytes(), b'\x02')
        self.assertFalse((self.root/'Chapter_1.mka').exists())
        self.assertFalse((self.root/'Chapter_2.mka').exists())


class MkaRenameDialogTests(QtTestCase):
    def test_confirmed_rename_failure_requires_a_fresh_review(self):
        from features.media.ui import dialogs

        root = Path(self.temporary_directory().name)
        source = root / 'Chapter_1.mka'
        source.write_bytes(b'original')
        (root / 'names.csv').write_text('1,First\n')
        dialog = dialogs.RenameMkaDialog(root)

        dialog.action_button.click()
        self.wait_until(lambda: not dialog.busy)
        approved_plan = dialog.plan
        self.assertIsNotNone(approved_plan)
        self.assertEqual(dialog.results.topLevelItemCount(), 1)

        with patch.object(dialog, '_confirm', return_value=False):
            dialog.action_button.click()
        self.assertIs(dialog.plan, approved_plan)
        self.assertEqual(dialog.action_button.text(), 'Apply reviewed names')
        self.assertEqual(dialog.results.topLevelItemCount(), 1)

        source.write_bytes(b'changed after review')
        with (patch.object(dialog, '_confirm', return_value=True),
              patch.object(dialogs, 'apply_renames', wraps=renameUtils.apply_renames) as apply):
            dialog.action_button.click()
            self.wait_until(lambda: not dialog.busy)
        apply.assert_called_once()
        self.assertIs(apply.call_args.args[0], approved_plan)
        self.assertIn('Operation failed: Source changed since preview', dialog.task.message.text())
        self.assertIsNone(dialog.plan)
        self.assertEqual(dialog.action_button.text(), 'Review names')
        self.assertEqual(dialog.results.topLevelItemCount(), 0)

        dialog.action_button.click()
        self.wait_until(lambda: not dialog.busy)
        self.assertIsNotNone(dialog.plan)
        self.assertIsNot(dialog.plan, approved_plan)
        self.assertEqual(dialog.action_button.text(), 'Apply reviewed names')

        reports = []
        dialog.task.progress_changed.connect(lambda *report: reports.append(report))
        with patch.object(dialog, '_confirm', return_value=True):
            dialog.action_button.click()
            self.wait_until(lambda: not dialog.busy)
        self.assertIn((2, 2, 'Renamed 1 - First.mka'), reports)
        self.assertEqual((root / '1 - First.mka').read_bytes(), b'changed after review')
