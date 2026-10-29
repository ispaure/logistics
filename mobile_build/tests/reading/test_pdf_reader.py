"""Mobile session integration using Toga's official dummy backend."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import base64
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mobile.app import LogisticsMobile
from features.rclone.mobile.remote_readers import RemoteReaders
from mobile_build.tests.support.readers import RemoteClient
from mobile_build.tests.support.localcrypt import seed_offline_copy
from mobile_build.tests.support.pdf import PDF, native_pdf


@contextmanager
def search_panel():
    from features.pdf.mobile.search import PDFSearchBar
    with TemporaryDirectory() as directory:
        previous_root = LogisticsMobile.storage_root
        LogisticsMobile.storage_root = Path(directory)
        app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        pages, active = [], [True]
        async def navigate(page):
            pages.append(page)
        search = PDFSearchBar(SimpleNamespace(data=PDF), on_page=navigate, alive=lambda: active[0])
        try:
            yield app, search, pages, active
        finally:
            search.dispose()
            app.main_window.close()
            app.loop.close()
            LogisticsMobile.storage_root = previous_root


class PDFMobileTests(unittest.TestCase):
    def test_numeric_jump_waits_for_refresh_and_rejects_a_retired_navigation(self):
        with TemporaryDirectory() as directory, patch('features.pdf.document.PDFDocument.open', native_pdf):
            previous_root = LogisticsMobile.storage_root
            LogisticsMobile.storage_root = Path(directory)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            path = Path(directory) / 'jump.pdf'
            path.write_bytes(PDF)
            async def check():
                self.assertTrue(await app.open_download(path=path))
                owner = app.private_sessions.active
                owner.pdf_number.value = '3'
                await owner.read_crypt_page()
                self.assertEqual(owner.pdf_number.value, '3')
                for leave in (False, True):
                    owner.resume_crypt()
                    owner.set_cloud_busy(True)
                    owner.pdf_number.value = '3'
                    pending = owner.pdf_number.on_confirm()
                    try:
                        await asyncio.sleep(0)
                        self.assertFalse(pending.done())
                        # A refresh may synchronize the input with its old page.
                        # The submitted target must already have been captured.
                        owner.pdf_number.value = '1'
                        if leave:
                            app.show_settings()
                        owner.set_cloud_busy(False)
                        await pending
                        self.assertEqual(owner.crypt_page.value, 'Page 1' if leave else 'Page 3')
                        if leave:
                            self.assertEqual(app.native_host.state.destination, 'settings')
                            self.assertEqual(owner.pdf_jump_status.text, 'Page jump cancelled.')
                        else:
                            await owner.move_private_page(0)
                    finally:
                        owner.set_cloud_busy(False)
                        await pending
            try:
                app.loop.run_until_complete(check())
            finally:
                app.main_window.close()
                app.loop.close()
                LogisticsMobile.storage_root = previous_root

    def test_spreads_follow_page_dimensions_and_last_page_without_skipping(self):
        from features.pdf.mobile.canvas import PDFNavigation
        from io import BytesIO
        from PIL import Image
        def page(width, height):
            output = BytesIO()
            Image.new('RGB', (width, height), 'white').save(output, format='PNG')
            return output.getvalue()
        pages = [page(300, 600)] * 5
        document = SimpleNamespace(count=5, page=lambda index: pages[index])
        navigation = PDFNavigation(document)
        self.assertEqual(navigation.load(0, (600, 1000))[0], (0,))
        indices, data = navigation.load(0, (1200, 800))
        self.assertEqual(indices, (0, 1))
        navigation.indices, navigation.viewport = indices, (1200, 800)
        self.assertEqual(navigation.next(), 2)
        navigation.indices = (2, 3)
        self.assertEqual(navigation.previous(), 0)
        navigation.indices = (4,)
        self.assertIsNone(navigation.next())
        self.assertEqual(navigation.previous(), 2)
        self.assertEqual(navigation.load(4, (1200, 800))[0], (4,))
        pages[1] = page(1200, 600)
        self.assertEqual(navigation.load(0, (1200, 800))[0], (0,))

    def test_search_worker_start_failure_is_retryable(self):
        with search_panel() as (app, search, pages, active):
            async def check():
                search.input.value = 'needle'
                with patch('features.pdf.mobile.search.asyncio.to_thread', side_effect=RuntimeError()):
                    await search.next_match()
                self.assertIn('RuntimeError', search.status.text)
                self.assertTrue(search.following.enabled)
                await search.next_match()
                self.assertEqual(pages, [0])
                self.assertIn('Match 1 of 3', search.status.text)
            app.loop.run_until_complete(check())

    def test_search_awaits_navigation_and_rejects_obsolete_page_errors(self):
        with search_panel() as (app, search, pages, active):
            async def check():
                started, release = asyncio.Event(), asyncio.Event()
                async def navigate(page):
                    pages.append(page)
                    started.set()
                    await release.wait()
                    raise ValueError('obsolete page error')
                search.on_page = navigate
                search.input.value = 'needle'
                pending = asyncio.create_task(search.next_match())
                try:
                    await asyncio.wait_for(started.wait(), 5)
                    self.assertFalse(search.following.enabled)
                    await search.next_match()
                    self.assertEqual(pages, [0])
                    search.input.value = 'new query'
                finally:
                    release.set()
                    await pending
                self.assertEqual(search.status.text, '')
                self.assertTrue(search.following.enabled)
            app.loop.run_until_complete(check())

    def test_search_rejects_late_completion_after_edit_inactivity_or_dispose(self):
        from features.pdf.search import search_pdf
        for change in ('edit', 'error', 'inactive', 'dispose', 'cancel'):
            with self.subTest(change=change), search_panel() as (app, search, pages, active):
                started, release = Event(), Event()
                def slow_search(data, query, **kwargs):
                    started.set()
                    if not release.wait(5):
                        raise TimeoutError('Search fixture was not released')
                    if change == 'error':
                        raise RuntimeError('obsolete failure')
                    # Intentionally ignore cancellation to exercise result rejection.
                    return search_pdf(data, query)
                async def check():
                    search.input.value = 'needle'
                    with patch('features.pdf.mobile.search.search_pdf', slow_search):
                        pending = asyncio.create_task(search.next_match())
                        try:
                            self.assertTrue(await asyncio.to_thread(started.wait, 5))
                            self.assertFalse(search.following.enabled)
                            if change in ('edit', 'error'):
                                search.input.value = 'missing'
                            elif change == 'inactive':
                                active[0] = False
                            elif change == 'dispose':
                                search.dispose()
                            else:
                                pending.cancel()
                                await asyncio.sleep(0)
                                self.assertTrue(search.controller.state.busy)
                        finally:
                            release.set()
                        if change == 'cancel':
                            with self.assertRaises(asyncio.CancelledError):
                                await pending
                        else:
                            await pending
                    self.assertEqual(pages, [])
                    self.assertFalse(search.controller.results.matches)
                    self.assertEqual(search.status.text, '')
                    self.assertFalse(search.controller.state.busy)
                    if change == 'dispose':
                        self.assertFalse(search.following.enabled)
                        self.assertEqual(search.input.value, '')
                    else:
                        active[0] = True
                        await search.next_match()
                        self.assertTrue(search.following.enabled)
                        self.assertIn('No matches' if change in ('edit', 'error') else 'Match 1 of 3',
                                      search.status.text)
                app.loop.run_until_complete(check())

    def test_cold_local_pdf_open_initializes_provider_controls(self):
        with TemporaryDirectory() as directory, patch('features.pdf.document.PDFDocument.open', native_pdf):
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            local = root / 'cold.pdf'
            local.write_bytes(PDF)
            self.assertFalse(hasattr(app, 'cloud_view'))
            async def check():
                self.assertTrue(await app.open_download(path=local), app.cloud_status.value)
                owner = app.private_sessions.active
                self.assertEqual(owner.crypt_reader.pdf.count, 3)
                self.assertIsNotNone(owner._provider_layout_task)
                self.assertFalse(owner._provider_layout_task.done())
                self.assertIsNotNone(owner.crypt_image.image)
                with patch('mobile.page_animation.begin_page_slide') as begin:
                    await owner.move_private_page(1)
                    self.assertEqual(begin.call_args.args[1], 1)
                    await owner.move_private_page(0)
                    self.assertEqual(begin.call_args.args[1], -1)
                self.assertTrue(owner.clear_private_reader())
            app.loop.run_until_complete(check())

    def test_local_remote_and_localcrypt_sessions(self):
        class Client(RemoteClient):
            def request(self, action, **values):
                if action == 'crypt_describe':
                    return 'secret.pdf'
                if action == 'crypt_decode':
                    return dict(name='secret.pdf', data=base64.b64encode(PDF).decode())
                return super().request(action, **values)
            def crypt_remotes(self):
                return []
        with TemporaryDirectory() as directory, patch('features.pdf.document.PDFDocument.open', native_pdf):
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            client = app.cloud_client = Client()
            client.supports_streaming = False
            client.files['remote.pdf'] = PDF
            app.show_cloud(present=False)
            local = root / 'local.pdf'
            local.write_bytes(PDF)
            crypt_key = seed_offline_copy(app.crypt_copies)

            async def check():
                async def verify():
                    owner = app.private_sessions.active
                    reader = owner.crypt_reader
                    self.assertEqual(owner.session.kind, 'pdf')
                    self.assertFalse(reader.editable)
                    self.assertIsNotNone(owner.crypt_image.image)
                    # PDFs now open fullscreen. Expose controls before testing
                    # page tools, then exercise both modes as before.
                    self.assertTrue(owner.reading_frame.immersive)
                    owner.toggle_private_reading_mode()
                    self.assertNotIn(owner.pdf_tools.panel, owner.pdf_tools.widget.children)
                    owner.pdf_tools.toggle()
                    self.assertIn(owner.pdf_tools.panel, owner.pdf_tools.widget.children)
                    canvas = owner.crypt_image
                    self.assertEqual(canvas.page_axis, 'vertical')
                    self.assertFalse(canvas.magnifier_enabled)
                    canvas.toggle_controls()
                    self.assertTrue(owner.reading_frame.immersive)
                    self.assertTrue(owner.crypt_view._reader_fullscreen)
                    self.assertTrue(canvas.magnifier_enabled)
                    self.assertNotIn(owner.reader_restore, owner.reading_frame.widget.children)
                    self.assertEqual(owner.crypt_view.style.margin_top, 0)
                    canvas.page(1)
                    await owner._comic_swipe_task
                    self.assertEqual(owner.crypt_page.value, 'Page 2')
                    self.assertTrue(canvas.magnifier_enabled)
                    canvas.page(-1)
                    await owner._comic_swipe_task
                    self.assertEqual(owner.crypt_page.value, 'Page 1')
                    canvas.toggle_controls()
                    self.assertFalse(owner.reading_frame.immersive)
                    self.assertFalse(canvas.magnifier_enabled)
                    canvas.page(1)
                    await owner._comic_swipe_task
                    self.assertEqual(owner.crypt_page.value, 'Page 2')
                    canvas.page(-1)
                    await owner._comic_swipe_task
                    self.assertEqual(owner.crypt_page.value, 'Page 1')
                    owner.pdf_number.value = '3'
                    await owner.pdf_number.on_confirm()
                    self.assertEqual(owner.crypt_page.value, 'Page 3')
                    owner.pdf_number.value = '0'
                    await owner.pdf_number.on_confirm()
                    self.assertEqual(owner.crypt_page.value, 'Page 3')
                    owner.crypt_image.page(-1)
                    await owner._comic_swipe_task
                    self.assertEqual(owner.crypt_page.value, 'Page 2')
                    self.assertEqual(owner.pdf_number.value, '2')
                    await owner.previous_private_page()
                    self.assertEqual(owner.crypt_page.value, 'Page 1')
                    await owner.previous_private_page()
                    self.assertEqual(owner.crypt_page.value, 'Page 1')
                    search = owner.pdf_search
                    search.input.value = 'needle'
                    await search.next_match()
                    self.assertIn('Match 1 of 3', search.status.text)
                    await search.previous_match()
                    self.assertEqual(owner.crypt_page.value, 'Page 3')
                    await search.next_match()
                    self.assertEqual(owner.crypt_page.value, 'Page 1')
                    search.input.value = 'absent'
                    await search.next_match()
                    self.assertIn('No matches', search.status.text)
                    # Closing while extraction is in flight must reject its
                    # eventual result and clear private query/snippet state.
                    import asyncio
                    from threading import Event
                    from features.pdf.search import search_pdf
                    started, release = Event(), Event()
                    def slow_search(data, query, **kwargs):
                        started.set()
                        if not release.wait(5):
                            raise TimeoutError('Search fixture was not released')
                        return search_pdf(data, query, **kwargs)
                    search.input.value = 'needle'
                    with patch('features.pdf.mobile.search.search_pdf', slow_search):
                        pending = asyncio.create_task(search.next_match())
                        try:
                            async def wait_started():
                                while not started.is_set():
                                    await asyncio.sleep(.001)
                            await asyncio.wait_for(wait_started(), timeout=5)
                            owner.close_crypt()
                        finally:
                            release.set()
                        await pending
                    self.assertTrue(search.controller.disposed)
                    self.assertFalse(search.controller.results.matches)
                    self.assertEqual(search.input.value, '')
                    self.assertEqual(search.status.text, '')
                    self.assertEqual(reader.pdf.data, b'')
                    self.assertEqual(reader.data, b'')
                    self.assertIsNone(owner.crypt_image.image)
                    self.assertIsNone(owner.crypt_image.on_page)
                    self.assertIsNone(owner.crypt_image.on_toggle)
                    self.assertFalse(owner.crypt_image.magnifier_enabled)
                self.assertTrue(await app.open_download(path=local), app.cloud_status.value)
                await verify()
                self.assertTrue(await app.open_crypt(copies=RemoteReaders(client, 'Files'), key='remote.pdf'), app.cloud_status.value)
                await verify()
                self.assertTrue(await app.open_crypt(copies=app.crypt_copies, key=crypt_key), app.cloud_status.value)
                owner = app.private_sessions.active
                reader = owner.crypt_reader
                client.generation += 1
                app.screen_privacy.retire_stale()
                self.assertIsNone(owner.crypt_reader)
                self.assertTrue(owner.pdf_search.controller.disposed)
                self.assertEqual(owner.pdf_search.input.value, '')
                self.assertEqual(reader.pdf.data, b'')
                self.assertTrue(reader.source.closed)
                self.assertEqual(reader.source.backend.data, b'')
                self.assertIsNone(owner.crypt_image.image)
                self.assertFalse(app.private_sessions.controllers)
                for path in root.rglob('*'):
                    if path.is_file() and path != local:
                        self.assertNotIn(b'mobile-private-pdf-sentinel', path.read_bytes())
            app.loop.run_until_complete(check())


if __name__ == '__main__':
    unittest.main()
