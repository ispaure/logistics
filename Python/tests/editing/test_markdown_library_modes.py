"""Documentation navigation stays fixed; notes mutations use their provider."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.ui.markdown.window import MarkdownWindow
from features.text_editor.notes import NotesLibrary
from features.text_editor.ui.notes_library import NotesLibraryWindow
from features.text_editor.ui.notes_offer import NotesFolderOffer


class LibraryModeTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_real_workspace_browser_offers_root_vault(self):
        from desktop.file_browser import BrowserView
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            view = BrowserView(root_path=root)
            view.show()
            try:
                binding = view._extensions_by_feature['text_editor']
                offer = binding.controller.notes_offer
                self.wait_until(lambda: not offer.progress.busy and offer.location is not None)
                self.assertIsNotNone(offer.candidate, offer.progress.message.text())
                self.assertFalse(offer.isHidden())
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
            with patch.object(qt.QInputDialog, 'getText', return_value=('New note', True)):
                window.new_note()
            self.wait_until(lambda: not window.progress.busy)
            self.assertTrue((root / 'New folder/New note.md').exists())
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

    def test_desktop_offer_appears_for_vault_and_hides_when_entering_regular_folder(self):
        class Browser(qt.QWidget):
            directory_changed = qt.Signal(object)
        with self.temporary_directory() as directory:
            root = Path(directory)
            (root / '.obsidian').mkdir()
            (root / 'Regular').mkdir()
            browser = Browser()
            qt.QVBoxLayout(browser)
            browser.navigation = SimpleNamespace(directory=root)
            offer = NotesFolderOffer(browser)
            browser.show()
            self.wait_until(lambda: offer.candidate is not None)
            self.assertFalse(offer.isHidden())
            with patch('features.text_editor.ui.notes_library.open_notes') as opened:
                offer.open()
                self.assertEqual(opened.call_args.kwargs['root'], '')
                self.assertFalse(opened.call_args.kwargs['remote'])
            browser.navigation.directory = root / 'Regular'
            browser.directory_changed.emit(root / 'Regular')
            self.wait_until(lambda: not offer.progress.busy)
            self.assertIsNone(offer.candidate)
            self.assertTrue(offer.isHidden())
            self.assertTrue(offer.prepare_close())
            browser.close()
