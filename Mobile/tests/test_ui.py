"""Widget contracts using Toga's official dummy backend, not device evidence."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from logisticsmobile.access import LocalDocuments
from logisticsmobile.app import LogisticsMobile
from Mobile.native_tests.tests.logisticsmobile.fixtures import make_books
from logisticsmobile.chat_fixture import fixture_server


class MobileUITests(unittest.TestCase):
    def test_create_edit_recover_switch_import_save_and_conflict_copy(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            self.assertEqual(app.native_host.state.destination, 'home')
            self.assertEqual(app.body.children[0].content.children[0].text, 'Logistics')
            app.show_settings()
            app.font_choice.value = '20'
            app.restore_choice.value = False
            app.save_preferences()
            self.assertEqual(app.preferences.values['font_size'], '20')
            self.assertEqual(app.preferences.values['restore_last_document'], 'false')
            app.show_documents()
            first = app.current.id
            self.assertEqual(app.native_host.state.destination, 'documents')
            app.name.value = 'Notes.md'
            app.editor.value = '# Recovered\n'
            app.native_host.root.current_tab = 'Settings'
            app.native_host._selected(app.native_host.root)
            self.assertIs(app.body, app.routes.body('settings'))
            app.native_host.root.current_tab = 'Documents'
            app.native_host._selected(app.native_host.root)
            self.assertIs(app.body.children[0], app.document_view)
            self.assertEqual(app.editor.value, '# Recovered\n')
            recovered = app.store.open(first)
            self.assertEqual(recovered.name, 'Notes.md')
            self.assertTrue(recovered.modified)
            app.new_document()
            app.selector.value = 'Notes.md'
            self.assertEqual(app.current.id, first)
            self.assertEqual(app.editor.value, '# Recovered\n')
            app.save_document()
            self.assertFalse(app.store.open(first).modified)
            source = root / 'external.txt'
            source.write_bytes(b'external\r\n')
            with patch('logisticsmobile.pickers.pick_document', new=AsyncMock(return_value=(LocalDocuments(), source))):
                app.loop.run_until_complete(app.import_document())
            self.assertTrue(app.import_button.enabled)
            self.assertEqual(app.editor.value, 'external\n')
            app.editor.value = 'edited\n'
            app.save_document()
            self.assertEqual(source.read_bytes(), b'external\r\n')
            conflicted = app.current.id
            app.current.snapshot.path.write_bytes(b'changed outside the app')
            app.editor.value = 'keep these edits'
            app.save_document()
            self.assertIn('changed', app.status.text)
            app.save_copy()
            self.assertNotEqual(app.current.id, conflicted)
            self.assertEqual(app.current.text, 'keep these edits')
            app.show_preview()
            preview = app.preview
            self.assertIs(app.body.children[0].children[-1], app.preview)
            app.show_documents()
            app.show_preview()
            self.assertIs(app.preview, preview)
            app.show_documents()
            with patch('logisticsmobile.pickers.export_document', new=AsyncMock(return_value=True)) as export:
                app.loop.run_until_complete(app.export_document())
                self.assertEqual(export.await_args.args[2], b'keep these edits')
            self.assertTrue(app.export_button.enabled)
            self.assertIn('exported', app.status.text)
            app.show_library()
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            epub, comic = make_books(fixtures)
            record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)
            app.refresh_library()
            app.loop.run_until_complete(app.open_book(record['id']))
            self.assertIsNotNone(app.reader_manager().active.book_reader, app.reader_manager().active.book_status.text)
            self.assertFalse(app.reader_manager().active.previous_page.enabled)
            self.assertTrue(app.reader_manager().active.next_page.enabled)
            reader_view = app.reader_manager().active.book_content.children[0]
            app.loop.run_until_complete(app.next_book_page())
            self.assertIs(app.reader_manager().active.book_content.children[0], reader_view)
            self.assertEqual(app.reader_manager().active.book_record['position'], 1)
            self.assertFalse(app.reader_manager().active.next_page.enabled)
            app.loop.run_until_complete(app.toggle_bookmark())
            self.assertEqual(app.reader_manager().active.book_record['bookmarks'], [1])
            record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), comic)
            app.refresh_library()
            app.loop.run_until_complete(app.open_book(record['id']))
            self.assertEqual(app.reader_manager().active.book_reader.pages, ['page2.png', 'page10.png'])
            self.assertIsNotNone(app.reader_manager().active.book_content.children[0].image)
            with fixture_server() as (url, started, release, requests):
                app.show_chat()
                app.chat_url.value = url
                app.chat_key.value = 'synthetic-ui-key'
                app.loop.run_until_complete(app.refresh_chat_models())
                self.assertEqual(app.chat_model.value, 'fixture-model')
                app.chat_prompt.value = 'Hello fixture'
                app.loop.run_until_complete(app.send_chat())
                self.assertEqual(app.chat_current['messages'][-1]['status'], 'complete', app.chat_status.value)
                self.assertEqual(app.chat_current['messages'][-1]['content'], 'Native fixture reply')
                self.assertNotIn('synthetic-ui-key', app.chat_store.path(app.chat_current['id']).read_text())
                app.show_chat_configuration()
                app.show_chat()
            class FixtureCloud:
                forgotten = False
                def import_package(self, access, reference, password, *, remember=True):
                    with access.open(reference) as (_, stream):
                        assert stream.read(1024) == b'synthetic package'
                    assert password == 'synthetic-ui-password'
                    return ['Fixture']
                def entries(self, remote, path=''):
                    assert remote == 'Fixture'
                    return [dict(path='fixture.txt', size=22, directory=False)]
                def download_into(self, remote, path, descriptor):
                    import os
                    os.write(descriptor, b'Private cloud fixture\n')
                def clear(self):
                    self.forgotten = True
                def cancel(self):
                    pass
            credentials = fixtures / 'credentials.zip'
            credentials.write_bytes(b'synthetic package')
            app.cloud_client = FixtureCloud()
            app.show_cloud()
            with patch('logisticsmobile.pickers.pick_document', new=AsyncMock(return_value=(LocalDocuments(), credentials))):
                app.loop.run_until_complete(app.choose_cloud_package())
                self.assertTrue(app.cloud_import.enabled)
                app.cloud_password.value = 'synthetic-ui-password'
                app.loop.run_until_complete(app.import_cloud_package())
            self.assertEqual(app.cloud_password.value, '')
            app.loop.run_until_complete(app.browse_cloud())
            app.cloud_entries.value = next(iter(app.cloud_rows))
            app.loop.run_until_complete(app.download_cloud())
            self.assertEqual(len(app.downloads.items()), 1)
            app.loop.run_until_complete(app.open_download())
            self.assertEqual(app.editor.value, 'Private cloud fixture\n')
            app.show_cloud()
            app.loop.run_until_complete(app.clear_cloud())
            self.assertTrue(app.cloud_client.forgotten)
            self.assertEqual(len(app.downloads.items()), 1)
            app.main_window.close()
            app.loop.close()


if __name__ == '__main__':
    unittest.main()
