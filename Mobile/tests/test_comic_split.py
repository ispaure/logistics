"""Portrait wide-page navigation across imported and provider reader surfaces."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image
from commonUtils.runtime.document_access import LocalDocuments
from logisticsmobile.app import LogisticsMobile
from services.documents.readers import PrivateReader


class ComicSplitTests(unittest.TestCase):
    def test_halves_follow_direction_overlap_resume_and_keep_failed_view(self):
        for rtl in (False, True):
            with self.subTest(rtl=rtl), TemporaryDirectory() as directory:
                root = Path(directory)
                LogisticsMobile.storage_root = root
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                source = root / 'wide.cbz'
                # Distinct outer halves and a shared centre stripe prove actual crops.
                image = Image.new('RGB', (1000, 600), 'red')
                image.paste('blue', (500, 0, 1000, 600))
                image.paste('green', (460, 0, 540, 600))
                encoded = BytesIO()
                image.save(encoded, format='PNG')
                with ZipFile(source, 'w') as archive:
                    for i in range(2):
                        archive.writestr(f'{i}.png', encoded.getvalue())
                    archive.writestr('ComicInfo.xml', '<ComicInfo><Manga>' +
                                     ('YesAndRightToLeft' if rtl else 'No') + '</Manga></ComicInfo>')
                record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), source)

                def pixels(owner, provider):
                    view = owner.provider_spread if provider else owner.book_content.children[0]
                    return view.canvas.image._impl.native.raw

                async def exercise():
                    with patch('features.comics.mobile.reader_controller.ComicController.comic_viewport', return_value=(400, 800)), \
                            patch('features.comics.mobile.provider_controller.ProviderComicController.private_comic_viewport', return_value=(400, 800)):
                        await app.open_book(record['id'])
                        imported = app.readers.active
                        self.assertEqual(app.preferences.values['comic_split_wide'], 'true')
                        for provider in (False, True):
                            if provider:
                                app.show_cloud()
                                reader = PrivateReader('wide.cbz', source.read_bytes())
                                with patch.object(app.crypt_copies, 'open', return_value=reader):
                                    await app.open_crypt(copies=app.crypt_copies, key='c' * 32)
                                owner = app.private_sessions.active
                                await owner.read_crypt_page()
                                nav = reader.comic_navigation
                                move = owner.move_provider_comic
                                jump = owner.move_private_page
                            else:
                                owner, nav = imported, imported.comic_navigation
                                move, jump = owner.move_comic, owner.move_book_page
                            self.assertEqual((nav.page, nav.half, nav.split), (0, 0, True))
                            self.assertFalse(owner.previous_page.enabled)
                            first = pixels(owner, provider)
                            self.assertEqual(first.size, (540, 600))
                            outer = (0, 0, 255, 255) if rtl else (255, 0, 0, 255)
                            self.assertEqual(first.getpixel((539 if rtl else 0, 0)), outer)
                            self.assertEqual(first.getpixel((0 if rtl else 539, 0)), (0, 128, 0, 255))
                            # Use the actual gesture scheduling path, including manga inversion.
                            if provider:
                                owner.swipe_crypt_page(-1 if rtl else 1)
                            else:
                                owner.swipe_book_page(-1 if rtl else 1)
                            await owner._comic_swipe_task
                            self.assertEqual((nav.page, nav.half), (0, 1))
                            self.assertTrue(owner.previous_page.enabled)
                            self.assertIsNot(pixels(owner, provider), first)
                            await move(1)
                            self.assertEqual((nav.page, nav.half), (1, 0))
                            self.assertTrue(owner.next_page.enabled)
                            with patch('features.comics.mobile.composite.compose_spread', side_effect=ValueError('decode')):
                                previous = pixels(owner, provider)
                                await move(1)
                            self.assertEqual((nav.page, nav.half), (1, 0))
                            self.assertIs(pixels(owner, provider), previous)
                            await move(1)
                            self.assertEqual((nav.page, nav.half), (1, 1))
                            self.assertFalse(owner.next_page.enabled)
                            await move(-1)
                            self.assertEqual((nav.page, nav.half), (1, 0))
                            await move(-1)
                            self.assertEqual((nav.page, nav.half), (0, 1))
                            await move(-1)
                            self.assertEqual((nav.page, nav.half), (0, 0))
                            await move(1)
                            if not provider:
                                saved, _ = owner.library_store.read_record(record['id'])
                                self.assertEqual((saved['position'], saved['comic_half']), (0, 1))
                            app.preferences.save(comic_split_wide='false')
                            await jump(0)
                            self.assertFalse(nav.split)
                            app.preferences.save(comic_split_wide='true')
                            await jump(0)
                            self.assertTrue(nav.split)
                            if provider:
                                app.private_sessions.close(owner.session.id, discard=True)
                        # Imported progress restores the half as well as the original page.
                        self.assertTrue(app.close_session(imported.session.id))
                        await app.open_book(record['id'])
                        owner = app.readers.active
                        self.assertEqual(owner.comic_navigation.page, 0)
                        await owner.move_comic(1)
                        self.assertEqual(owner.comic_navigation.half, 1)
                        key = owner.session.id
                        self.assertTrue(app.close_session(key))
                        await app.open_book(record['id'])
                        owner = app.readers.active
                        self.assertEqual(owner.comic_navigation.half, 1)
                        with patch('features.comics.mobile.reader_controller.ComicController.comic_viewport', return_value=(800, 400)):
                            await owner.move_book_page(0)
                            self.assertFalse(owner.comic_navigation.split)
                            self.assertEqual(owner.book_content.children[0].image.size, (1000, 600))
                try:
                    app.loop.run_until_complete(exercise())
                finally:
                    app.main_window.close()
                    app.loop.close()
                    LogisticsMobile.storage_root = None

    def test_split_eligibility_and_one_page_boundaries(self):
        from features.comics.mobile.navigation import ComicNavigation
        encoded = BytesIO()
        Image.new('RGB', (1000, 600), 'red').save(encoded, format='PNG')
        nav = ComicNavigation(lambda index: (encoded.getvalue(), 'image'), 1)
        for mode in ('single', 'auto', 'double'):
            nav.requested_half = 0
            indices, _ = nav.load(0, viewport=(400, 800), mode=mode)
            nav.commit(indices)
            self.assertEqual(nav.next(0), 0)
            self.assertFalse(nav.can_previous(0))
            nav.requested_half = 1
            indices, _ = nav.load(0, viewport=(400, 800), mode=mode)
            nav.commit(indices)
            self.assertIsNone(nav.next(0))
            self.assertEqual(nav.previous(0, viewport=(400, 800), mode=mode), 0)
        for viewport, enabled in (((800, 400), True), ((600, 600), True), ((400, 800), False)):
            indices, _ = nav.load(0, viewport=viewport, split_wide=enabled)
            nav.commit(indices)
            self.assertFalse(nav.split)
            self.assertIsNone(nav.crop)
            self.assertIsNone(nav.next(0))

    def test_preference_validation_and_missing_key_default(self):
        from logisticsmobile.preferences import Preferences
        from features.books.mobile.appearance import ReaderAppearance
        with TemporaryDirectory() as directory:
            (Path(directory) / 'preferences.ini').write_text('[Mobile]\ncomic_layout=single\n')
            prefs = Preferences(Path(directory))
            self.assertEqual(prefs.values['comic_layout'], 'single')
            self.assertEqual(prefs.values['comic_split_wide'], 'true')
            form = ReaderAppearance(prefs.values, lambda widget: None, kind='comic')
            form.split_wide.value = False
            prefs.save(**form.settings())
            self.assertEqual(Preferences(Path(directory)).values['comic_split_wide'], 'false')
            with self.assertRaises(ValueError):
                prefs.save(comic_split_wide='invalid')
