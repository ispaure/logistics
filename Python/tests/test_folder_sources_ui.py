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
from services.folders.sources import discover_folder_sources
from ui_new.settings.workspaces import WorkspaceVisibility, workspace_visibility


class FolderSourceTests(QtTestCase):
    def until(self, condition):
        from time import monotonic, sleep
        deadline = monotonic() + 10
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
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.wait(page)
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
            self.until(lambda: not page.discovery.busy)
            self.select_first(page)
            self.until(entered.is_set)
            self.assertNotEqual(threads[0], self.app.thread())
            self.assertFalse(page.prepare_close())
            release.set(); self.wait(page)
            self.assertTrue(page.prepare_close())

    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        workspace_visibility().set_show_legacy(False)
        self.addCleanup(workspace_visibility().set_show_legacy, False)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.local_folders = []
        self.locals = []
        self.remotes = []
        self.settings = {}
        class BrowserStub(qt.QWidget):
            idle = qt.Signal()
            def prepare_close(self):
                return True
        patcher = patch('ui_new.pages.folders.FoldersPage._create_browser', side_effect=lambda *args, **kwargs: BrowserStub())
        self.browser_factory = patcher.start()
        self.browser_patcher = patcher
        self.addCleanup(patcher.stop)
        for target, options in (
            ('services.folders.entries.folder_discovery.get_local_folders', {'side_effect': lambda: self.local_folders}),
            ('services.folders.entries._get_configured_name_values', {'side_effect': lambda key: self.settings.get(key, [])}),
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
        self.until(page.prepare_close)
        self.wait(page)
        page.close()
        page.deleteLater()

    def wait(self, page):
        from time import monotonic, sleep
        deadline = monotonic() + 10
        while page.discovery.busy or page.details.busy:
            self.assertLess(monotonic(), deadline, 'Folder discovery did not finish')
            self.app.processEvents(); sleep(.005)
        self.app.processEvents()

    def tab(self, page, name):
        names = [page.source_tabs.tabText(index) for index in range(page.source_tabs.count())]
        self.assertIn(name, names)
        return names.index(name)

    def select_first(self, page):
        page.folder_tree.setCurrentItem(next(iter(page._entry_items.values())))

    def entries(self, page):
        return [item.data(0, qt.Qt.ItemDataRole.UserRole) for item in page._entry_items.values()]

    def test_legacy_visibility_defaults_off_and_is_shared_for_the_session(self):
        self.local_folders = [self.folder('Books'), self.folder('Legacy-Books'),
                              self.folder('lEgAcY-Notes')]
        self.remote(['Books', 'Legacy-Books', 'legacy-Notes'], 'cloud')
        self.remote(['Books', 'LEGACY-Server'], 'Network shares.conf', feature='rclone')
        page = self.page()
        self.assertFalse(page.visibility.show_legacy)
        self.assertEqual([entry.name for entry in self.entries(page)], ['Books'])
        page.visibility.set_show_legacy(True)
        self.assertEqual(len(self.entries(page)), 3)
        page.refresh()
        self.wait(page)
        self.assertTrue(page.visibility.show_legacy)
        self.assertEqual(len(self.entries(page)), 3)
        for source, count in [('Cloud', 5), ('Home Server', 2), ('Local', 3)]:
            page.source_tabs.setCurrentIndex(self.tab(page, source))
            self.wait(page)
            self.assertEqual(len(self.entries(page)), count)
            legacy = next(item for item in page._entry_items.values()
                          if item.data(0, qt.Qt.ItemDataRole.UserRole).name.casefold().startswith('legacy-'))
            page.folder_tree.setCurrentItem(legacy)
            page.visibility.set_show_legacy(False)
            self.assertEqual({entry.name for entry in self.entries(page)}, {'Books'})
            self.assertIsNone(page.selected_entry_name)
            page.visibility.set_show_legacy(True)
        fresh_page = self.page()
        self.assertTrue(fresh_page.visibility.show_legacy)
        self.assertEqual(len(self.entries(fresh_page)), 3)
        page.visibility.set_show_legacy(False)
        self.assertEqual([entry.name for entry in self.entries(fresh_page)], ['Books'])
        self.assertFalse(WorkspaceVisibility().show_legacy)

    def test_hiding_only_legacy_workspace_clears_browser_and_actions(self):
        self.local_folders = [self.folder('Legacy-Books')]
        page = self.page()
        self.assertFalse(self.entries(page))
        page.visibility.set_show_legacy(True)
        self.select_first(page)
        page.show()
        self.app.processEvents()
        self.assertIsNotNone(page._browser_view)
        page.visibility.set_show_legacy(False)
        self.assertFalse(self.entries(page))
        self.assertIsNone(page.selected_entry_name)
        self.assertIsNone(page._browser_view)
        self.assertIs(page.browser_stack.currentWidget(), page.browser_notice)
        self.assertFalse(page.detail_scroll.widget().findChildren(qt.QPushButton))

    def test_all_local_copies_and_loaded_cloud_remotes_use_separate_browser_targets(self):
        from types import SimpleNamespace
        from features.rclone.localcrypt.backend import LocalCryptFolder
        from features.rclone.ui_contributions import CopyContext
        local = self.folder('Shared')
        dropbox = self.folder('Dropbox', 'dropbox')
        cipher = self.root / 'cipher'
        cipher.mkdir()
        connection = SimpleNamespace(data=cipher, remote='Shared', package=self.root / 'keys.zip',
                                     context=self.root / 'keys.session')
        crypt = LocalCryptFolder(connection)
        sources = [RemoteFolderSource('keys', lambda: ['Shared'], context=self.root / 'keys.conf',
                                      get_local_folders=lambda: [local]),
                   RemoteFolderSource('offline', lambda: ['Shared'], context=CopyContext(connection),
                                      get_local_folders=lambda: [crypt])]
        contribution = RemoteFolderSourceContribution('rclone', lambda: sources)
        self.remotes.append(RegisteredContribution('rclone', 'rclone', contribution))
        self.local_folders = [local]
        self.locals.append(RegisteredContribution('dropbox', 'Dropbox',
            LocalFolderSourceContribution('Dropbox', lambda: [LocalFolderSource('Dropbox', lambda: [dropbox])])))
        page = self.page()
        page.show()
        self.app.processEvents()
        self.assertEqual(page.credential_combo.currentText(), 'Rclone')
        self.assertEqual({entry.local.path for entry in self.entries(page)}, {local.path, cipher})
        page.credential_combo.setCurrentText('Dropbox')
        page.refresh()
        self.wait(page)
        self.assertEqual(page.credential_combo.currentText(), 'Dropbox')
        self.assertEqual({entry.local.path for entry in self.entries(page)}, {dropbox.path})
        page.credential_combo.setCurrentText('Rclone')
        entry = next(entry for entry in self.entries(page) if entry.local.path == local.path)
        self.assertEqual(entry.remote_context, self.root / 'keys.conf')
        page.folder_tree.setCurrentItem(page._entry_items[page._entry_key(entry)])
        self.assertEqual(self.browser_factory.call_args.args, (local.path,))
        crypt_entry = next(entry for entry in self.entries(page) if entry.local.path == cipher)
        icon_item = page._entry_items[page._entry_key(crypt_entry)]
        self.assertFalse(icon_item.icon(0).isNull())
        self.assertEqual(icon_item.data(0, qt.Qt.ItemDataRole.AccessibleDescriptionRole), 'LocalCrypt, locked')
        page.folder_tree.setCurrentItem(icon_item)
        from ui_new.file_browser import _PrivateBrowserLocation
        self.assertEqual(self.browser_factory.call_args.args, (_PrivateBrowserLocation(connection, cipher),))
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.wait(page)
        self.assertEqual(len(self.entries(page)), 2)
        loaded = next(entry for entry in self.entries(page) if entry.remote_context == self.root / 'keys.conf')
        page.folder_tree.setCurrentItem(page._entry_items[page._entry_key(loaded)])
        from features.rclone.ui.remote_browser import RemoteLocation
        self.assertEqual(self.browser_factory.call_args.args,
                         (RemoteLocation(self.root / 'keys.conf', 'Shared'),))

    def test_local_provider_filter_preserves_selection_and_others_is_remainder(self):
        self.local_folders = [self.folder('Server-Books'), self.folder('Server-Notes')]
        dropbox = self.folder('Books', 'dropbox')
        other = self.folder('Books', 'custom')
        for feature, folder in [('dropbox', dropbox), ('custom', other)]:
            self.locals.append(RegisteredContribution(feature, feature.title(),
                LocalFolderSourceContribution(feature, lambda folder=folder: [
                    LocalFolderSource('Files', lambda: [folder])])))
        page = self.page()
        page.show()
        self.app.processEvents()
        self.assertEqual(page.credential_label.text(), 'Source')
        self.assertEqual([page.credential_combo.itemText(i) for i in range(page.credential_combo.count())],
                         ['Dropbox', 'Rclone', 'Others'])
        page.credential_combo.setCurrentText('Others')
        self.assertEqual({entry.local.path for entry in self.entries(page)}, {other.path})
        selected = page._selected_entry_key
        page.refresh()
        self.wait(page)
        self.assertEqual(page.credential_combo.currentText(), 'Others')
        self.assertEqual(page._selected_entry_key, selected)
        page.credential_combo.setCurrentText('Rclone')
        self.assertEqual({entry.local.path for entry in self.entries(page)},
                         {folder.path for folder in self.local_folders})
        tree = page.folder_tree
        root = tree.topLevelItem(0)
        child = root.child(0)
        self.assertIsNotNone(child)
        root_rect, child_rect = tree.visualItemRect(root), tree.visualItemRect(child)
        self.assertLessEqual(root_rect.left(), 2)
        self.assertGreater(child_rect.left(), root_rect.left())
        self.assertLessEqual(child_rect.left() - root_rect.left(), 20)
        self.assertLessEqual(child_rect.height(), 30)
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.wait(page)
        self.assertEqual(page.credential_label.text(), 'Credential')
        page.source_tabs.setCurrentIndex(self.tab(page, 'Local'))
        self.wait(page)
        self.assertEqual(page.credential_combo.currentText(), 'Rclone')

    def test_sources_open_without_selecting_or_browsing_a_folder(self):
        self.local_folders = [self.folder('Workspace')]
        self.remote(['Online'], 'profile')
        page = self.page()
        page.show()
        self.app.processEvents()
        for source in ('Local', 'Cloud', 'Local'):
            page.source_tabs.setCurrentIndex(self.tab(page, source))
            self.wait(page)
            self.assertIsNone(page.folder_tree.currentItem())
            self.assertIsNone(page.selected_entry_name)
            self.assertIsNone(page._browser_view)
            self.assertIn('Select a folder', page.browser_notice.text())
            self.browser_factory.assert_not_called()
            # Selecting a folder is the only step that starts a browser.
            self.select_first(page)
            self.assertIsNotNone(page._browser_view)
            self.browser_factory.reset_mock()
        for dock in page.panes.docks:
            header = dock.titleBarWidget()
            self.assertEqual(header.height(), 0)
            self.assertIn(dock.windowTitle(), header.accessibleName())

    def test_locked_workspace_unlocks_in_files_and_retries_inline(self):
        from types import SimpleNamespace
        from features.rclone import session
        from features.rclone.localcrypt.backend import LocalCryptFolder
        from features.rclone.ui.workspace_unlock import WorkspaceUnlockView
        self.browser_patcher.stop()
        cipher = self.root / 'cipher'
        cipher.mkdir()
        config, package = self.root / 'keys.session', self.root / 'keys.zip'
        connection = SimpleNamespace(data=cipher, remote='Private', context=config, package=package)
        self.addCleanup(session.forget, config)
        second = SimpleNamespace(data=cipher, remote='Second', context=config, package=package)
        second.data = self.root / 'second-cipher'
        second.data.mkdir()
        self.locals.append(RegisteredContribution('rclone', 'Rclone',
            LocalFolderSourceContribution('LocalCrypt', lambda: [
                LocalFolderSource('Private', lambda: [LocalCryptFolder(connection), LocalCryptFolder(second)])])))
        page = self.page()
        page.show()
        self.app.processEvents()
        class OpenedBrowser(qt.QWidget):
            idle = qt.Signal()
            def prepare_close(self):
                return True
        opened = OpenedBrowser()
        from features.contributions import FolderFeatureContribution
        available = Mock(return_value=True)
        page._folder_features = [RegisteredContribution('test', 'Test', FolderFeatureContribution(
            'Test', available, get_actions=lambda entry: [], supports_private_folders=True))]
        with patch('features.registry.get_folder_features', return_value=page._folder_features), patch(
                'ui_new.file_browser._browser_view', return_value=opened) as factory, patch(
                'features.rclone.localcrypt.ui.views.ensure_session', side_effect=AssertionError('Popup requested')), patch(
                'features.rclone.session.read_package', side_effect=[ValueError('bad password'), {'Private': {'type': 'crypt'}}]):
            self.select_first(page)
            view = page._browser_view
            self.assertIsInstance(view, WorkspaceUnlockView)
            self.assertIs(page.browser_stack.currentWidget(), view)
            self.assertTrue(page.panes.docks[1].isHidden())
            self.assertIn('Private', [label.text() for label in view.findChildren(qt.QLabel)
                                     if label.accessibleName() == 'Selected workspace'])
            factory.assert_not_called()
            available.assert_not_called()
            view.password.setText('wrong')
            view.submit()
            self.assertEqual(view.password.text(), '')
            self.until(lambda: not view.operation.busy)
            self.assertIn('Check the password', view.error.text())
            self.assertIsNone(session.credentials(config))
            available.assert_not_called()
            self.assertIs(page._browser_view, view)
            self.assertTrue(page.panes.docks[1].isHidden())
            view.password.setText('correct')
            view.submit()
            self.until(lambda: page._browser_view is opened)
            self.assertEqual(session.package_path(config), package)
            self.assertEqual(session.credentials(config), {'Private': {'type': 'crypt'}})
            self.assertEqual(page.selected_entry_name, 'Private')
            self.wait(page)
            self.assertFalse(page.panes.docks[1].isHidden())
            available.assert_called()
            factory.assert_called_once()
            self.assertEqual(len(page._entry_items), 2)
            for item in page._entry_items.values():
                self.assertEqual(item.data(0, qt.Qt.ItemDataRole.AccessibleDescriptionRole), 'LocalCrypt, unlocked')

    def test_unlock_refreshes_icons_and_actions_even_if_browser_cannot_open(self):
        from types import SimpleNamespace
        from features.contributions import FolderFeatureContribution, UIAction
        from features.rclone import session
        from features.rclone.localcrypt.backend import LocalCryptFolder
        self.browser_patcher.stop()
        config, package = self.root / 'keys.session', self.root / 'keys.zip'
        self.addCleanup(session.forget, config)
        copies = []
        for name in ('One', 'Two'):
            data = self.root / name
            data.mkdir()
            copies.append(LocalCryptFolder(SimpleNamespace(
                data=data, remote=name, context=config, package=package)))
        self.locals.append(RegisteredContribution('rclone', 'Rclone', LocalFolderSourceContribution(
            'LocalCrypt', lambda: [LocalFolderSource('Copies', lambda: copies)])))
        tool = FolderFeatureContribution('Fixture', lambda entry: True,
            get_actions=lambda entry: [UIAction('Fixture action', callback=lambda: None)],
            supports_private_folders=True)
        with patch('features.registry.get_folder_features', return_value=[RegisteredContribution('test', 'Test', tool)]), patch(
                'ui_new.file_browser._browser_view', side_effect=OSError('synthetic browser failure')), patch(
                'features.rclone.session.read_package', return_value={name: {'type': 'crypt'} for name in ('One', 'Two')}):
            page = self.page()
            page.show()
            self.select_first(page)
            view = page._browser_view
            view.password.setText('synthetic password')
            view.submit()
            self.until(lambda: session.credentials(config) is not None and not view.operation.busy)
            self.wait(page)
            self.assertIn('synthetic browser failure', page.browser_notice.text())
            self.assertFalse(page.panes.docks[1].isHidden())
            for item in page._entry_items.values():
                self.assertEqual(item.data(0, qt.Qt.ItemDataRole.AccessibleDescriptionRole), 'LocalCrypt, unlocked')
            buttons = {button.text() for button in page.detail_scroll.widget().findChildren(qt.QPushButton)}
            self.assertIn('Fixture action', buttons)

    def test_credentials_locked_during_action_detection_do_not_publish_actions(self):
        from threading import Event
        from types import SimpleNamespace
        from features.contributions import FolderFeatureContribution, UIAction
        from features.rclone import session
        from features.rclone.ui_contributions import CopyContext
        from models.folder_entry import FolderEntry
        config, package = self.root / 'local.session', self.root / 'local.zip'
        session.remember(config, {'Plain': {'type': 'local'}}, package_path=package)
        self.addCleanup(session.forget, config)
        local = self.folder('Plain')
        context = CopyContext(SimpleNamespace(context=config, package=package, data=local.path))
        entry = FolderEntry('Plain', local=local, remote_name='Plain', remote_source='rclone', remote_context=context)
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        def available(entry):
            entered.set()
            release.wait(5)
            return True
        tool = FolderFeatureContribution('Fixture', available,
            get_actions=lambda entry: [UIAction('Fixture action', callback=lambda: None)])
        page = self.page()
        page._folder_features = [RegisteredContribution('test', 'Test', tool)]
        page._show_entry(entry)
        self.until(entered.is_set)
        session.forget(config)
        release.set()
        self.wait(page)
        buttons = {button.text() for button in page.detail_scroll.widget().findChildren(qt.QPushButton)}
        self.assertNotIn('Fixture action', buttons)
        self.assertIsNotNone(page._actions_unlock_view)

    def test_replaced_credentials_redetect_actions_instead_of_publishing_stale_result(self):
        from threading import Event
        from features.contributions import FolderFeatureContribution, UIAction
        from features.rclone import session
        from models.folder_entry import FolderEntry
        config = self.root / 'account.session'
        session.remember(config, {'Plain': {'type': 'local', 'label': 'Old'}})
        self.addCleanup(session.forget, config)
        entry = FolderEntry('Plain', local=self.folder('Plain'), remote_name='Plain',
                            remote_source='rclone', remote_context=config)
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        def actions(entry):
            label = session.credentials(config)['Plain']['label']
            if label == 'Old':
                entered.set()
                release.wait(5)
            return [UIAction(label + ' action', callback=lambda: None)]
        tool = FolderFeatureContribution('Fixture', lambda entry: True, get_actions=actions)
        page = self.page()
        page._folder_features = [RegisteredContribution('test', 'Test', tool)]
        page._show_entry(entry)
        self.until(entered.is_set)
        session.remember(config, {'Plain': {'type': 'local', 'label': 'New'}})
        release.set()
        self.wait(page)
        buttons = {button.text() for button in page.detail_scroll.widget().findChildren(qt.QPushButton)}
        self.assertIn('New action', buttons)
        self.assertNotIn('Old action', buttons)

    def test_plain_local_actions_require_unlock_and_discard_late_password_results(self):
        from threading import Event
        from types import SimpleNamespace
        from features.contributions import FolderFeatureContribution
        from features.rclone import session
        from features.rclone.ui_contributions import CopyContext
        from models.folder_entry import FolderEntry
        config, package = self.root / 'local.session', self.root / 'local.zip'
        self.addCleanup(session.forget, config)
        local = self.folder('Plain')
        context = CopyContext(SimpleNamespace(context=config, package=package, data=local.path))
        entry = FolderEntry('Plain', local=local, remote_name='Plain', remote_source='rclone', remote_context=context)
        page = self.page()
        available = Mock(return_value=False)
        page._folder_features = [RegisteredContribution('test', 'Test', FolderFeatureContribution(
            'Test', available, get_actions=lambda entry: []))]
        page._show_entry(entry)
        view = page._actions_unlock_view
        self.assertIsNotNone(view)
        self.assertFalse(page.panes.docks[1].isHidden())
        self.assertTrue(any('load this workspace’s actions' in label.text() for label in view.findChildren(qt.QLabel)))
        available.assert_not_called()
        with patch('features.rclone.session.read_package', return_value={'Plain': {'type': 'local'}}):
            view.password.setText('correct')
            view.submit()
            self.until(lambda: not view.operation.busy and not page.details.busy)
        available.assert_called_once()
        self.assertIsNone(page._actions_unlock_view)
        session.forget(config)
        page._show_entry(entry)
        old_view = page._actions_unlock_view
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        def delayed(*args):
            entered.set()
            release.wait(5)
            return {'Plain': {'type': 'local'}}
        with patch('features.rclone.session.read_package', side_effect=delayed):
            old_view.password.setText('correct')
            old_view.submit()
            self.until(entered.is_set)
            page._show_empty_state()
            release.set()
            self.until(lambda: not old_view.operation.busy)
        self.assertIsNone(session.credentials(config))
        self.assertIsNone(page._actions_unlock_view)

    def test_cloud_browser_keeps_associated_package_for_inline_unlock(self):
        from types import SimpleNamespace
        from features.rclone.ui_contributions import CopyContext
        from features.rclone.ui.remote_browser import RemoteLocation
        from models.folder_entry import FolderEntry
        config, package = self.root / 'cloud.session', self.root / 'cloud.zip'
        association = SimpleNamespace(context=config, package=package, data=self.root / 'copy')
        page = self.page()
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.wait(page)
        entry = FolderEntry(name='Cloud', remote_name='Cloud', remote_source='rclone',
                            remote_context=CopyContext(association))
        page._browse_entry(entry)
        self.assertEqual(self.browser_factory.call_args.args, (RemoteLocation(config, 'Cloud'),))
        self.assertEqual(self.browser_factory.call_args.kwargs, {'package': package})

    def test_leaving_unlock_discards_late_credentials(self):
        from threading import Event
        from features.rclone import session
        from features.rclone.ui.remote_browser import RemoteLocation
        from features.rclone.ui.workspace_unlock import WorkspaceUnlockView
        self.browser_patcher.stop()
        config, package = self.root / 'remote.session', self.root / 'remote.zip'
        session.remember(config, {'Remote': {'type': 'alias'}}, package_path=package)
        session.forget(config)
        self.addCleanup(session.forget, config)
        entered, release = Event(), Event()
        self.addCleanup(release.set)
        def read(*args):
            entered.set()
            release.wait(5)
            return {'Remote': {'type': 'alias'}}
        page = self.page()
        page.show()
        with patch('features.rclone.session.read_package', side_effect=read), patch(
                'features.rclone.localcrypt.ui.views.ensure_session', side_effect=AssertionError('Popup requested')):
            from features.rclone.ui.remote_browser import open_remote
            view = open_remote(config, 'Remote', page, package=package)
            self.assertIsInstance(view, WorkspaceUnlockView)
            self.assertTrue(page.panes.docks[1].isHidden())
            view.password.setText('password')
            view.submit()
            self.until(entered.is_set)
            page._clear_browser('Select a folder')
            self.assertFalse(page.panes.docks[1].isHidden())
            self.assertIn(view, page._retired_browsers)
            self.assertIsNone(page._browser_view)
            release.set()
            self.until(lambda: not page._retired_browsers)
        self.assertIsNone(session.credentials(config))
        self.assertIs(page.browser_stack.currentWidget(), page.browser_notice)

    def test_hidden_page_does_not_open_or_unlock_a_browser(self):
        self.local_folders = [self.folder('Workspace')]
        page = self.page()
        self.select_first(page)
        self.browser_factory.assert_not_called()
        page.show()
        self.app.processEvents()
        self.browser_factory.assert_called_once_with(self.local_folders[0].path)

    def test_remote_browse_failure_keeps_action_scope_without_local_fallback(self):
        local = self.folder('Shared')
        self.local_folders = [local]
        self.remote(['Shared'], 'profile')
        page = self.page()
        page.show()
        self.app.processEvents()
        self.browser_factory.reset_mock()
        self.browser_factory.side_effect = OSError('Connection unavailable')
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.wait(page)
        entry = next(entry for entry in self.entries(page) if entry.remote_context == Path('profile'))
        page.folder_tree.setCurrentItem(page._entry_items[page._entry_key(entry)])
        from features.rclone.ui.remote_browser import RemoteLocation
        self.assertTrue(all(isinstance(call.args[0], RemoteLocation)
                            for call in self.browser_factory.call_args_list))
        self.assertIn('Connection unavailable', page.browser_notice.text())
        self.assertIsNone(page._browser_view)
        self.assertEqual(page.selected_entry_name, 'Shared')
        self.assertEqual(page._selected_entry_key[2], 'profile')

    def test_home_server_uses_explicit_package_identity(self):
        self.remote(['CloudFolder'], 'ordinary')
        self.remote(['Share'], 'Network shares.session', feature='rclone')
        page = self.page()
        self.assertEqual([page.source_tabs.tabText(i) for i in range(3)], ['Local', 'Cloud', 'Home Server'])
        page.source_tabs.setCurrentIndex(self.tab(page, 'Home Server'))
        self.wait(page)
        self.assertEqual([entry.name for entry in self.entries(page)], ['Share'])
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.wait(page)
        self.assertEqual([entry.name for entry in self.entries(page)], ['CloudFolder'])

    def test_locked_cloud_account_groups_copies_and_discovers_more_remotes_after_unlock(self):
        from types import SimpleNamespace
        from features.rclone import session
        from features.rclone.ui_contributions import CopyContext
        from features.rclone.localcrypt.backend import LocalCryptFolder
        from features.rclone.ui.workspace_unlock import WorkspaceUnlockView
        self.browser_patcher.stop()
        local = self.folder('Shared')
        private_path = self.root / 'private-copy'
        private_path.mkdir()
        config, package = self.root / 'keys.session', self.root / 'keys.zip'
        self.addCleanup(session.forget, config)
        plain = SimpleNamespace(data=local.path, remote='Shared', context=config, package=package)
        private = SimpleNamespace(data=private_path, remote='Shared', context=config, package=package)
        crypt = LocalCryptFolder(private)
        def sources():
            rows = [RemoteFolderSource('keys — Local', lambda: ['Shared'], context=CopyContext(plain),
                                       get_local_folders=lambda: [local]),
                    RemoteFolderSource('keys — LocalCrypt', lambda: ['Shared'], context=CopyContext(private),
                                       get_local_folders=lambda: [crypt])]
            if session.names(config) is not None:
                rows.insert(0, RemoteFolderSource('keys (session)', lambda: session.names(config),
                                                  context=config, get_local_folders=lambda: [local]))
            return rows
        self.remotes.append(RegisteredContribution('rclone', 'rclone',
            RemoteFolderSourceContribution('rclone', sources)))
        page = self.page()
        page.show()
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.wait(page)
        self.assertEqual([page.credential_combo.itemText(i) for i in range(page.credential_combo.count())],
                         ['All', 'keys (locked)'])
        page.credential_combo.setCurrentIndex(1)
        self.assertEqual([entry.name for entry in self.entries(page)], ['Shared'])
        self.select_first(page)
        unlock = page._browser_view
        self.assertIsInstance(unlock, WorkspaceUnlockView)
        item = page.folder_tree.currentItem()
        self.assertEqual(item.data(0, qt.Qt.ItemDataRole.AccessibleDescriptionRole), 'Remote, locked')
        class Opened(qt.QWidget):
            idle = qt.Signal()
            def prepare_close(self):
                return True
        opened = Opened()
        with patch('ui_new.file_browser._browser_view', return_value=opened) as factory, patch(
                'features.rclone.session.read_package', return_value={
                    'Shared': {'type': 'crypt'}, 'Additional': {'type': 'drive'}}):
            unlock.password.setText('synthetic password')
            unlock.submit()
            self.until(lambda: page._browser_view is opened)
            self.wait(page)
            self.assertEqual([entry.name for entry in self.entries(page)], ['Additional', 'Shared'])
            self.assertEqual(page.credential_combo.currentText(), 'keys (session)')
            self.assertEqual(page.selected_entry_name, 'Shared')
            self.assertIs(page._browser_view, opened)
            factory.assert_called_once()
            for item in page._entry_items.values():
                self.assertEqual(item.data(0, qt.Qt.ItemDataRole.AccessibleDescriptionRole), 'Remote, unlocked')

    def test_unassociated_local_has_locked_cloud_placeholder_without_local_fallback(self):
        local = self.folder('Unassociated')
        self.local_folders = [local]
        config = self.root / 'loaded.conf'
        config.write_text('[Other]\ntype=local\n')
        self.remotes.append(RegisteredContribution('rclone', 'rclone', RemoteFolderSourceContribution(
            'rclone', lambda: [RemoteFolderSource('loaded', lambda: ['Other'], context=config,
                                                get_local_folders=lambda: [local])])))
        page = self.page()
        page.show()
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.wait(page)
        self.assertEqual([entry.name for entry in self.entries(page)], ['Other', 'Unassociated'])
        entry = next(entry for entry in self.entries(page) if entry.name == 'Unassociated')
        page.folder_tree.setCurrentItem(page._entry_items[page._entry_key(entry)])
        self.assertIsNone(page._browser_view)
        self.browser_factory.assert_not_called()
        self.assertIn('Load the matching credential package', page.browser_notice.text())
        self.assertIn('Credentials required', [page.credential_combo.itemText(i)
                                             for i in range(page.credential_combo.count())])
        self.assertEqual(page.folder_tree.currentItem().data(0, qt.Qt.ItemDataRole.AccessibleDescriptionRole),
                         'Remote, locked')

    def test_remote_with_default_local_matching_has_no_duplicate_placeholder(self):
        self.local_folders = [self.folder('Shared')]
        self.remote(['Shared'], 'account.conf', feature='rclone')
        page = self.page()
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.wait(page)
        self.assertEqual([entry.name for entry in self.entries(page)], ['Shared'])
        self.assertEqual(page.credential_combo.count(), 2)

    def test_real_credential_zip_unlock_browses_remote_contents_in_workspaces(self):
        from types import SimpleNamespace
        from commonUtils.archives.zip_access import open_archive
        from features.rclone import executable, session
        from features.rclone.ui_contributions import CopyContext
        from features.rclone.ui.workspace_unlock import WorkspaceUnlockView
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is not installed')
        self.browser_patcher.stop()
        local = self.folder('Workspace')
        cloud = self.root / 'remote' / 'Workspace'
        cloud.mkdir(parents=True)
        (cloud / 'remote-note.txt').write_text('Synthetic remote data')
        (local.path / 'local-note.txt').write_text('Local copy must not be browsed as Cloud')
        config, package = self.root / 'account.session', self.root / 'account.zip'
        self.addCleanup(session.forget, config)
        with open_archive(package, 'w', password='synthetic-password') as archive:
            archive.writestr('Workspace.txt', f'[Workspace]\ntype=alias\nremote={cloud}\n')
            archive.writestr('Additional.txt', f'[Additional]\ntype=alias\nremote={cloud}\n')
        association = SimpleNamespace(data=local.path, remote='Workspace', context=config, package=package)
        def sources():
            if session.names(config) is not None:
                return [RemoteFolderSource('account (session)', lambda: session.names(config),
                    context=config, get_local_folders=lambda: [local])]
            return [RemoteFolderSource('account — Local', lambda: ['Workspace'],
                context=CopyContext(association), get_local_folders=lambda: [local])]
        self.remotes.append(RegisteredContribution('rclone', 'rclone', RemoteFolderSourceContribution('rclone', sources)))
        with patch.object(executable, 'ensure_rclone', return_value=binary):
            page = self.page()
            page.resize(1100, 800)
            page.show()
            page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
            self.wait(page)
            self.select_first(page)
            unlock = page._browser_view
            self.assertIsInstance(unlock, WorkspaceUnlockView)
            unlock.password.setText('synthetic-password')
            unlock.submit()
            self.until(lambda: page._browser_view is not unlock)
            self.wait(page)
            view = page._browser_view
            self.assertIsNotNone(view)
            browser = view.file_browser
            self.until(lambda: not browser.busy)
            tree = browser.model.tree
            labels = {tree.entries[key].label for key in tree.children[tree.root]}
            self.assertEqual(labels, {'remote-note.txt'})
            self.assertEqual(view.provider.config_path, config)
            self.assertEqual(view.provider.remote, 'Workspace')
            self.assertEqual(page.selected_entry_name, 'Workspace')
            self.assertEqual([entry.name for entry in self.entries(page)], ['Additional', 'Workspace'])
            self.assertFalse(config.exists())
            self.assertEqual(sorted(cloud.iterdir()), [cloud / 'remote-note.txt'])

    def test_actions_are_below_sources_and_files_uses_full_height(self):
        page = self.page()
        page.resize(1100, 800)
        page.show()
        self.app.processEvents()
        files, actions, sources = page.panes.docks
        self.assertLess(sources.geometry().bottom(), actions.geometry().top())
        self.assertLess(actions.geometry().right(), files.geometry().left())
        self.assertLessEqual(files.geometry().top(), sources.geometry().top())
        self.assertGreaterEqual(files.geometry().bottom(), actions.geometry().bottom())
        before = sources.height()
        page.panes.resizeDocks([sources, actions], [250, 450], qt.Qt.Orientation.Vertical)
        self.app.processEvents()
        self.assertLess(sources.height(), before)
        self.assertGreater(page.folder_tree.height(), 0)
        self.assertGreater(actions.height(), 120)

    def test_info_and_actions_are_separate_and_refresh_is_in_folder_list(self):
        self.local_folders = [self.folder('One'), self.folder('Two')]
        page = self.page()
        page.resize(1100, 800)
        page.show()
        self.app.processEvents()
        files, actions, sources = page.panes.docks
        self.assertIs(page.details_tabs.currentWidget(), page.detail_scroll)
        self.assertEqual([page.details_tabs.tabText(i) for i in range(2)], ['Info', 'Actions'])
        self.assertEqual(page.refresh_button.text(), '')
        self.assertFalse(page.refresh_button.icon().isNull())
        self.assertEqual(page.refresh_button.accessibleName(), 'Refresh folders')
        button_position = page.refresh_button.mapTo(sources.widget(), qt.QPoint(0, 0))
        self.assertIs(page.refresh_button.parentWidget(), page.folder_list_panel)
        self.assertIs(page.folder_tree.parentWidget(), page.folder_list_panel)
        combo_position = page.credential_combo.mapTo(sources.widget(), qt.QPoint(0, 0))
        self.assertGreaterEqual(button_position.y(), combo_position.y() + page.credential_combo.height())
        self.assertLess(page.refresh_button.y(), page.folder_tree.y())
        self.assertGreater(button_position.x(), sources.widget().width() / 2)
        self.assertLess(sources.width(), page.panes.width() * .24)
        for entry in self.entries(page):
            page.folder_tree.setCurrentItem(page._entry_items[page._entry_key(entry)])
            self.wait(page)
            self.assertIn(str(entry.local.path), [label.text() for label in
                          page.info_scroll.widget().findChildren(qt.QLabel)])
            self.assertFalse(page.info_scroll.widget().findChildren(qt.QPushButton))
            self.assertNotIn('General', [group.title() for group in
                             page.detail_scroll.widget().findChildren(qt.QGroupBox)])
            page.details_tabs.setCurrentWidget(page.info_scroll)
        page._show_empty_state('Select a folder')
        self.assertNotIn(str(entry.local.path), [label.text() for label in
                         page.info_scroll.widget().findChildren(qt.QLabel)])

    def test_busy_browser_is_retained_until_idle_and_panes_can_unlock(self):
        self.local_folders = [self.folder('One'), self.folder('Two')]
        page = self.page()
        page.show()
        self.app.processEvents()
        self.select_first(page)
        old = page._browser_view
        old.prepare_close = Mock(return_value=False)
        second = next(entry for entry in self.entries(page) if entry.name == 'Two')
        page.folder_tree.setCurrentItem(page._entry_items[page._entry_key(second)])
        self.assertIn(old, page._retired_browsers)
        self.assertIsNot(old, page._browser_view)
        old.prepare_close.return_value = True
        old.idle.emit()
        self.assertNotIn(old, page._retired_browsers)
        self.assertTrue(page.panes.locked)
        for dock in page.panes.docks:
            self.assertEqual(dock.features(), qt.QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        page.panes.set_locked(False)
        for dock in page.panes.docks:
            self.assertTrue(dock.features() & qt.QDockWidget.DockWidgetFeature.DockWidgetFloatable)
            self.assertFalse(dock.features() & qt.QDockWidget.DockWidgetFeature.DockWidgetClosable)

    def test_real_embedded_browser_navigation_does_not_change_actions_root(self):
        self.browser_patcher.stop()
        root = self.folder('Workspace')
        child = root.path / 'child'
        child.mkdir()
        (child / 'note.txt').write_text('hello')
        self.local_folders = [root]
        page = self.page()
        page.resize(1250, 750)
        page.show()
        self.select_first(page)
        browser = page._browser_view.file_browser
        self.assertFalse(browser.preview_toggle.isChecked())
        self.assertTrue(browser.preview_panel.isHidden())
        browser.preview_toggle.setChecked(True)
        browser.navigate(child)
        self.until(lambda: browser.navigation.directory == child)
        self.assertEqual(page.selected_entry_name, 'Workspace')
        self.assertEqual(page._selected_entry_key[-1], str(root.path))
        self.assertIn(str(root.path), [label.text() for label in page.info_scroll.widget().findChildren(qt.QLabel)])
        self.assertIs(page.browser_stack.currentWidget(), page._browser_view)
        self.assertTrue(all(dock.width() >= dock.minimumWidth() for dock in page.panes.docks))
        # Refresh keeps the browsed child and retained view for the same workspace.
        view = page._browser_view
        page.refresh()
        self.wait(page)
        self.assertIs(page._browser_view, view)
        self.assertEqual(browser.navigation.directory, child)

    def test_private_folder_keeps_rclone_tools_without_local_detectors(self):
        from types import SimpleNamespace
        from features.contributions import FolderFeatureContribution
        from features.rclone.localcrypt.backend import LocalCryptFolder
        from features.rclone.ui_contributions import get_contributions
        from models.folder_entry import FolderEntry
        from features.calibre import ui_contributions as calibre
        from features.obsidian import ui_contributions as obsidian
        from features.minecraft import ui_contributions as minecraft
        local_detector = Mock(side_effect=AssertionError('Private copy reached local-only detector'))
        local_only = FolderFeatureContribution('Local only', local_detector, lambda entry: [])
        tools = [RegisteredContribution('local', 'Local', local_only)]
        for module in (calibre, obsidian, minecraft):
            feature = module.get_contributions()
            tools.extend(RegisteredContribution(feature.id, feature.label, tool) for tool in feature.folder_features)
        rclone_tool = get_contributions().folder_features[0]
        tools.append(RegisteredContribution('rclone', 'rclone', rclone_tool))
        from features.rclone import session
        config, package = self.root / 'keys.session', self.root / 'keys.zip'
        session.remember(config, {'Legacy': {'type': 'crypt'}}, package_path=package)
        self.addCleanup(session.forget, config)
        connection = SimpleNamespace(data=self.root / 'ciphertext', remote='Legacy', package=package, context=config)
        entry = FolderEntry('Legacy', local=LocalCryptFolder(connection), remote_name='Legacy',
                            remote_source='rclone', remote_context=self.root / 'keys.session')
        with patch('features.registry.get_folder_features', return_value=tools):
            page = self.page()
            page._show_entry(entry)
            self.wait(page)
        local_detector.assert_not_called()
        self.assertTrue(page._tools_status.isHidden())
        labels = {button.text() for button in page.detail_scroll.widget().findChildren(qt.QPushButton)}
        self.assertTrue({'Push...', 'Pull'}.issubset(labels), labels)
        for removed in ('Browse encrypted copy', 'Browse in Logistics', 'Open Folder', 'Browse'):
            self.assertNotIn(removed, labels)
        # Ordinary local entries still go through availability detection.
        local_detector.side_effect = None
        local_detector.return_value = False
        page._show_entry(FolderEntry('Local', local=self.folder('Local')))
        self.wait(page)
        local_detector.assert_called_once()

    def test_source_switch_refreshes_but_show_and_credential_selection_do_not(self):
        read_names = self.remote(['Shared', 'Remote-Only'], 'profile')
        self.local_folders = [self.folder('Local'), self.folder('Shared')]
        page = self.page()
        page.show()
        self.app.processEvents()
        self.assertTrue(page.source_tabs.isVisible())
        self.assertGreater(page.source_tabs.height(), 0)
        read_names.assert_called_once_with()
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.wait(page)
        self.assertEqual(read_names.call_count, 2)
        page.credential_combo.setCurrentIndex(1)
        page.credential_combo.setCurrentIndex(0)
        self.assertEqual(read_names.call_count, 2)
        page.refresh()
        self.wait(page)
        self.assertEqual(read_names.call_count, 3)
        self.assertEqual({entry.name for entry in self.entries(page)}, {'Local', 'Shared', 'Remote-Only'})
        page.close()

    def test_remote_tab_recovers_empty_snapshot_and_retries_failed_refresh(self):
        from threading import Event
        self.local_folders = [self.folder('Local')]
        read_names = self.remote([], 'profile')
        page = self.page()
        entered, release = Event(), Event()
        def names():
            entered.set()
            release.wait(5)
            return ['Restored']
        read_names.side_effect = names
        self.addCleanup(release.set)
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.until(entered.is_set)
        self.assertTrue(page.discovery.busy)
        release.set()
        self.wait(page)
        self.assertEqual([entry.name for entry in self.entries(page)], ['Local', 'Restored'])
        read_names.side_effect = OSError('temporarily unavailable')
        page.refresh_button.click()
        self.wait(page)
        self.assertEqual([entry.name for entry in self.entries(page)], ['Local', 'Restored'])
        self.assertIn('temporarily unavailable', page.discovery.message.text())
        read_names.side_effect = None
        read_names.return_value = ['Recovered']
        page.refresh_button.click()
        self.wait(page)
        self.assertEqual([entry.name for entry in self.entries(page)], ['Local', 'Recovered'])

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
                               if window.tabs.tabText(index) == 'Workspaces')
            self.assertEqual(window.tabs.tabText(0), 'File Browser')
            window.launch_stack.setCurrentWidget(window.hub)
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
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.wait(page)
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

    def test_equal_source_labels_keep_credentials_and_selection_distinct(self):
        self.remote(['One'], 'one', feature='one', label='Same')
        self.remote(['Two'], 'two', feature='two', label='Same')
        page = self.page()
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.wait(page)
        page.credential_combo.setCurrentIndex(2)
        page.refresh()
        self.wait(page)
        self.assertEqual(page.credential_combo.currentData(), Path('two'))
        self.assertEqual([entry.name for entry in self.entries(page)], ['Two'])

    def test_removed_credential_returns_to_all_in_the_same_category(self):
        self.remote(['One'], 'one', feature='one', label='One')
        self.remote(['Two'], 'two', feature='two', label='Two')
        page = self.page()
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.wait(page)
        page.credential_combo.setCurrentIndex(1)
        self.remotes.pop(0)
        page.refresh()
        self.wait(page)
        self.assertEqual(page.source_tabs.tabText(page.source_tabs.currentIndex()), 'Cloud')
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
        page.credential_combo.setCurrentText('Others')
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
        self.assertTrue(page.source_tabs.isVisible())
        self.remote(['New'], 'profile')
        page.refresh()
        self.wait(page)
        self.app.processEvents()
        self.assertTrue(page.source_tabs.isVisible())
        self.assertGreater(page.source_tabs.height(), 0)
        page.source_tabs.setCurrentIndex(self.tab(page, 'Cloud'))
        self.wait(page)
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
        self.select_first(page)
        titles = [label for label in page.detail_scroll.widget().findChildren(qt.QLabel)
                  if label.text() == self.local_folders[0].name]
        self.assertTrue(titles)
        self.assertTrue(all(label.textFormat() == qt.Qt.TextFormat.PlainText for label in titles))
