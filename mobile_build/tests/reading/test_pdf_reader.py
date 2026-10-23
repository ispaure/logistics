"""Mobile session integration using Toga's official dummy backend."""
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
from mobile_build.tests.reading.test_remote_readers import RemoteClient
from mobile_build.tests.transfers.test_localcrypt_ui import seed_offline_copy

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
def search_fixture():
    from io import BytesIO
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    output = BytesIO()
    with PdfWriter() as writer:
        for text in ('needle first needle', 'middle page', 'last NEEDLE'):
            page = writer.add_blank_page(width=300, height=600)
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
                DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
            content = DecodedStreamObject()
            content.set_data(f'BT /F1 18 Tf 20 500 Td (mobile-private-pdf-sentinel {text}) Tj ET'.encode())
            page[NameObject('/Contents')] = writer._add_object(content)
        writer.write(output)
    return output.getvalue()


PDF = search_fixture()


@contextmanager
def native_pdf(document):
    # Real PDF decoding is separately exercised with Qt;
    # this fixture keeps the mobile UI suite independent of desktop Qt imports.
    class Renderer:
        count = 3
        def render(self, index):
            return PNG
    yield Renderer()


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
                self.assertEqual(reader.source.data, b'')
                self.assertIsNone(owner.crypt_image.image)
                self.assertFalse(app.private_sessions.controllers)
                for path in root.rglob('*'):
                    if path.is_file() and path != local:
                        self.assertNotIn(b'mobile-private-pdf-sentinel', path.read_bytes())
            app.loop.run_until_complete(check())


if __name__ == '__main__':
    unittest.main()
