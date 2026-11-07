"""Sharing overrides presentation without changing standalone preferences."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PIL import Image
from commonUtils.runtime.resources.documents import LocalDocuments
from mobile.app import LogisticsMobile
from mobile.layout_events import notify_layout
from mobile.preferences import Preferences
from services.documents.readers import PrivateReader


class ComicSharingTests(unittest.TestCase):
    def test_navigation_waits_for_automatic_layout_reload(self):
        self.navigation_during_reload(retire=False)

    def test_navigation_waiting_for_layout_does_not_touch_a_replaced_reader(self):
        self.navigation_during_reload(retire=True)

    def navigation_during_reload(self, *, retire):
        from mobile_build.tests.support.app import create_app
        from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
        app = create_app(self)
        app.preferences.save(comic_layout='single')
        with TemporaryDirectory() as directory:
            _, comic = make_books(Path(directory))
            record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), comic)
            async def exercise():
                await app.open_book(record['id'])
                owner = app.reader_manager().active
                owner.comic_navigation.layout_reload = True
                owner.set_book_busy(True)
                pending = asyncio.create_task(owner.move_comic(1))
                await asyncio.sleep(0)
                self.assertFalse(pending.done(), 'Page action was dropped during automatic reload')
                if not retire:
                    # A second geometry update can start another fit before
                    # the waiting navigation resumes from the first one.
                    owner.set_book_busy(False)
                    owner.set_book_busy(True)
                    await asyncio.sleep(0)
                    self.assertFalse(pending.done(), 'Page action was dropped between consecutive reloads')
                if retire:
                    owner.book_epoch += 1
                owner.comic_navigation.layout_reload = False
                owner.set_book_busy(False)
                await pending
                self.assertEqual(owner.book_record['position'], 0 if retire else 1)
            app.loop.run_until_complete(exercise())

    def test_defaults_and_saved_choices_restore_after_sharing_for_both_readers(self):
        for choices in ({}, {'comic_layout': 'single', 'comic_split_wide': 'false'}):
            with self.subTest(choices=choices), TemporaryDirectory() as directory:
                root = Path(directory)
                LogisticsMobile.storage_root = root
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                if choices:
                    app.preferences.save(**choices)
                expected = dict(comic_layout=choices.get('comic_layout', 'auto'),
                                comic_split_wide=choices.get('comic_split_wide', 'true'))
                source = root / 'mixed.cbz'
                with ZipFile(source, 'w') as archive:
                    for index in range(4):
                        image = BytesIO()
                        Image.new('RGB', (300, 160) if index == 2 else (120, 240), 'red').save(image, format='PNG')
                        archive.writestr(f'{index}.png', image.getvalue())
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
                                nav, jump, move = reader.comic_navigation, owner.move_private_page, owner.move_provider_comic
                            else:
                                owner = imported
                                nav, jump, move = owner.comic_navigation, owner.move_book_page, owner.move_comic
                            state = {'sharing': False}
                            owner.format_services = replace(owner.format_services, comic_sharing=lambda state=state: state['sharing'])
                            await jump(0)
                            self.assertEqual(nav.visible, (0,))
                            original = app.preferences.path.read_bytes() if app.preferences.path.exists() else None

                            async def sharing(enabled):
                                with patch.object(nav, 'load', wraps=nav.load) as load:
                                    state['sharing'] = enabled
                                    notify_layout(app)
                                    for _ in range(300):
                                        busy = owner.cloud_busy if provider else owner.book_busy
                                        if load.call_count and not busy:
                                            break
                                        await asyncio.sleep(.01)
                                    else:
                                        self.fail('Display change did not relayout the current comic')
                                self.assertEqual(app.preferences.values['comic_layout'], expected['comic_layout'])
                                self.assertEqual(app.preferences.values['comic_split_wide'], expected['comic_split_wide'])
                                current = app.preferences.path.read_bytes() if app.preferences.path.exists() else None
                                self.assertEqual(current, original, 'Sharing wrote a presentation override to preferences')

                            await sharing(True)
                            self.assertEqual(nav.visible, (0, 1))
                            await sharing(False)
                            self.assertEqual(nav.visible, (0,))
                            await jump(2)
                            split = expected['comic_split_wide'] == 'true'
                            self.assertEqual(nav.split, split)
                            if split:
                                await move(1)
                                self.assertEqual(nav.half, 1)
                            await sharing(True)
                            self.assertEqual(nav.visible, (2,))
                            self.assertFalse(nav.split)
                            await sharing(False)
                            self.assertEqual(nav.split, split)
                            self.assertEqual(nav.half, 1 if split else 0)
                            restored = Preferences(app.preferences.path.parent)
                            for key, value in expected.items():
                                self.assertEqual(restored.values[key], value)
                            if provider:
                                app.private_sessions.close(owner.session.id, discard=True)
                try:
                    app.loop.run_until_complete(exercise())
                finally:
                    app.main_window.close()
                    close_loop(app.loop)
                    LogisticsMobile.storage_root = None
