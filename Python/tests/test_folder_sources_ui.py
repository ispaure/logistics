"""Folder-source snapshots, contextual selections and startup refresh counts."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import unittest
from commonUtils.tests.qt_test_case import QtTestCase

from commonUtils.ui import pyside as qt
from features.contributions import (
    LocalFolderSource, LocalFolderSourceContribution, RemoteFolderSource,
    RemoteFolderSourceContribution, RegisteredContribution,
)
from models.local_folder import LocalFolder
from ui_new.main_window import MainWindow
from ui_new.pages.folders import FoldersPage
from services.folder_sources import discover_folder_sources


class FolderSourceTests(QtTestCase):
    def until(self, condition):
        from time import monotonic, sleep
        deadline = monotonic() + 5
        while not condition():
            self.assertLess(monotonic(), deadline)
            self.app.processEvents(); sleep(.005)

    def test_slow_source_does_not_block_gui_and_stale_refresh_is_discarded(self):
        from threading import Event
        entered, release = Event(), Event()
        reads = []
        def names():
            reads.append(qt.QThread.currentThread())
            if len(reads) == 1:
                entered.set(); release.wait(5)
                return ['Old']
            return ['New']
        self.remote([], 'profile').side_effect = names
        page = FoldersPage()
        self.addCleanup(self.close_page, page)
        self.addCleanup(release.set)
        self.until(entered.is_set)
        tick = []
        qt.QTimer.singleShot(0, lambda: tick.append(True))
        self.until(lambda: bool(tick))
        self.assertTrue(page.discovery.busy)
        page.refresh()
        release.set(); self.wait(page)
        self.assertEqual([entry.name for entry in self.entries(page)], ['New'])
        self.assertTrue(all(thread != self.app.thread() for thread in reads))

    def test_feature_detection_runs_off_gui_thread_and_close_waits_for_it(self):
        from threading import Event
        from features.contributions import FolderFeatureContribution
        entered, release = Event(), Event()
        threads = []
        def available(entry):
            threads.append(qt.QThread.currentThread())
            entered.set(); release.wait(5)
            return True
        self.local_folders = [self.folder('Local')]
        contribution = FolderFeatureContribution('Slow', available, get_actions=lambda entry: [])
        with patch('features.registry.get_folder_features', return_value=[RegisteredContribution('slow', 'Slow', contribution)]):
            page = FoldersPage()
            self.addCleanup(self.close_page, page); self.addCleanup(release.set)
            self.until(entered.is_set)
            self.assertNotEqual(threads[0], self.app.thread())
            self.assertFalse(page.prepare_close())
            release.set(); self.wait(page)
            self.assertTrue(page.prepare_close())

    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.local_folders = []
        self.locals = []
        self.remotes = []
        self.settings = {}
        for target, options in (
            ('services.folder_entries.folder_discovery.get_local_folders', {'side_effect': lambda: self.local_folders}),
            ('services.folder_entries._get_configured_name_values', {'side_effect': lambda key: self.settings.get(key, [])}),
            ('features.registry.get_local_folder_sources', {'side_effect': lambda: self.locals}),
            ('features.registry.get_remote_folder_sources', {'side_effect': lambda: self.remotes}),
            ('features.registry.get_folder_features', {'return_value': []}),
        ):
            patcher = patch(target, **options)
            patcher.start()
            self.addCleanup(patcher.stop)

    def folder(self, name, parent='managed'):
        path = self.root / parent / name
        path.mkdir(parents=True)
        return LocalFolder(path)

    def remote(self, names, context, feature='remote', label='Remote'):
        read_names = Mock(return_value=names)
        source = RemoteFolderSource(context, read_names, context=Path(context))
        provider = RemoteFolderSourceContribution(label, Mock(return_value=[source]))
        self.remotes.append(RegisteredContribution(feature, feature.title(), provider))
        return read_names

    def page(self):
        page = FoldersPage()
        self.addCleanup(self.close_page, page)
        self.wait(page)
        return page

    def close_page(self, page):
        # Selection changes can start detail work after wait() returns. Cancel
        # and drain it before scheduling QObject destruction.
        page.prepare_close()
        self.wait(page)
        page.close()
        page.deleteLater()

    def wait(self, page):
        from time import monotonic, sleep
        deadline = monotonic() + 5
        while page.discovery.busy or page.details.busy:
            self.assertLess(monotonic(), deadline, 'Folder discovery did not finish')
            self.app.processEvents(); sleep(.005)
        self.app.processEvents()

    def tab(self, page, name):
        names = [page.source_tabs.tabText(index) for index in range(page.source_tabs.count())]
        self.assertIn(name, names)
        return names.index(name)

    def entries(self, page):
        return [item.data(0, qt.Qt.ItemDataRole.UserRole) for item in page._entry_items.values()]

    def test_sources_are_read_once_per_refresh_not_again_on_show_or_selection(self):
        read_names = self.remote(['Shared', 'Remote-Only'], 'profile')
        self.local_folders = [self.folder('Local'), self.folder('Shared')]
        page = self.page()
        page.show()
        self.app.processEvents()
        self.assertTrue(page.source_tabs.isVisible())
        self.assertGreater(page.source_tabs.height(), 0)
        read_names.assert_called_once_with()
        page.source_tabs.setCurrentIndex(self.tab(page, 'Remote'))
        page.credential_combo.setCurrentIndex(1)
        page.credential_combo.setCurrentIndex(0)
        read_names.assert_called_once_with()
        page.refresh()
        self.wait(page)
        self.assertEqual(read_names.call_count, 2)
        self.assertEqual({entry.name for entry in self.entries(page)}, {'Shared', 'Remote-Only'})
        page.close()

    def test_main_window_first_display_reads_sources_once_and_returning_refreshes(self):
        read_names = self.remote(['Remote'], 'profile')
        with patch('features.registry.get_pages', return_value=[]), patch(
                'features.registry.get_debug_actions', return_value=[]):
            window = MainWindow()
            self.addCleanup(window.dlg.deleteLater)
            self.addCleanup(window.tabs.widget(0).file_browser.shutdown)
            window.dlg.show()
            self.wait(window._core_pages[1][2])
            read_names.assert_called_once_with()
            known_index = next(index for index in range(window.tabs.count())
                               if window.tabs.tabText(index) == 'Folder Hub')
            self.assertEqual(window.tabs.tabText(0), 'File Browser')
            window.tabs.setCurrentIndex(known_index)
            page = window.tabs.widget(known_index)
            self.wait(page)
            self.assertGreater(page.source_tabs.height(), 0)
            self.assertEqual(read_names.call_count, 2)
            window.tabs.setCurrentIndex(0)
            window.tabs.setCurrentIndex(known_index)
            self.wait(page)
            self.assertEqual(read_names.call_count, 3)
            window.dlg.close()

    def test_excluded_remote_does_not_hide_its_local_folder(self):
        self.local_folders = [self.folder('Hidden')]
        self.settings['excluded_remote_names'] = ['Hidden']
        self.remote(['Hidden'], 'profile')
        page = self.page()
        page.source_tabs.setCurrentIndex(self.tab(page, 'Local'))
        self.assertEqual([entry.name for entry in self.entries(page)], ['Hidden'])
        self.assertTrue(self.entries(page)[0].has_local)
        self.assertFalse(self.entries(page)[0].has_remote)

    def test_same_named_remote_folders_keep_distinct_credentials_and_selection(self):
        self.remote(['Shared'], 'one')
        self.remote(['Shared'], 'two')
        page = self.page()
        self.assertEqual(len(page._entry_items), 2)
        entry = next(entry for entry in self.entries(page) if entry.remote_context == Path('two'))
        page.folder_tree.setCurrentItem(page._entry_items[page._entry_key(entry)])
        selected_key = page._selected_entry_key
        page.refresh()
        self.wait(page)
        self.assertEqual(page._selected_entry_key, selected_key)
        self.assertEqual(page.folder_tree.currentItem().data(0, qt.Qt.ItemDataRole.UserRole).remote_context, Path('two'))
        page.credential_combo.setCurrentIndex(2)
        self.assertEqual(len(page._entry_items), 1)
        self.assertEqual(self.entries(page)[0].remote_context, Path('two'))

    def test_equal_source_labels_restore_the_correct_feature(self):
        self.remote(['One'], 'one', feature='one', label='Same')
        self.remote(['Two'], 'two', feature='two', label='Same')
        page = self.page()
        page.source_tabs.setCurrentIndex(1)
        page.refresh()
        self.wait(page)
        self.assertEqual(page.source_tabs.tabData(page.source_tabs.currentIndex())[1], 'two')
        self.assertEqual([entry.name for entry in self.entries(page)], ['Two'])

    def test_removed_source_does_not_transfer_its_credential_to_another_feature(self):
        self.remote(['One'], 'profile', feature='one', label='One')
        self.remote(['Two'], 'profile', feature='two', label='Two')
        page = self.page()
        page.credential_combo.setCurrentIndex(1)
        self.remotes.pop(0)
        page.refresh()
        self.wait(page)
        self.assertEqual(page.source_tabs.tabText(page.source_tabs.currentIndex()), 'Two')
        self.assertIsNone(page.credential_combo.currentData())
        self.assertEqual([entry.name for entry in self.entries(page)], ['Two'])

    def test_dedicated_local_sources_keep_same_named_paths_separate(self):
        one = self.folder('Shared', 'one')
        two = self.folder('Shared', 'two')
        for folder in (one, two):
            source = LocalFolderSource(folder.path.parent.name, Mock(return_value=[folder]))
            contribution = LocalFolderSourceContribution('Dedicated', Mock(return_value=[source]))
            self.locals.append(RegisteredContribution('local', 'Local', contribution))
        page = self.page()
        self.assertEqual({entry.local.path for entry in self.entries(page)}, {one.path, two.path})
        self.assertEqual(len(page._entry_items), 2)

    def test_refresh_without_sources_shows_empty_state(self):
        page = self.page()
        self.assertFalse(page._entry_items)
        self.assertIsNone(page.selected_entry_name)
        self.assertIsNotNone(page.detail_scroll.widget())

    def test_sources_added_after_first_display_become_visible_on_refresh(self):
        page = self.page()
        page.show()
        self.app.processEvents()
        self.assertFalse(page.source_tabs.isVisible())
        self.remote(['New'], 'profile')
        page.refresh()
        self.wait(page)
        self.app.processEvents()
        self.assertTrue(page.source_tabs.isVisible())
        self.assertGreater(page.source_tabs.height(), 0)
        self.assertEqual([entry.name for entry in self.entries(page)], ['New'])
        page.close()

    def test_refresh_restores_signal_state_even_if_tab_rebuild_fails(self):
        self.local_folders = [self.folder('Local')]
        page = self.page()
        for originally_blocked in (False, True):
            with self.subTest(originally_blocked=originally_blocked):
                page.source_tabs.blockSignals(originally_blocked)
                with patch.object(page, '_rebuild_source_tabs', side_effect=ValueError('bad source')):
                    with self.assertRaisesRegex(ValueError, 'bad source'):
                        page._apply_sources(discover_folder_sources())
                self.assertEqual(page.source_tabs.signalsBlocked(), originally_blocked)
        page.source_tabs.blockSignals(False)

    def test_credential_refresh_preserves_existing_signal_block(self):
        self.remote(['Remote'], 'profile')
        page = self.page()
        page.credential_combo.blockSignals(True)
        page._refresh_credentials()
        self.assertTrue(page.credential_combo.signalsBlocked())
        page.credential_combo.blockSignals(False)

    def test_folder_names_are_plain_text_in_the_details(self):
        name = '<b>Folder</b>'.replace('/', '_')
        if os.name == 'nt':
            name = name.replace('<', '&lt;').replace('>', '&gt;')
        self.local_folders = [self.folder(name)]
        page = self.page()
        titles = [label for label in page.detail_scroll.widget().findChildren(qt.QLabel)
                  if label.text() == self.local_folders[0].name]
        self.assertTrue(titles)
        self.assertTrue(all(label.textFormat() == qt.Qt.TextFormat.PlainText for label in titles))
