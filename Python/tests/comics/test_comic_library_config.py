"""Configured library selection stays rooted in the collection folder."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.tests.qt_test_case import QtTestCase

from features.comics.library_config import configured_libraries, has_library_configuration
from tests.comics.fixtures import comic_library


class LibraryConfigurationFixture:
    def setUp(self):
        if isinstance(self, QtTestCase):
            self.temp = self.temporary_directory()
        else:
            self.temp = TemporaryDirectory()
            self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'remoteConfig.ini'


class LibraryConfigurationTests(LibraryConfigurationFixture, unittest.TestCase):
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


class LibraryTabsTests(LibraryConfigurationFixture, QtTestCase):
    def test_tabs_include_all_and_keep_catalog_at_collection_root(self):
        from commonUtils.ui import pyside as qt
        app = qt.QApplication.instance() or qt.QApplication([])
        self.config.write_text('[LogisticsComics]\nlibraries = Missing, Artbooks, Comics [Marvel]\n')
        for name in ('Artbooks', 'Comics [Marvel]'):
            (self.root / name).mkdir()
        window = comic_library(self.root)
        self.assertEqual([window.library_tabs.tabText(i) for i in range(window.library_tabs.count())],
                         ['All', 'Missing', 'Artbooks', 'Comics [Marvel]'])
        self.assertFalse(window.library_tabs.isTabEnabled(1))
        self.assertEqual(Path(window.model.filePath(window.tree.rootIndex())), self.root)
        window._navigate(self.root / 'Artbooks')
        self.assertEqual(window.navigation.library, self.root)
        window._up()
        self.assertEqual(window.browser.browsing_directory(), self.root)
        window.library_tabs.setCurrentIndex(2)
        self.assertEqual(Path(window.model.filePath(window.tree.rootIndex())), self.root / 'Artbooks')
        window.library_tabs.setCurrentIndex(3)
        self.assertEqual(Path(window.model.filePath(window.tree.rootIndex())), self.root / 'Comics [Marvel]')
        self.assertEqual(window.catalog.root, self.root)
        self.assertEqual(window.tree.header().visualIndex(3), 1)
        self.wait_until(lambda: not window.catalog_busy, message='Library catalog did not finish')
        window.close()
        app.processEvents()
