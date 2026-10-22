"""Portrait wide-page navigation across imported and provider reader surfaces."""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image
from commonUtils.runtime.resources.documents import LocalDocuments
from mobile.app import LogisticsMobile
from services.documents.readers import PrivateReader


class ComicSplitTests(unittest.TestCase):
    def test_explicit_two_page_layout_wide_page_and_odd_tail_for_both_readers(self):
        for rtl in (False, True):
            with self.subTest(rtl=rtl), TemporaryDirectory() as directory:
                root = Path(directory)
                LogisticsMobile.storage_root = root
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                app.preferences.save(comic_layout='double', comic_split_wide='false')
                source = root / 'mixed.cbz'
                with ZipFile(source, 'w') as archive:
                    for index in range(6):
                        encoded = BytesIO()
                        Image.new('RGB', (300, 160) if index == 2 else ((240, 240) if index == 4 else (120, 240)), 'red').save(encoded, format='PNG')
                        archive.writestr(f'{index}.png', encoded.getvalue())
                    archive.writestr('ComicInfo.xml', '<ComicInfo><Manga>' +
                                     ('YesAndRightToLeft' if rtl else 'No') + '</Manga></ComicInfo>')
                record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), source)
                async def exercise():
                    with patch('features.comics.mobile.reader_controller.ComicController.comic_viewport', return_value=(400, 800)), \
                            patch('features.comics.mobile.provider_controller.ProviderComicController.private_comic_viewport', return_value=(400, 800)):
                        await app.open_book(record['id'])
                        imported = app.readers.active
                        for provider in (False, True):
                            if provider:
                                app.show_cloud()
                                reader = PrivateReader('mixed.cbz', source.read_bytes())
                                with patch.object(app.crypt_copies, 'open', return_value=reader):
                                    await app.open_crypt(copies=app.crypt_copies, key='e' * 32)
                                owner = app.private_sessions.active
                                nav, move = reader.comic_navigation, owner.move_provider_comic
                            else:
                                owner = imported
                                nav, move = owner.comic_navigation, owner.move_comic
                            self.assertEqual(nav.visible, (0, 1))
                            for direction, expected in ((1, (2,)), (1, (3, 4)), (1, (5,)),
                                                        (-1, (3, 4)), (-1, (2,)), (-1, (0, 1))):
                                await move(direction)
                                self.assertEqual(nav.visible, expected)
                                self.assertFalse(nav.split)
                            if provider:
                                app.private_sessions.close(owner.session.id, discard=True)
                try:
                    app.loop.run_until_complete(exercise())
                finally:
                    app.main_window.close()
                    app.loop.close()
                    LogisticsMobile.storage_root = None

    def test_halves_follow_direction_overlap_resume_and_keep_failed_view(self):
        for rtl in (False, True):
            with self.subTest(rtl=rtl), TemporaryDirectory() as directory:
                root = Path(directory)
                LogisticsMobile.storage_root = root
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                app.preferences.save(comic_split_wide='true')
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
                            def capture_outgoing(content, direction, preferences):
                                self.assertIs(pixels(owner, provider), first,
                                              'The new crop was published before the outgoing page was captured')
                            with patch('mobile.page_animation.begin_page_slide', side_effect=capture_outgoing) as capture:
                                if provider:
                                    owner.swipe_crypt_page(-1 if rtl else 1)
                                else:
                                    owner.swipe_book_page(-1 if rtl else 1)
                                await owner._comic_swipe_task
                                capture.assert_called_once()
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

    def test_duo_round_trip_keeps_right_page_in_imported_and_provider_readers(self):
        from dataclasses import replace
        for rtl in (False, True):
            with self.subTest(rtl=rtl), TemporaryDirectory() as directory:
                root = Path(directory)
                LogisticsMobile.storage_root = root
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                source = root / 'continuity.cbz'
                encoded = BytesIO()
                Image.new('RGB', (100, 200), 'red').save(encoded, format='PNG')
                with ZipFile(source, 'w') as archive:
                    for index in range(6):
                        archive.writestr(f'{index}.png', encoded.getvalue())
                    archive.writestr('ComicInfo.xml', '<ComicInfo><Manga>' +
                                     ('YesAndRightToLeft' if rtl else 'No') + '</Manga></ComicInfo>')
                record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), source)

                async def exercise():
                    await app.open_book(record['id'])
                    imported = app.readers.active
                    for provider in (False, True):
                        if provider:
                            app.show_cloud()
                            reader = PrivateReader('continuity.cbz', source.read_bytes())
                            with patch.object(app.crypt_copies, 'open', return_value=reader):
                                await app.open_crypt(copies=app.crypt_copies, key='d' * 32)
                            owner = app.private_sessions.active
                            nav, jump = reader.comic_navigation, owner.move_private_page
                        else:
                            owner = imported
                            nav, jump = owner.comic_navigation, owner.move_book_page
                        state = dict(seam=None, mode='single', region=None)
                        owner.format_services = replace(owner.format_services,
                            seam=lambda view: state['seam'], mode=lambda view: state['mode'],
                            seam_gap=lambda view: 24 if state['seam'] else 0,
                            page_region=lambda view: state['region'])
                        # Explicit outer selection, then only layout changes.
                        await jump(3)
                        self.assertEqual(nav.visible, (3,))
                        for seam in (.48, .5, None, .5, None):
                            state.update(seam=seam, mode='double' if seam else 'single')
                            nav.layout_reload = True
                            await jump(3)
                            nav.layout_reload = False
                            self.assertEqual(nav.page, 3)
                            if seam:
                                self.assertEqual(nav.visible, (3, 4) if rtl else (2, 3))
                                self.assertEqual(nav.visible[0] if rtl else nav.visible[-1], 3)
                                self.assertTrue(nav.right_anchored)
                            else:
                                self.assertEqual(nav.visible, (3,))
                            self.assertEqual(owner.crypt_reader if provider else owner.book_reader,
                                             reader if provider else imported.book_reader)
                        # A horizontal fold constrains the discrete page above
                        # the division, without changing the logical anchor.
                        state.update(seam=None, mode='single', region=(0, 0, 400, 160))
                        await jump(3)
                        page = owner.provider_spread if provider else owner.book_content.children[0]
                        self.assertEqual(page.style.height, 160)
                        self.assertEqual(nav.visible, (3,))
                        state['region'] = None
                        await jump(3)
                        page = owner.provider_spread if provider else owner.book_content.children[0]
                        self.assertEqual(page.style.flex, 1)
                        self.assertEqual(nav.page, 3)
                        if provider:
                            app.private_sessions.close(owner.session.id, discard=True)
                try:
                    app.loop.run_until_complete(exercise())
                finally:
                    app.main_window.close()
                    app.loop.close()
                    LogisticsMobile.storage_root = None

    def test_duo_wide_half_survives_relayout_and_fold_margin_is_blank(self):
        from features.comics.mobile.navigation import ComicNavigation
        from features.comics.mobile.composite import compose_spread
        from mobile_build.native_tests.tests.logisticsmobile.reader_parity_probe import image_bytes
        page = image_bytes(b'\xff\x00\x00\xff', 300, 200)
        nav = ComicNavigation(lambda i: (page, 'image'), 1)
        nav.requested_half = 1
        indices, _ = nav.load(0, viewport=(400, 800))
        nav.commit(indices)
        nav.layout_reload = True
        for viewport in ((1000, 700), (400, 800)):
            indices, _ = nav.load(0, viewport=viewport)
            nav.commit(indices)
        self.assertEqual(nav.half, 1)
        portrait = image_bytes(b'\xff\x00\x00\xff', 100, 200)
        image = compose_spread([portrait, portrait], viewport=(800, 600), seam=.5, seam_gap=30)
        pixels = image._impl.native.raw
        self.assertEqual(pixels.getpixel((800, 600))[3], 0)
        self.assertEqual(pixels.getpixel((760, 600)), (255, 0, 0, 255))
        self.assertEqual(pixels.getpixel((840, 600)), (255, 0, 0, 255))

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
        from mobile.preferences import Preferences
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
