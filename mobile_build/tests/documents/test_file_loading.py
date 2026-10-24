"""File loading owns a temporary panel without leaving a Back-stack entry."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch
from toga_dummy.utils import EventLog

import toga
from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.resources import LocalTextCopies
from mobile.app import LogisticsMobile
from mobile.document_sources import reopen_file


class FileLoadingTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        LogisticsMobile.storage_root = Path(directory.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.app.show_cloud(present=False)
        self.path = self.app.private_root / 'loading.md'
        self.path.write_text('# Ready')
        self.copies = LocalTextCopies(LocalFiles(self.path.parent))

    def test_cancelled_or_failed_split_loading_restores_destination_bar(self):
        from mobile.document_sources import opening_status
        app = self.app
        async def exercise():
            for failure in (ValueError, asyncio.CancelledError):
                app.show_documents_hub()
                origin = app.body
                adaptive = app.adaptive
                adaptive.split = Mock()
                adaptive.secondary = Mock()
                def present(panel, *, route, title):
                    adaptive.detail_routes.append((route, panel, Mock()))
                    adaptive.in_detail = True
                    app.body = panel
                    app.route_changed(panel)
                def trim(count):
                    adaptive.detail_routes = adaptive.detail_routes[:count]
                try:
                    with patch.object(adaptive, 'present', side_effect=present), \
                            patch.object(adaptive, 'trim_details', side_effect=trim):
                        with self.assertRaises(failure):
                            with opening_status(app, dict(key='Pending.pdf')):
                                self.assertTrue(app._document_tabs_hidden)
                                raise failure()
                        self.assertIs(app.body, origin)
                        self.assertFalse(adaptive.in_detail)
                        self.assertFalse(app._document_tabs_hidden)
                finally:
                    adaptive.split = None
                    adaptive.detail_routes = []
                    adaptive.in_detail = False
        app.loop.run_until_complete(exercise())

    def test_real_byte_counts_switch_from_percentage_to_preparing(self):
        from mobile.document_sources import opening_status
        from mobile.loading_progress import reading_stream
        self.path.write_bytes(b'x' * (256 * 1024))
        started, release = Event(), Event()
        def read():
            with self.path.open('rb') as source, reading_stream(source) as stream:
                first = stream.read(64 * 1024)
                started.set()
                if not release.wait(3):
                    raise RuntimeError('Progress fixture timed out')
                return first + stream.read()
        async def exercise():
            self.app.show_home()
            with opening_status(self.app, dict(path=str(self.path))):
                content = self.app.body.children[0].children[1]
                bar, status = content.children[2:]
                task = asyncio.create_task(asyncio.to_thread(read))
                try:
                    self.assertTrue(await asyncio.to_thread(started.wait, 2))
                    await asyncio.sleep(.1)
                    self.assertEqual(bar.max, 256 * 1024)
                    self.assertEqual(bar.value, 64 * 1024)
                    self.assertEqual(status.text, 'Reading 25%')
                finally:
                    release.set()
                    data = await task
                self.assertEqual(len(data), 256 * 1024)
                await asyncio.sleep(.1)
                self.assertIsNone(bar.max)
                self.assertEqual(status.text, 'Preparing document…')
                reporter = self.app._file_loading['progress']
            reporter.publish(1, 2)
            await asyncio.sleep(.1)
            self.assertEqual(status.text, '')
        self.app.loop.run_until_complete(exercise())

    def test_unknown_size_and_stale_loading_updates_never_show_fake_percent(self):
        from mobile.document_sources import opening_status
        from mobile.loading_progress import reading_stream
        from io import BytesIO
        async def exercise():
            self.app.show_home()
            with opening_status(self.app, dict(key='Unknown.txt')):
                content = self.app.body.children[0].children[1]
                bar, status = content.children[2:]
                with reading_stream(BytesIO(b'content')) as stream:
                    self.assertEqual(stream.read(3), b'con')
                    await asyncio.sleep(.1)
                    self.assertIsNone(bar.max)
                    self.assertEqual(status.text, 'Reading file…')
                    self.assertEqual(stream.read(), b'tent')
                await asyncio.sleep(.1)
                self.assertIsNone(bar.max)
                self.assertEqual(status.text, 'Preparing document…')
                reporter = self.app._file_loading['progress']
                self.app._file_loading = None
                reporter.publish(9, 10)
                await asyncio.sleep(.1)
                self.assertEqual(status.text, 'Preparing document…')
        self.app.loop.run_until_complete(exercise())

    def test_reopen_panel_is_replaced_and_back_returns_to_each_origin(self):
        async def exercise():
            for destination in ('home', 'documents', 'files'):
                self.app.show_view(toga.Box(), destination=destination, root=True)
                origin = self.app.body
                from mobile.document_sources import _reopen_file

                async def inspect_panel(app, source):
                    self.assertEqual(app.native_host.state.destination, destination)
                    self.assertIsNot(app.body, origin)
                    self.assertTrue(app.routes.screens[destination][-1][0].startswith('file-loading:'))
                    content = app.body.children[0].children[1]
                    self.assertIsInstance(content.children[0], toga.ImageView)
                    self.assertEqual(content.children[1].text, self.path.name)
                    self.assertIsInstance(content.children[2], toga.ProgressBar)
                    return await _reopen_file(app, source)

                with patch('mobile.document_sources._reopen_file', inspect_panel):
                    self.assertTrue(await reopen_file(self.app, dict(type='local', path=str(self.path))))
                self.assertFalse(any(route.startswith('file-loading:')
                                     for route, *_ in self.app.routes.screens[destination]))
                self.assertTrue(self.app.routes.back())
                self.assertIs(self.app.body, origin)
        self.app.loop.run_until_complete(exercise())

    def delayed_open(self, *, fail=False, back=False, download=False):
        started, release = Event(), Event()
        target, method = (self.app.store, 'import_document') if download else (self.copies, 'open')
        original = getattr(target, method)

        def read(*args, **kwargs):
            started.set()
            if not release.wait(5):
                raise RuntimeError('Loading fixture timed out')
            if fail:
                raise ValueError('Unavailable file')
            return original(*args, **kwargs)

        async def exercise():
            self.app.show_home()
            origin = self.app.body
            operation = (self.app.open_download(path=self.path) if download else
                         self.app.open_crypt(copies=self.copies, key=self.path.name))
            task = asyncio.create_task(operation)
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                self.assertIsNot(self.app.body, origin)
                if back:
                    self.assertTrue(self.app.routes.back())
                    self.assertIs(self.app.body, origin)
                release.set()
                self.assertEqual(await task, not fail and not (download and back))
                self.assertIs(self.app.body, origin)
                self.assertFalse(self.app.routes.screens['home'])
            finally:
                release.set()
                await task
        with patch.object(target, method, side_effect=read):
            self.app.loop.run_until_complete(exercise())

    def test_failure_restores_opening_screen(self):
        with patch.object(self.app.main_window, 'dialog', new_callable=AsyncMock) as dialog:
            self.delayed_open(fail=True)
        dialog.assert_awaited_once()
        self.assertEqual(EventLog.performed_actions(dialog.call_args.args[0], 'create InfoDialog')[0]['title'], 'Could not open document')
        self.assertIn('Unavailable file', EventLog.performed_actions(dialog.call_args.args[0], 'create InfoDialog')[0]['message'])

    def test_back_during_loading_keeps_origin_after_completion(self):
        self.delayed_open(back=True)

    def test_back_during_local_import_keeps_origin_after_completion(self):
        self.delayed_open(back=True, download=True)

    def test_book_keeps_loading_panel_until_first_page_is_ready(self):
        from commonUtils.runtime.resources.documents import LocalDocuments
        from mobile.reader_sessions import ReaderController
        from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books

        async def exercise():
            epub, _ = make_books(self.path.parent)
            manager = self.app.reader_manager()
            record = manager.catalog.library_store.import_book(LocalDocuments(), epub)
            self.app.show_home()
            started, release = asyncio.Event(), asyncio.Event()
            original = ReaderController.display_book_page

            async def first_page(owner, index):
                started.set()
                await release.wait()
                await original(owner, index)

            with patch.object(ReaderController, 'display_book_page', first_page):
                task = asyncio.create_task(self.app.open_book(record['id']))
                try:
                    await asyncio.wait_for(started.wait(), 3)
                    self.assertTrue(self.app.routes.screens['home'][-1][0].startswith('file-loading:'))
                    release.set()
                    self.assertTrue(await task)
                    self.assertTrue(self.app.routes.screens['home'][-1][0].startswith('reader:'))
                finally:
                    release.set()
                    await task
            await manager.catalog.metadata_task
            await manager.catalog.library_scan_task
        self.app.loop.run_until_complete(exercise())
