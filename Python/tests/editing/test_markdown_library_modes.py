"""Documentation navigation stays fixed; notes mutations use their provider."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.ui.markdown.window import MarkdownWindow
from features.notes_library.notes import NotesLibrary
from features.notes_library.ui.notes_library import NotesLibraryWindow
from features.notes_library.ui.notes_offer import NotesFolderOffer


class LibraryModeTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_windows_link_cache_detects_new_names_when_directory_times_do_not_change(self):
        from types import SimpleNamespace
        from features.notes_library import notes
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Vault/Topics').mkdir(parents=True)
            (root / 'Vault/Home.md').write_text('# Home')
            (root / 'Vault/Topics/Tech.md').write_text('# Tech')
            provider = LocalFiles(root)
            library = NotesLibrary(provider, 'Vault')
            stamp = SimpleNamespace(st_dev=1, st_ino=2, st_mtime_ns=3, st_ctime_ns=4)
            location = SimpleNamespace(stat=lambda: stamp)
            with patch.object(notes, 'os', SimpleNamespace(name='nt')), \
                    patch.object(provider, 'transfer_location', return_value=location), \
                    patch.object(provider, 'list', wraps=provider.list) as listing:
                self.assertEqual(library.link('Vault/Home.md', 'Tech')[0], 'Vault/Topics/Tech.md')
                listing.reset_mock()
                self.assertEqual(library.link('Vault/Home.md', 'Tech')[0], 'Vault/Topics/Tech.md')
                listing.assert_not_called()
                (root / 'Vault/Other').mkdir()
                (root / 'Vault/Other/Tech.md').write_text('# Duplicate')
                with self.assertRaisesRegex(ValueError, 'Several notes'):
                    library.link('Vault/Home.md', 'Tech')

    def test_real_workspace_browser_opens_root_vault_without_prompt(self):
        from desktop.file_browser import BrowserView
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            view = BrowserView(root_path=root)
            view.show()
            try:
                binding = view._extensions_by_feature['text_editor']
                self.assertFalse(hasattr(binding.controller, 'notes_offer'))
                self.wait_until(lambda: view.file_browser.navigation.directory == root)
            finally:
                view.close()

    def test_note_links_find_nested_names_and_reject_ambiguity(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            for folder in ('Vault', 'Vault/Current', 'Vault/Topics', 'Vault/.obsidian'):
                (root / folder).mkdir()
            (root / 'Vault/Current/Home.md').write_text('# **[[Tech]]**')
            (root / 'Vault/Topics/Tech.md').write_text('# Tech')
            (root / 'Outside.md').write_text('# Outside')
            library = NotesLibrary(LocalFiles(root), 'Vault')
            for target in ('Tech', 'Tech.md#heading', 'Topics/Tech.md'):
                path, _ = library.link('Vault/Current/Home.md', target)
                self.assertEqual(path, 'Vault/Topics/Tech.md')
            (root / 'Vault/Tech.md').write_text('# Root')
            self.assertEqual(library.link('Vault/Current/Home.md', 'Tech.md')[0], 'Vault/Tech.md')
            (root / 'Vault/Tech.md').unlink()
            (root / 'Vault/Current/Other').mkdir()
            (root / 'Vault/Current/Other/Tech.md').write_text('# Duplicate')
            with self.assertRaisesRegex(ValueError, 'Several notes'):
                library.link('Vault/Current/Home.md', 'Tech.md')
            for target in ('../../Outside.md', '../.obsidian/private.md', '%2FOutside.md', 'https://example.com/Tech.md'):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    library.link('Vault/Current/Home.md', target)

    def test_note_lookup_is_cancellable_and_bounded(self):
        from commonUtils.runtime.operations import OperationCancelled
        with self.temporary_directory() as directory:
            provider = LocalFiles(Path(directory))
            library = NotesLibrary(provider)
            with self.assertRaises(OperationCancelled):
                library.link('Home.md', 'Tech.md', cancelled=lambda: True)
            rows = [dict(name=f'{index}.md', path=f'{index}.md', directory=False) for index in range(10001)]
            with patch.object(provider, 'list', return_value=rows), self.assertRaisesRegex(ValueError, '10,000-entry'):
                library.link('Home.md', 'Tech.md')

    def test_desktop_wiki_link_opens_note_in_an_unloaded_subfolder(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            (root / 'Topics').mkdir()
            (root / 'Home.md').write_text('# **[[Tech]]**')
            (root / 'Topics/Tech.md').write_text('# Tech')
            window = NotesLibraryWindow(lambda: LocalFiles(root), 'Notes')
            window.show()
            self.wait_until(lambda: not window.progress.busy)
            window.open_note('Home.md')
            self.wait_until(lambda: not window.progress.busy)
            window.viewer.follow_link(qt.QUrl('Tech.md'))
            self.wait_until(lambda: not window.progress.busy)
            self.assertEqual(window.storage.path, (root / 'Topics/Tech.md').resolve(), window.viewer.status.text())
            window.close()

    def test_documentation_keeps_heading_titles_and_fixed_tree_with_option_editing(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            page = root / 'filename.md'
            page.write_text('# Human title\n')
            with patch.object(qt.QApplication, 'keyboardModifiers', return_value=qt.Qt.KeyboardModifier.AltModifier):
                window = MarkdownWindow(page, directory=root)
            self.assertTrue(window.viewer.allow_edit)
            tree = window.viewer.wiki.tree
            self.assertEqual(tree.topLevelItem(0).text(0), 'Human title')
            self.assertEqual(tree.dragDropMode(), qt.QAbstractItemView.DragDropMode.NoDragDrop)
            self.assertEqual(tree.editTriggers(), qt.QAbstractItemView.EditTrigger.NoEditTriggers)
            window.close()

    def test_notes_create_and_move_refresh_paths_and_preserve_filename_labels(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            (root / 'filename.md').write_text('# Human title\n')
            window = NotesLibraryWindow(lambda: LocalFiles(root), 'Notes')
            window.show()
            self.wait_until(lambda: not window.progress.busy)
            self.assertEqual(window.items['filename.md'].text(0), 'filename.md')
            window.open_note('filename.md')
            self.wait_until(lambda: not window.progress.busy)
            with patch.object(qt.QInputDialog, 'getText', return_value=('New folder', True)):
                window.new_entry(folder=True)
            self.wait_until(lambda: not window.progress.busy)
            self.assertTrue((root / 'New folder').is_dir())
            window.move_entry('filename.md', 'New folder/renamed.md')
            self.wait_until(lambda: not window.progress.busy)
            self.assertFalse((root / 'filename.md').exists())
            self.assertEqual(window.storage.path, (root / 'New folder/renamed.md').resolve())
            self.assertEqual(window.history, ['New folder/renamed.md'])
            self.assertIn('New folder/renamed.md', window.items)
            window.tree.setCurrentItem(window.items['New folder'])
            (root / 'New folder/Unopened').mkdir()
            def choose_markdown():
                menu = self.app.activePopupWidget()
                menu.close()
                next(action for action in menu.actions() if action.text() == 'Markdown').trigger()
            with patch.object(qt.QInputDialog, 'getText', return_value=('New note', True)), \
                    patch.object(qt.QInputDialog, 'getItem', return_value=('New folder/Unopened/', True)):
                qt.QTimer.singleShot(0, choose_markdown)
                window.new_note()
            self.wait_until(lambda: not window.progress.busy)
            self.assertTrue((root / 'New folder/Unopened/New note.md').exists())
            self.assertEqual(window.storage.path.name, 'New note.md')
            window.close()

    def test_unsaved_note_can_cancel_a_move_without_changing_the_tree_or_file(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            (root / 'Note.md').write_text('# Original')
            window = NotesLibraryWindow(lambda: LocalFiles(root), 'Notes')
            window.show()
            self.wait_until(lambda: not window.progress.busy)
            window.open_note('Note.md')
            self.wait_until(lambda: not window.progress.busy)
            window.viewer.set_edit_mode('source')
            window.viewer.editor.insertPlainText('Unsaved ')
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Cancel):
                window.move_entry('Note.md', 'Moved.md')
            self.assertFalse(window.progress.busy)
            self.assertTrue((root / 'Note.md').exists())
            self.assertFalse((root / 'Moved.md').exists())
            self.assertTrue(window.viewer.is_modified)
            self.assertIn('Note.md', window.items)
            with patch.object(qt.QMessageBox, 'warning', return_value=qt.QMessageBox.StandardButton.Discard):
                window.close()

    def test_mutations_reject_hidden_paths_escapes_overwrites_and_remote_writes(self):
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / 'Vault').mkdir()
            (root / 'Vault/a.md').write_text('# A')
            (root / 'Vault/b.md').write_text('# B')
            provider = LocalFiles(root)
            library = NotesLibrary(provider, 'Vault')
            for destination in ('outside.md', 'Vault/.obsidian/a.md', 'Vault/../outside.md', 'Vault/a.txt'):
                with self.subTest(destination=destination), self.assertRaises(ValueError):
                    library.move('Vault/a.md', destination)
            with self.assertRaises(FileExistsError):
                library.move('Vault/a.md', 'Vault/b.md')
            self.assertEqual((root / 'Vault/a.md').read_text(), '# A')
            provider.remote_storage = True
            with self.assertRaises(ValueError):
                library.move('Vault/a.md', 'Vault/c.md')
            with self.assertRaises(ValueError):
                library.create_folder('Remote folder')

    def choose(self, offer, label):
        next(button for button in offer.dialog.buttons() if button.text() == label).click()

    def test_desktop_choice_opens_notes_without_publishing_folder(self):
        from commonUtils.ui.file_browser import FileBrowser
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            (root / 'Regular').mkdir()
            browser = FileBrowser(calculate_folder_sizes=False)
            offer = NotesFolderOffer(browser)
            browser.show()
            browser.set_directory(root)
            self.wait_until(lambda: offer.dialog is not None)
            self.assertIsNone(browser.navigation.directory)
            self.assertIsNone(browser.views.root)
            with patch('features.notes_library.ui.notes_library.open_notes') as opened:
                self.choose(offer, 'Open as Notes Library')
                self.assertEqual(opened.call_args.kwargs['root'], '')
                self.assertFalse(opened.call_args.kwargs['remote'])
            self.assertIsNone(browser.navigation.directory)
            browser.set_directory(root / 'Regular')
            self.wait_until(lambda: not offer.progress.busy)
            self.assertEqual(browser.navigation.directory, root / 'Regular')
            self.assertIsNone(offer.candidate)
            self.assertIsNone(offer.dialog)
            self.assertTrue(offer.prepare_close())
            browser.close()

    def test_cancel_and_superseded_desktop_choices_keep_folder_history(self):
        from commonUtils.ui.file_browser import FileBrowser
        with self.temporary_directory() as directory:
            root = Path(directory)
            vault = root / 'Vault'
            (vault / '.obsidian').mkdir(parents=True)
            browser = FileBrowser(root, calculate_folder_sizes=False)
            offer = NotesFolderOffer(browser)
            browser.show()
            try:
                browser.navigate(vault)
                self.wait_until(lambda: offer.dialog is not None)
                self.assertEqual(browser.navigation.directory, root)
                offer.dialog.reject()
                self.assertEqual(browser.navigation.directory, root)
                self.assertEqual(browser.navigation.history, [root])
                browser.navigate(vault)
                self.wait_until(lambda: offer.dialog is not None)
                stale = offer.dialog
                browser.navigate(root)
                self.assertIsNone(offer.dialog)
                self.assertEqual(browser.navigation.directory, root)
                self.assertFalse(stale.isVisible())
                browser.navigate(vault)
                self.wait_until(lambda: offer.dialog is not None)
                self.choose(offer, 'Browse Files')
                self.assertEqual(browser.navigation.directory, vault)
                self.assertEqual(browser.navigation.history, [root, vault])
                browser.navigation._history(-1)
                self.assertEqual(browser.navigation.directory, root)
                browser.navigation._history(1)
                self.wait_until(lambda: offer.dialog is not None)
                self.assertEqual(browser.navigation.position, 0)
                self.choose(offer, 'Browse Files')
                self.assertEqual(browser.navigation.position, 1)
                self.assertEqual(browser.navigation.history, [root, vault])
            finally:
                offer.prepare_close()
                self.wait_until(lambda: not offer.progress.busy)
                browser.close()

    def test_provider_initial_listing_waits_for_choice(self):
        from commonUtils.ui.resources.browser import ResourceBrowser
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            (root / 'Home.md').write_text('# Home')
            provider = LocalFiles(root)
            browser = ResourceBrowser(provider)
            offer = NotesFolderOffer(browser)
            browser.show()
            try:
                self.wait_until(lambda: offer.dialog is not None)
                self.assertIsNone(browser.views.root)
                self.assertEqual(browser.history, [])
                self.choose(offer, 'Browse Files')
                self.wait_until(lambda: browser.views.root == root)
                self.assertEqual(browser.history, [root])
                browser.refresh()
                self.wait_until(lambda: not browser.operation.busy)
                self.assertIsNone(offer.dialog)
            finally:
                offer.prepare_close()
                self.wait_until(lambda: not offer.progress.busy)
                browser.stop()
                self.wait_until(lambda: not browser.busy)
                browser.close()

    def test_provider_choice_cannot_publish_or_open_after_access_is_revoked(self):
        from commonUtils.ui.resources.browser import ResourceBrowser
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            for choice in ('Browse Files', 'Open as Notes Library'):
                provider = LocalFiles(root)
                provider.revoked = False
                def check():
                    if provider.revoked:
                        raise ValueError('Access revoked')
                provider._check_active = check
                browser = ResourceBrowser(provider)
                offer = NotesFolderOffer(browser)
                browser.show()
                try:
                    self.wait_until(lambda: offer.dialog is not None)
                    provider.revoked = True
                    with patch('features.notes_library.ui.notes_library.open_notes') as opened:
                        self.choose(offer, choice)
                        opened.assert_not_called()
                    self.assertIsNone(browser.views.root)
                    self.assertEqual(browser.history, [])
                finally:
                    offer.prepare_close()
                    self.wait_until(lambda: not offer.progress.busy)
                    browser.stop()
                    self.wait_until(lambda: not browser.busy)
                    browser.close()

    def test_tree_and_columns_wait_for_choice_before_revealing_vault_children(self):
        from commonUtils.ui.file_browser import FileBrowser
        with self.temporary_directory() as directory:
            root = Path(directory)
            vault = root / 'Vault'
            (vault / '.obsidian').mkdir(parents=True)
            (vault / 'Home.md').write_text('# Home')
            for mode in (0, 2):
                browser = FileBrowser(root, calculate_folder_sizes=False)
                offer = NotesFolderOffer(browser)
                browser.show()
                try:
                    self.wait_until(lambda: browser.model.index(str(vault)).isValid())
                    index = browser.model.index(str(vault))
                    browser.view_selector.setCurrentIndex(mode)
                    if mode == 0:
                        index = browser.sort_model.mapFromSource(index)
                        browser.tree.expand(index)
                    else:
                        browser.views.columns.setCurrentIndex(index)
                    saved = qt.QPersistentModelIndex(index)
                    self.wait_until(lambda: offer.dialog is not None)
                    index = qt.QModelIndex(saved)
                    if mode == 0:
                        self.assertFalse(browser.tree.isExpanded(index))
                    else:
                        self.assertFalse(any(column.rootIndex() == index
                                             for column in browser.views.columns.findChildren(qt.QListView)))
                    self.assertEqual(browser.navigation.directory, root)
                    self.choose(offer, 'Browse Files')
                    if mode == 0:
                        self.assertTrue(browser.tree.isExpanded(index),
                                        (offer.location, offer.accepted, browser.navigation.directory))
                    else:
                        self.wait_until(lambda: any(column.rootIndex() == index
                            for column in browser.views.columns.findChildren(qt.QListView)))
                    self.assertEqual(browser.views.root, root)
                finally:
                    offer.prepare_close()
                    self.wait_until(lambda: not offer.progress.busy)
                    browser.close()

    def test_close_during_folder_probe_does_not_show_a_late_choice(self):
        from threading import Event
        from commonUtils.ui.file_browser import FileBrowser
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            entered, release = Event(), Event()
            provider = LocalFiles(root)
            original = provider.list
            def slow(*args, **kwargs):
                entered.set()
                release.wait(5)
                return original(*args, **kwargs)
            browser = FileBrowser(calculate_folder_sizes=False)
            offer = NotesFolderOffer(browser)
            try:
                with patch('services.documents.storage.local_document_provider', return_value=provider), \
                        patch.object(provider, 'list', side_effect=slow):
                    browser.set_directory(root)
                    self.wait_until(entered.is_set)
                    self.assertFalse(offer.prepare_close())
                    release.set()
                    self.wait_until(lambda: not offer.progress.busy)
                self.assertIsNone(offer.dialog)
                self.assertIsNone(browser.views.root)
            finally:
                release.set()
                offer.prepare_close()
                self.wait_until(lambda: not offer.progress.busy)
                browser.close()

    def test_reentering_a_cancelled_probe_still_requires_a_choice(self):
        from threading import Event
        from commonUtils.ui.file_browser import FileBrowser
        with self.temporary_directory() as directory:
            root = Path(directory)
            for name in ('First', 'Second'):
                (root / name / '.obsidian').mkdir(parents=True)
            entered, release = Event(), Event()
            class Slow(LocalFiles):
                def list(self, *args, **kwargs):
                    if not entered.is_set():
                        entered.set()
                        release.wait(5)
                    return super().list(*args, **kwargs)
            browser = FileBrowser(root, calculate_folder_sizes=False)
            offer = NotesFolderOffer(browser)
            try:
                with patch('services.documents.storage.local_document_provider', side_effect=Slow):
                    browser.navigate(root / 'First')
                    self.wait_until(entered.is_set)
                    browser.navigate(root / 'Second')
                    browser.navigate(root / 'First')
                    release.set()
                    self.wait_until(lambda: offer.dialog is not None)
                    self.assertEqual(browser.navigation.directory, root)
                    self.assertEqual(offer.location, root / 'First')
                    self.choose(offer, 'Browse Files')
                    self.assertEqual(browser.navigation.directory, root / 'First')
            finally:
                release.set()
                offer.prepare_close()
                self.wait_until(lambda: not offer.progress.busy)
                browser.close()
