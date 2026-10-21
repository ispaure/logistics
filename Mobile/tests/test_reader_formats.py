"""Comic and EPUB controls expose only settings usable by that format."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from commonUtils.runtime.document_access import LocalDocuments
from logisticsmobile.app import LogisticsMobile
from services.documents.readers import PrivateReader
from Mobile.native_tests.tests.logisticsmobile.fixtures import make_books


def labels(widget):
    result = [str(getattr(widget, 'text', ''))]
    for child in getattr(widget, 'children', ()):
        result.extend(labels(child))
    content = getattr(widget, 'content', None)
    if content is not None:
        result.extend(labels(content))
    return result


class ReaderFormatTests(unittest.TestCase):
    def test_imported_and_provider_comic_controls_preserve_epub_preferences(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            epub, comic = make_books(fixtures)

            def check(actions, tools, appearance, is_comic):
                menu = {title for title, _ in actions}
                self.assertIn('All documents', menu)
                tools_text = '\n'.join(labels(tools)).lower()
                form = '\n'.join(labels(appearance)).lower()
                if is_comic:
                    self.assertIn('Info…', menu)
                    for title in ('Read aloud…', 'Find in chapter…', 'Contents and bookmarks…',
                                  'Previous comic', 'Next comic', 'First comic page', 'Last comic page'):
                        self.assertNotIn(title, menu)
                    self.assertNotIn('bookmark', tools_text)
                    self.assertNotIn('save as', tools_text)
                    self.assertNotIn('discard changes', tools_text)
                    for text in ('font', 'spacing', 'margin', 'theme', 'maximum width'):
                        self.assertNotIn(text, form)
                    self.assertIn('comic page layout', form)
                    self.assertIn('Fit comic page', menu)
                else:
                    self.assertIn('Read aloud…', menu)
                    self.assertIn('bookmark', tools_text)
                    self.assertIn('reading font size', form)
                    self.assertNotIn('comic page layout', form)
                    self.assertNotIn('Fit comic page', menu)
                    self.assertNotIn('Previous comic', menu)

            async def exercise():
                app.show_cloud(present=False)
                for path, kind in ((comic, 'comic'), (epub, 'epub')):
                    record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), path)
                    await app.open_book(record['id'])
                    owner = app.readers.active
                    owner.show_reader_appearance()
                    check(owner.reader_actions.actions, owner.reader_tools_view, owner.reader_appearance, kind == 'comic')
                    if kind == 'comic':
                        comic_menu = [title for title, _ in owner.reader_actions.actions]
                        with patch.object(app.main_window, 'dialog', new=AsyncMock()) as dialog, \
                                patch('logisticsmobile.reader_chrome.toga.InfoDialog') as info:
                            await owner.show_comic_info()
                            info.assert_called_once_with('Comic path', str(owner.library_store.path(record['id'], '.cbz')))
                            dialog.assert_awaited_once_with(info.return_value)
                        comic_tools = labels(owner.reader_tools_view)
                        before = dict(app.preferences.values)
                        owner.reader_layout.value = 'single'
                        await owner.apply_reader_appearance()
                        for key in before.keys() - {'comic_layout'}:
                            self.assertEqual(app.preferences.values[key], before[key])
                        self.assertEqual(owner.book_record['position'], 0)
                    self.assertTrue(app.close_session(owner.session.id))
                    # Same UI contracts for Local/LocalCrypt and read-only remote previews.
                    for read_only in (False, True):
                        reader = PrivateReader(path.name, path.read_bytes())
                        reader.key = record['id']
                        reader.read_only = read_only
                        app.show_home()
                        with patch.object(app.crypt_copies, 'open', return_value=reader):
                            self.assertTrue(await app.open_crypt(copies=app.crypt_copies, key=record['id']))
                        provider = app.private_sessions.active
                        provider.show_provider_layout()
                        check(provider.crypt_actions_menu.actions, provider.crypt_tools_view,
                              provider.provider_appearance, kind == 'comic')
                        if kind == 'comic':
                            with patch.object(app.main_window, 'dialog', new=AsyncMock()) as dialog, \
                                    patch('logisticsmobile.provider_ui.toga.InfoDialog') as info, \
                                    patch.object(provider.manager, 'available', return_value=True):
                                await provider.show_provider_comic_info()
                                info.assert_called_once_with('Comic path', str(app.crypt_copies._data(record['id'])))
                                dialog.assert_awaited_once_with(info.return_value)
                            with patch.object(app.main_window, 'dialog', new=AsyncMock()) as dialog, \
                                    patch.object(provider.manager, 'available', return_value=False):
                                await provider.show_provider_comic_info()
                                dialog.assert_not_awaited()
                            # This synthetic encrypted reader has no backing
                            # folder; the imported library copy does.
                            unsupported = {'Show in folder'}
                            if read_only:
                                unsupported.add('Edit metadata…')
                            self.assertEqual([title for title, _ in provider.crypt_actions_menu.actions],
                                             [title for title in comic_menu if title not in unsupported])
                            self.assertEqual(labels(provider.crypt_tools_view), comic_tools)
                            before = dict(app.preferences.values)
                            provider.provider_layout.value = 'auto'
                            await provider.apply_provider_layout()
                            for key in before.keys() - {'comic_layout'}:
                                self.assertEqual(app.preferences.values[key], before[key])
                        provider.crypt_actions_menu.invoke(dict(provider.crypt_actions_menu.actions)['All documents'])
                        self.assertEqual(app.native_host.state.destination, 'documents')
                        self.assertFalse(app.routes.screens['documents'])
                        self.assertIn(provider.session.id, app.workspace.sessions)
                        self.assertTrue(app.private_sessions.close(provider.session.id, discard=True))
                await app.readers.catalog.metadata_task
                await app.readers.catalog.library_scan_task
            try:
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_info_paths_describe_storage_without_serializing_credentials(self):
        from types import SimpleNamespace
        from logisticsmobile.reader_controls import provider_comic_path
        reader = SimpleNamespace(key='Comics/Issue 1.cbz', source=SimpleNamespace(path='/private/ciphertext'))
        remote = SimpleNamespace(remote_storage=True, remote='Cloud', password='must-not-appear')
        self.assertEqual(provider_comic_path(remote, reader), 'Cloud:Comics/Issue 1.cbz')
        crypt = SimpleNamespace(provider=SimpleNamespace(private=True, remote='Secret'), password='must-not-appear')
        self.assertEqual(provider_comic_path(crypt, reader), 'LocalCrypt: Secret/Comics/Issue 1.cbz')
        local = SimpleNamespace(provider=SimpleNamespace(private=False))
        self.assertEqual(provider_comic_path(local, reader), '/private/ciphertext')

    def test_comic_file_buttons_stay_above_page_and_keep_controls_visible(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            _, source = make_books(fixtures)
            async def exercise():
                store = app.reader_manager().catalog.library_store
                records = []
                for name in ('01.cbz', '02.cbz', '03.cbz'):
                    path = fixtures / name
                    path.write_bytes(source.read_bytes())
                    records.append(store.import_book(LocalDocuments(), path))
                await app.open_book(records[1]['id'])
                owner = app.readers.active
                self.assertFalse(hasattr(owner.library_view, '_workspace_menu_button'))
                self.assertNotIn(owner.reader_header, owner.library_view.children)
                owner.set_reading_mode(False)
                self.assertLess(owner.library_view.children.index(owner.reader_header),
                                owner.library_view.children.index(owner.book_content))
                self.assertEqual(owner.comic_header.previous.control_icon, 'previous_comic')
                self.assertEqual(owner.comic_header.following.accessible_name, 'Next comic')
                self.assertTrue(owner.comic_header.previous.enabled)
                self.assertTrue(owner.comic_header.following.enabled)
                await owner.comic_header.following.on_press()
                last = app.readers.active
                self.assertEqual(last.book_record['id'], records[2]['id'])
                self.assertFalse(last.reader_immersive)
                self.assertFalse(last.comic_header.following.enabled)
                await last.comic_header.previous.on_press()
                await app.readers.active.comic_header.previous.on_press()
                first = app.readers.active
                self.assertEqual(first.book_record['id'], records[0]['id'])
                self.assertFalse(first.comic_header.previous.enabled)
                first.set_reading_mode(True)
                self.assertNotIn(first.reader_header, first.library_view.children)
                from types import SimpleNamespace
                rows = [dict(path=name, name=name, directory=False) for name in ('01.cbz', '02.cbz', '03.cbz')]
                provider = SimpleNamespace(root=root / 'provider', private=False, list=lambda folder='': rows)
                def open_copy(key, **kwargs):
                    reader = PrivateReader(key, source.read_bytes())
                    reader.key = key
                    return reader
                copies = SimpleNamespace(root=provider.root, provider=provider, open=open_copy, encrypted=False)
                app.show_cloud(present=False)
                self.assertTrue(await app.open_crypt(copies=copies, key='02.cbz'))
                private = app.private_sessions.active
                self.assertFalse(hasattr(private.crypt_view, '_workspace_menu_button'))
                private.toggle_private_reading_mode()
                self.assertTrue(private.comic_header.previous.enabled)
                self.assertTrue(private.comic_header.following.enabled)
                await private.comic_header.following.on_press()
                last_private = app.private_sessions.active
                self.assertEqual(last_private.crypt_reader.key, '03.cbz')
                self.assertFalse(last_private.crypt_immersive)
                self.assertFalse(last_private.comic_header.following.enabled)
                self.assertIn(last_private.comic_header.widget, last_private.reading_frame.controls)
                self.assertIn(last_private.page_footer.widget, last_private.reading_frame.controls)
                self.assertIs(last_private.page_footer.status, last_private.crypt_title)
                for key in list(app.private_sessions.controllers):
                    self.assertTrue(app.private_sessions.close(key, discard=True))
                await app.readers.catalog.metadata_task
                await app.readers.catalog.library_scan_task
            try:
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()
