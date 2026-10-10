"""CSV-driven media renames preserve sources on invalid plans and publication failures."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from commonUtils import renameUtils
from commonUtils.dirUtils import Directory
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
        def fail_second(source, target):
            if target.name == '2 - Second.mka':
                raise OSError('simulated publication failure')
            return rename(source, target)
        with patch.object(renameUtils, '_rename_exclusive', side_effect=fail_second):
            self.assertFalse(mka.rename_from_csv(self.root))
        for number in (1, 2):
            self.assertEqual((self.root/f'Chapter_{number}.mka').read_bytes(), bytes([number]))
        self.assertFalse(list(self.root.glob('.bulk-rename-*')))
        self.assertTrue(mka.rename_from_csv(self.root))
        self.assertEqual((self.root/'1 - First.mka').read_bytes(), b'\x01')
        self.assertEqual((self.root/'2 - Second.mka').read_bytes(), b'\x02')
