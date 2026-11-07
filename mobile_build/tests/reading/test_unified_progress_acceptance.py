"""Exercise nested managed files through both mobile entry points and fresh hosts."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mobile.document_sources import reopen_file
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
from mobile_build.tests.support.app import mobile_app
from mobile_build.tests.support.pdf import PDF, native_pdf
from services.documents.history_controls import clear_saved_positions


class UnifiedProgressAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.shelf = self.root / 'LocalFiles/Shelf'
        self.shelf.mkdir(parents=True)
        self.epub, self.comic = make_books(self.shelf, chapter_text='<p>' + 'Marker 😀 ' * 180 + '</p>')
        self.zip = self.comic.with_suffix('.zip')
        self.zip.write_bytes(self.comic.read_bytes())
        self.pdf = self.shelf / 'Fixture.pdf'
        self.pdf.write_bytes(PDF)
        self.enterContext(patch('features.pdf.document.PDFDocument.open', native_pdf))

    async def open_at(self, app, path, entry):
        if entry == 'home':
            app.show_home()
            opened = await reopen_file(app, {'type': 'local', 'path': str(path)})
        else:
            await app.show_files(location=('Local files', 'Shelf'))
            row = next(row for row in app.file_rows.values() if row['name'] == path.name)
            self.assertEqual(row['path'], 'Shelf/' + path.name)
            app.browser_file_selected(row)
            opened = await app.read_managed_file()
        self.assertTrue(opened, path)
        owner = app.private_sessions.active
        async with asyncio.timeout(5):
            while owner.cloud_busy or getattr(owner, 'page_suspended', False):
                await asyncio.sleep(.01)
        return owner

    def assert_page(self, owner, index):
        self.assertEqual(owner._provider_displayed_index, index)
        if owner.crypt_reader.kind == '.epub':
            self.assertIn(('Native EPUB first', 'Native EPUB second')[index],
                          owner.provider_epub_view.text.value)
        elif owner.crypt_reader.kind == '.pdf':
            self.assertIn(owner.crypt_image, owner.crypt_content.children)
            self.assertIsNotNone(owner.crypt_image.image)
        else:
            self.assertEqual(owner.crypt_reader.comic_navigation.visible, (index,))
            self.assertIn(owner.provider_spread, owner.crypt_content.children)

    async def close(self, app, owner):
        app.request_reader_close(owner.session.id)
        async with asyncio.timeout(5):
            while owner.session.id in app.workspace.sessions:
                await asyncio.sleep(.01)

    def check_entry_points(self, path):
        for start, end, advance in (('home', 'local', True), ('local', 'home', False)):
            with mobile_app(root=self.root) as app:
                async def navigate():
                    app.preferences.values['comic_layout'] = 'single'
                    try:
                        owner = await self.open_at(app, path, start)
                        if advance:
                            await owner.move_private_page(1)
                        self.assert_page(owner, 1)
                        other = await self.open_at(app, path, end)
                        self.assertIs(other, owner)
                        self.assert_page(other, 1)
                    finally:
                        for opened in tuple(app.private_sessions.controllers.values()):
                            await self.close(app, opened)
                app.loop.run_until_complete(navigate())

    def test_epub_home_local_and_fresh_host_share_one_checkpoint(self):
        self.check_entry_points(self.epub)

    def test_cbz_home_local_and_fresh_host_share_one_checkpoint(self):
        self.check_entry_points(self.comic)

    def test_zip_home_local_and_fresh_host_share_one_checkpoint(self):
        self.check_entry_points(self.zip)

    def test_pdf_home_local_and_fresh_host_share_one_checkpoint(self):
        self.check_entry_points(self.pdf)

    def test_callback_from_a_replaced_epub_surface_cannot_regress_the_passage(self):
        with mobile_app(root=self.root) as app:
            async def navigate():
                owner = await self.open_at(app, self.epub, 'home')
                first = owner.provider_epub_view
                late_position = first.on_position
                await owner.move_private_page(1)
                await owner.move_private_page(0)
                current = owner.provider_epub_view
                self.assertIsNot(current, first)
                current.seek(142)
                late_position(5)
                self.assertEqual(current.offset, 142)
                await self.close(app, owner)
            app.loop.run_until_complete(navigate())

        with mobile_app(root=self.root) as app:
            async def restore():
                owner = await self.open_at(app, self.epub, 'local')
                self.assertEqual(owner.provider_epub_view.offset, 142)
                await self.close(app, owner)
            app.loop.run_until_complete(restore())

    def test_failed_page_decode_keeps_the_last_mounted_comic_page(self):
        with mobile_app(root=self.root) as app:
            async def navigate():
                app.preferences.values['comic_layout'] = 'single'
                owner = await self.open_at(app, self.comic, 'home')
                try:
                    await owner.move_private_page(1)
                    self.assert_page(owner, 1)
                    with patch.object(owner, 'provider_page_content', side_effect=ValueError('synthetic decode error')):
                        await owner.move_private_page(0)
                    self.assertIn('Cannot read page', owner.crypt_title.text.replace('\n', ' '))
                    self.assert_page(owner, 1)
                finally:
                    await self.close(app, owner)
            app.loop.run_until_complete(navigate())

        with mobile_app(root=self.root) as app:
            async def restore():
                app.preferences.values['comic_layout'] = 'single'
                owner = await self.open_at(app, self.comic, 'local')
                try:
                    self.assert_page(owner, 1)
                finally:
                    await self.close(app, owner)
            app.loop.run_until_complete(restore())

    def test_visible_epub_after_clear_cannot_resurrect_a_cleared_position(self):
        with mobile_app(root=self.root) as app:
            async def navigate():
                owner = await self.open_at(app, self.epub, 'home')
                await owner.move_private_page(1)
                self.assert_page(owner, 1)
                clear_saved_positions(self.root, mobile=True)
                # A legitimate visible callback on the already-open reader still
                # belongs to the old history generation.
                await owner.move_private_page(0)
                await owner.move_private_page(1)
                self.assert_page(owner, 1)
                await self.close(app, owner)
            app.loop.run_until_complete(navigate())
        with mobile_app(root=self.root) as app:
            async def restore():
                owner = await self.open_at(app, self.epub, 'local')
                self.assert_page(owner, 0)
                await self.close(app, owner)
            app.loop.run_until_complete(restore())
