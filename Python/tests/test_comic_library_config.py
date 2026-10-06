"""Configured library selection stays rooted in the collection folder."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest

from features.comics.library_config import configured_libraries, has_library_configuration


class LibraryConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'remoteConfig.ini'

    def test_configured_order_spaces_duplicates_and_missing_folders(self):
        self.config.write_text('[LogisticsComics]\nlibraries = Artbooks, Comics, Comics [Marvel], Mangas, Manhwa, Comics\n')
        libraries, error = configured_libraries(self.root)
        self.assertFalse(error)
        self.assertTrue(has_library_configuration(self.root))
        self.assertEqual([name for name, path in libraries], ['Artbooks', 'Comics', 'Comics [Marvel]', 'Mangas', 'Manhwa'])
        self.assertTrue(all(path.parent == self.root for name, path in libraries))

    def test_missing_setting_falls_back_but_empty_or_invalid_configuration_does_not(self):
        self.assertEqual(configured_libraries(self.root), ([(self.root.name, self.root)], ''))
        self.assertFalse(has_library_configuration(self.root))
        self.config.write_text('[LogisticsComics]\nlibraries =\n')
        self.assertEqual(configured_libraries(self.root), ([], ''))
        for value in ('../Other', '/Other', 'Nested/Child', '..', 'Nested\\Child'):
            self.config.write_text(f'[LogisticsComics]\nlibraries = {value}\n')
            libraries, error = configured_libraries(self.root)
            self.assertFalse(libraries)
            self.assertTrue(error)
        self.config.write_text('bad config')
        self.assertTrue(configured_libraries(self.root)[1])
        self.assertFalse(has_library_configuration(self.root))

    def test_dropdown_switches_tree_and_keeps_catalog_at_collection_root(self):
        from commonUtils.ui import pyside as qt
        from features.comics.ui.library import ComicLibraryWindow
        app = qt.QApplication.instance() or qt.QApplication([])
        self.config.write_text('[LogisticsComics]\nlibraries = Missing, Artbooks, Comics [Marvel]\n')
        for name in ('Artbooks', 'Comics [Marvel]'):
            (self.root / name).mkdir()
        window = ComicLibraryWindow(self.root)
        self.assertEqual(window.library_selector.currentText(), 'Artbooks')
        self.assertFalse(window.library_selector.model().item(0).isEnabled())
        self.assertEqual(window.model.filePath(window.tree.rootIndex()), str(self.root / 'Artbooks'))
        window.library_selector.setCurrentIndex(2)
        self.assertEqual(window.model.filePath(window.tree.rootIndex()), str(self.root / 'Comics [Marvel]'))
        self.assertEqual(window.catalog.root, self.root)
        self.assertEqual(window.tree.header().visualIndex(3), 1)
        deadline = time.monotonic() + 5
        while window.catalog_busy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        self.assertFalse(window.catalog_busy)
        window.close()
        app.processEvents()
