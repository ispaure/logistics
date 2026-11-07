"""Discard-and-reopen parity across the mobile document editor owners."""
import asyncio
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from commonUtils.testing.stages import TestStage
from mobile.documents import DocumentStore
from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.resources import LocalTextCopies
import test_document_navigation as navigation
import test_obsidian as notes

TEST_STAGE = TestStage.REGRESSION


class ManagedDiscardTests(unittest.IsolatedAsyncioTestCase):
    async def test_queued_and_published_recovery_cannot_restore_discarded_text(self):
        with TemporaryDirectory() as folder:
            store = DocumentStore(Path(folder))
            for extension in ('txt', 'md', 'json', 'html'):
                for published in (False, True):
                    with self.subTest(extension=extension, published=published):
                        doc = store.create('note.' + extension, b'Saved baseline')
                        doc.text = 'Discard this edit'
                        store.queue_checkpoint(doc, asyncio.get_running_loop())
                        if published:
                            store.flush_checkpoints()
                        store.discard(doc)
                        await asyncio.sleep(.3)
                        await asyncio.gather(*store._writes)
                        reopened = DocumentStore(Path(folder)).open(doc.id)
                        self.assertEqual(reopened.text, 'Saved baseline')
                        self.assertFalse(reopened.modified)
                        self.assertEqual(store.path(doc.id, '.data').read_bytes(), b'Saved baseline')


class FileDiscardTests(unittest.TestCase):
    setUp = navigation.DocumentNavigationTests.setUp

    def test_provider_text_discard_reopens_saved_bytes(self):
        async def exercise():
            for suffix in ('txt', 'md', 'json', 'html'):
                with self.subTest(suffix=suffix):
                    path = self.folder / ('discard.' + suffix)
                    original = b'Saved baseline\r\n'
                    path.write_bytes(original)
                    self.assertTrue(await self.app.open_crypt(copies=LocalTextCopies(LocalFiles(self.folder)), key=path.name))
                    owner = self.app.private_sessions.active
                    owner.crypt_text.value = 'Discard this edit'
                    self.assertTrue(owner.private_dirty())
                    with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='discard')):
                        self.app.request_close_session(owner.session.id)
                        await asyncio.gather(*self.app._document_close_tasks.values())
                    self.assertNotIn(owner.session.id, self.app.workspace.sessions)
                    self.assertEqual(path.read_bytes(), original)
                    self.assertTrue(await self.app.open_crypt(copies=LocalTextCopies(LocalFiles(self.folder)), key=path.name))
                    reopened = self.app.private_sessions.active
                    self.assertEqual(reopened.crypt_text.value, reopened.crypt_reader.text)
                    self.assertNotIn('Discard this edit', reopened.crypt_text.value)
                    self.assertFalse(reopened.private_dirty())
                    self.assertTrue(self.app.close_session(reopened.session.id))
        self.app.loop.run_until_complete(exercise())

    def test_imported_text_discard_reopens_clean_copy_after_checkpoints_settle(self):
        async def exercise():
            for suffix in ('txt', 'md'):
                with self.subTest(suffix=suffix):
                    path = self.folder / ('import-discard.' + suffix)
                    original = b'Saved imported baseline'
                    path.write_bytes(original)
                    from mobile_build.tests.support.readers import open_legacy_import
                    self.assertTrue(await open_legacy_import(self.app, path))
                    owner = self.app.editor_view
                    owner.editor.value = 'Discard imported edit'
                    self.assertTrue(owner.document.modified)
                    with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='discard')):
                        self.app.request_close_session(owner.session.id)
                        await asyncio.gather(*self.app._document_close_tasks.values())
                    await asyncio.sleep(.3)
                    await asyncio.gather(*self.app.store._writes)
                    from mobile_build.tests.support.readers import open_legacy_import
                    self.assertTrue(await open_legacy_import(self.app, path))
                    self.assertEqual(self.app.editor_view.document.text, 'Saved imported baseline')
                    self.assertFalse(self.app.editor_view.document.modified)
                    self.assertEqual(path.read_bytes(), original)
                    self.assertTrue(self.app.close_session(self.app.editor_view.session.id))
        self.app.loop.run_until_complete(exercise())

    def test_imported_book_metadata_discard_reopens_saved_values(self):
        async def exercise():
            for path in self.paths[:2]:
                with self.subTest(suffix=path.suffix):
                    original = path.read_bytes()
                    from mobile_build.tests.support.readers import open_legacy_import
                    self.assertTrue(await open_legacy_import(self.app, path))
                    owner = self.app.readers.active
                    owner.show_book_metadata()
                    initial = dict(owner.book_metadata_initial)
                    self.assertTrue(initial)
                    owner.book_metadata_fields[next(iter(initial))].value = 'Discard imported metadata'
                    with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='discard')):
                        self.app.request_close_session(owner.session.id)
                        await asyncio.gather(*self.app._document_close_tasks.values())
                    self.assertNotIn(owner.session.id, self.app.workspace.sessions)
                    from mobile_build.tests.support.readers import open_legacy_import
                    self.assertTrue(await open_legacy_import(self.app, path))
                    reopened = self.app.readers.active
                    reopened.show_book_metadata()
                    self.assertEqual(reopened.book_metadata_initial, initial)
                    self.assertEqual(path.read_bytes(), original)
                    self.assertTrue(self.app.close_session(reopened.session.id))
        self.app.loop.run_until_complete(exercise())

    def test_epub_and_comic_metadata_discard_reopens_saved_values(self):
        async def exercise():
            for path in self.paths[:2]:
                with self.subTest(suffix=path.suffix):
                    original = path.read_bytes()
                    self.assertTrue(await self.app.open_crypt(copies=LocalTextCopies(LocalFiles(self.folder)), key=path.name))
                    owner = self.app.private_sessions.active
                    owner.edit_crypt_metadata()
                    initial = dict(owner.crypt_metadata_initial)
                    self.assertTrue(initial)
                    field = next(iter(initial))
                    owner.crypt_metadata_fields[field].value = 'Discard metadata edit'
                    self.assertTrue(owner.private_dirty())
                    with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='discard')):
                        self.app.request_close_session(owner.session.id)
                        await asyncio.gather(*self.app._document_close_tasks.values())
                    self.assertEqual(path.read_bytes(), original)
                    self.assertTrue(await self.app.open_crypt(copies=LocalTextCopies(LocalFiles(self.folder)), key=path.name))
                    reopened = self.app.private_sessions.active
                    reopened.edit_crypt_metadata()
                    self.assertEqual(reopened.crypt_metadata_initial, initial)
                    self.assertFalse(reopened.private_dirty())
                    self.assertTrue(self.app.close_session(reopened.session.id))
        self.app.loop.run_until_complete(exercise())


class LibraryDiscardTests(unittest.TestCase):
    setUp = notes.ObsidianTests.setUp
    tearDown = notes.ObsidianTests.tearDown
    run_async = notes.ObsidianTests.run_async

    def test_notes_library_discard_reopens_saved_text_and_code(self):
        from mobile.obsidian import open_vault
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            for suffix in ('txt', 'md', 'json', 'js', 'html'):
                with self.subTest(suffix=suffix):
                    path = self.vault / ('discard.' + suffix)
                    original = b'Saved baseline\r\n'
                    path.write_bytes(original)
                    relative = 'Vault/' + path.name
                    self.assertTrue(await owner.open_note(relative))
                    if owner.embedded is None:
                        self.assertTrue(await owner.open_editor())
                    editor = owner.embedded
                    editor.source_input().value = 'Discard this edit'
                    editor.changed('Discard this edit')
                    self.assertTrue(editor.dirty)
                    with patch.object(owner, 'host', replace(owner.host, confirm=AsyncMock(return_value='discard'))):
                        self.assertTrue(await owner.open_note('Vault/Home.md'))
                    self.assertTrue(editor.closed)
                    self.assertEqual(path.read_bytes(), original)
                    self.assertTrue(await owner.open_note(relative))
                    if owner.embedded is None:
                        self.assertTrue(await owner.open_editor())
                    self.assertNotIn('Discard this edit', owner.embedded.text)
                    self.assertFalse(owner.embedded.dirty)
            owner.dispose()
        self.run_async(exercise())
