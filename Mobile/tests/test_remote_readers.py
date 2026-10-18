"""Remote reader UI contracts with a bounded in-memory engine fixture."""
import asyncio
import base64
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.ui.native.password_input import PasswordInput
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile

from logisticsmobile.app import LogisticsMobile
from features.rclone.mobile.remote_readers import RemoteSource


def assert_preview_only_ui(test, owner):
    """Check visible controls and overflow tools, including disabled widgets."""
    def labels(widget):
        yield str(getattr(widget, 'text', ''))
        children = getattr(widget, 'children', ())
        for child in children:
            yield from labels(child)
        content = getattr(widget, 'content', None)
        if content is not None:
            yield from labels(content)
    text = '\n'.join([*labels(owner.crypt_view), *labels(owner.crypt_tools_view),
                      *(label for label, _ in owner.crypt_actions_menu.actions)]).lower()
    for forbidden in ('save', 'download', 'edit metadata', 'discard changes', 'previous comic', 'next comic'):
        test.assertNotIn(forbidden, text)
    actions = {label for label, _ in owner.crypt_actions_menu.actions}
    if owner.crypt_reader.editable:
        expected = {'Reader tools…', 'Close private document'}
        if owner.crypt_reader.kind in {'.md', '.markdown'}:
            expected.add('Open beside another document')
        test.assertEqual(actions, expected)
    elif getattr(owner.crypt_reader, 'image_document', False):
        test.assertEqual(actions, {'Reader tools…', 'Fit image', 'Close private document'})


class RemoteClient:
    supports_streaming = True
    generation = 1

    def __init__(self):
        self.calls = []
        self.text = b'REMOTE_MEMORY_SENTINEL'
        self.files = {'note.txt': self.text}
        self.cached = {}

    def connection_identity(self, remote):
        return 'a' * 64

    def entries(self, remote, path=''):
        self.calls.append(('list', path))
        return [dict(path='note.txt', directory=False, size=len(self.text)),
                dict(path='movie.mp4', directory=False, size=200),
                dict(path='folder', directory=True, size=0)]

    def request(self, action, **values):
        self.calls.append((action, values.get('path')))
        if action == 'remote_cache_close':
            self.cached.pop(values['run'], None)
            return {}
        if action == 'remote_cache_status':
            data = self.cached.get(values['run'], b'')
            return dict(done=len(data), total=len(data), ready=bool(data))
        data = self.cached[values['run']] if action == 'remote_cache_archive' else self.files[values['path']]
        if action == 'remote_cache_open':
            self.cached[values['run']] = data
            return dict(size=len(data), revision='one')
        if action == 'remote_cache_archive':
            data = self.cached[values['run']]
        if action == 'remote_stat':
            return dict(size=len(data), revision='one')
        if action == 'remote_range':
            start = values['offset']
            return dict(data=base64.b64encode(data[start:start+values['count']]).decode())
        if action in {'remote_archive', 'remote_cache_archive'}:
            with ZipFile(BytesIO(data)) as archive:
                if values.get('member'):
                    return dict(data=base64.b64encode(archive.read(values['member'])).decode())
                return [dict(name=row.filename, size=row.file_size, crc=row.CRC, flags=0,
                             directory=row.is_dir()) for row in archive.infolist()]
        raise AssertionError('Unexpected request: ' + action)

    def cancel(self):
        pass


class RemoteReaderTests(unittest.TestCase):
    def test_parent_folder_is_in_main_browser_and_walks_back_to_remote_root(self):
        with TemporaryDirectory() as folder:
            LogisticsMobile.storage_root = Path(folder)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            client = app.cloud_client = RemoteClient()

            async def check():
                app.show_cloud()
                toolbar = app.cloud_up.parent
                ancestor = toolbar
                while ancestor is not None and ancestor is not app.cloud_view:
                    ancestor = ancestor.parent
                self.assertIs(ancestor, app.cloud_view)
                self.assertIn(app.cloud_status, toolbar.children)
                self.assertEqual(app.cloud_up.control_icon, 'back')
                self.assertEqual(app.cloud_up.style.width, 48)
                self.assertNotIn(app.remote_browser.back_button,
                                 app.remote_browser.navigation_controls.children)
                app.cloud_remote.items = ['Files']
                app.cloud_location.value = 'Books/Series'
                self.assertTrue(await app.browse_cloud(preserve_path=True))
                for expected in ('Books', '', ''):
                    await app.cloud_up.on_press()
                    self.assertEqual(app.cloud_path, expected)
                    self.assertEqual(app.cloud_location.value, expected)
                    self.assertEqual(client.calls[-1], ('list', expected))
                app.set_cloud_busy(True)
                self.assertTrue(app.cloud_up.enabled)
                app.set_cloud_busy(False)
                self.assertTrue(app.cloud_up.enabled)

            app.loop.run_until_complete(check())

    def test_slow_200_folder_listing_keeps_timer_and_hub_menus_live_then_pages_without_relisting(self):
        from threading import Event, get_ident
        started, release = Event(), Event()
        ui_thread = get_ident()
        class ListingClient(RemoteClient):
            def entries(client, remote, path=''):
                self.assertNotEqual(get_ident(), ui_thread)
                client.calls.append(('list', path))
                started.set()
                if not release.wait(6):
                    raise TimeoutError('Synthetic listing was not released')
                return [dict(path=f'mangas/series-{index:03}', directory=True, size=-1) for index in range(200)]
        with TemporaryDirectory() as folder:
            LogisticsMobile.storage_root = Path(folder)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            client = app.cloud_client = ListingClient()
            async def check():
                app.show_cloud()
                app.cloud_remote.items = ['Files', 'Other']
                app.cloud_location.value = 'mangas'
                task = asyncio.create_task(app.browse_cloud(preserve_path=True))
                try:
                    for _ in range(100):
                        if started.is_set():
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(started.is_set())
                    await asyncio.sleep(2.1)
                    self.assertIn(' · 2s', app.cloud_status.value)
                    app.show_locations()
                    app.choose_folder('Other')
                    self.assertEqual(app.folder_picker_selected['remote'], 'Other')
                    self.assertTrue(app.cloud_cancel.enabled)
                    self.assertFalse(task.done())
                finally:
                    release.set()
                self.assertTrue(await task)
                browser = app.remote_browser
                self.assertEqual(len(browser.entries), 200)
                self.assertEqual(len(browser.buttons), browser.page_size)
                self.assertIn(browser.paging, browser.widget.children)
                browser.next_page()
                self.assertEqual(len(browser.buttons), browser.page_size)
                browser.show_tiles()
                self.assertEqual(len(browser.buttons), browser.page_size)
                browser.search.value = 'series-199'
                for _ in range(100):
                    if len(browser.buttons) == 1:
                        break
                    await asyncio.sleep(.01)
                self.assertEqual(len(browser.buttons), 1)
                self.assertEqual(client.calls, [('list', 'mangas')])
                self.assertEqual(app.folder_picker_selected['remote'], 'Other')
            app.loop.run_until_complete(check())

    def test_comic_is_cached_once_then_pages_use_memory_and_close_releases_it(self):
        from PIL import Image
        from features.rclone.mobile.remote_readers import RemoteReaders
        pages = []
        comic = BytesIO()
        with ZipFile(comic, 'w') as archive:
            for index, color in enumerate(('red', 'blue')):
                image = BytesIO()
                Image.new('RGB', (24, 32), color).save(image, 'PNG')
                pages.append(image.getvalue())
                archive.writestr(f'{index}.png', pages[-1])
        client = RemoteClient()
        client.files['comic.cbz'] = comic.getvalue()
        progress = []
        reader = RemoteReaders(client, 'Files', progress=progress.append).open('comic.cbz')
        source = reader.source
        self.addCleanup(source.close)
        self.assertEqual(sum(action == 'remote_cache_open' for action, _ in client.calls), 1)
        del client.files['comic.cbz']
        client.calls.clear()
        self.assertEqual(reader.page(0), ('image', pages[0]))
        self.assertEqual(reader.page(1), ('image', pages[1]))
        self.assertEqual(reader.page(0), ('image', pages[0]))
        self.assertTrue(all(action == 'remote_cache_archive' for action, _ in client.calls))
        self.assertTrue(any('100%' in message for message in progress))
        client.generation += 1
        with self.assertRaisesRegex(ValueError, 'Credentials'):
            reader.page(1)
        self.assertFalse(client.cached)
        self.assertIsNone(source.cache_token)

    def test_epub_snapshot_survives_remote_removal_and_releases_on_close(self):
        from Mobile.native_tests.tests.logisticsmobile.fixtures import make_books
        from features.rclone.mobile.remote_readers import RemoteReaders
        with TemporaryDirectory() as folder:
            epub, _ = make_books(Path(folder))
            client = RemoteClient()
            client.files['book.epub'] = epub.read_bytes()
            reader = RemoteReaders(client, 'Files').open('book.epub')
            source = reader.source
            self.addCleanup(source.close)
            self.assertEqual(sum(action == 'remote_cache_open' for action, _ in client.calls), 1)
            del client.files['book.epub']
            client.calls.clear()
            self.assertIn('Native EPUB first', reader.page(0)[1])
            self.assertFalse(any(action in {'remote_range', 'remote_stat', 'remote_archive'}
                                 for action, _ in client.calls))
            source.close()
            self.assertFalse(client.cached)

    def test_comic_download_failure_releases_partial_cache(self):
        from features.rclone.mobile.remote_readers import RemoteReaders
        class BrokenClient(RemoteClient):
            def request(self, action, **values):
                result = super().request(action, **values)
                if action == 'remote_cache_open':
                    raise OSError('Synthetic interrupted download')
                return result
        client = BrokenClient()
        for name in ('comic.cbz', 'book.epub'):
            with self.subTest(name=name):
                client.files[name] = b'partial archive'
                with self.assertRaisesRegex(OSError, 'interrupted'):
                    RemoteReaders(client, 'Files').open(name)
                self.assertFalse(client.cached)

    def test_remote_browsing_never_fetches_thumbnails_in_list_or_tiles(self):
        with TemporaryDirectory() as folder:
            LogisticsMobile.storage_root = Path(folder)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            client = RemoteClient()
            client.entries = lambda remote, path='': [dict(path='comic.cbz', directory=False, size=40*1024*1024)]
            app.cloud_client = client
            async def check():
                app.show_cloud(present=False)
                app.cloud_remote.items = ['Files']
                self.assertTrue(await app.browse_cloud())
                self.assertIsNone(app.remote_browser.thumbnail)
                app.remote_browser.mode = 'Tiles'
                app.remote_browser.render()
                await asyncio.sleep(.05)
                self.assertEqual(client.calls, [])
            app.loop.run_until_complete(check())

    def test_slow_remote_open_reports_step_elapsed_time_and_cancels(self):
        from threading import Event
        started, release = Event(), Event()
        class SlowClient(RemoteClient):
            def request(self, action, **values):
                if action == 'remote_stat':
                    started.set()
                    if not release.wait(5):
                        raise TimeoutError('Synthetic remote did not resume')
                return super().request(action, **values)
            def cancel(self):
                release.set()
        with TemporaryDirectory() as folder:
            LogisticsMobile.storage_root = Path(folder)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.cloud_client = SlowClient()
            async def check():
                app.show_cloud(present=False)
                app.cloud_remote.items = ['Files']
                app.cloud_open_remote = 'Files'
                task = asyncio.create_task(app.open_remote_document(dict(path='note.txt', directory=False, size=20)))
                try:
                    for _ in range(100):
                        if started.is_set():
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(started.is_set())
                    self.assertTrue(app.cloud_busy)
                    self.assertTrue(app.cloud_cancel.enabled)
                    self.assertIsNone(app.cloud_transfer_progress.max)
                    initial_status = app.cloud_status.value
                    for _ in range(250):
                        await asyncio.sleep(.01)
                        if app.cloud_status.value != initial_status and ' · 0s' not in app.cloud_status.value:
                            break
                    self.assertIn('Checking remote file and connection', app.cloud_status.value)
                    self.assertNotIn(' · 0s', app.cloud_status.value)
                    self.assertIn(app.cloud_view, app.body.children)
                    app.cancel_cloud()
                    self.assertFalse(await asyncio.wait_for(task, 2))
                    self.assertIn('cancelled', app.cloud_status.value)
                    self.assertFalse(app.cloud_busy)
                    self.assertEqual(app.cloud_transfer_progress.max, 100)
                    self.assertFalse(app.private_sessions.controllers)
                    status = app.cloud_status.value
                    await asyncio.sleep(.05)
                    self.assertEqual(app.cloud_status.value, status)
                finally:
                    release.set()
                    await task
            app.loop.run_until_complete(check())

    def test_item_actions_open_selected_folder_and_prompt_for_inner_password(self):
        from commonUtils.archives.zip_access import ArchivePasswordError
        from features.rclone.mobile.remote_readers import RemoteReaders
        with TemporaryDirectory() as folder:
            LogisticsMobile.storage_root = Path(folder)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            app.cloud_client = RemoteClient()
            async def check():
                app.show_cloud()
                app.cloud_remote.items = ['Cloud', 'Secret']
                app.cloud_open_remote = 'Cloud'
                await app.browse_cloud()
                browser = app.remote_browser
                entry = next(entry for entry in browser.entries if entry.container)
                row = browser.items.children[browser.entries.index(entry)]
                import toga
                menu = [child for child in row.children[0].children if isinstance(child, toga.Button)][-1]
                await menu.on_press()
                self.assertIn(app.remote_item_view, app.body.children)
                self.assertNotIn(app.cloud_advanced_view, app.body.children)
                open_button = next(child for child in app.remote_item_view.children
                                   if getattr(child, 'text', '') == 'Open folder')
                with patch.object(app, 'browser_cloud_folder', new=AsyncMock(return_value=True)) as opened:
                    self.assertTrue(await open_button.on_press())
                    opened.assert_awaited_once()
                    self.assertEqual(opened.call_args.args[0]['path'], entry.payload['path'])
                with patch.object(RemoteReaders, 'open', side_effect=ArchivePasswordError('ZIP password required')), \
                        patch.object(app.main_window, 'dialog', new=AsyncMock()) as dialog:
                    self.assertFalse(await app.open_remote_document(dict(path='locked.cbz', directory=False, size=100)))
                    dialog.assert_not_awaited()
                password = next(child for child in app.remote_item_view.children if isinstance(child, PasswordInput))
                password.value = 'synthetic-inner-password'
                open_button = next(child for child in app.remote_item_view.children
                                   if getattr(child, 'text', '') == 'Open preview')
                with patch.object(app, 'open_crypt', new=AsyncMock(return_value=True)) as opened:
                    self.assertTrue(await open_button.on_press())
                    self.assertEqual(app.crypt_password.value, 'synthetic-inner-password')
                    self.assertEqual(password.value, '')
                    self.assertEqual(opened.call_args.kwargs['key'], 'locked.cbz')
                app.cloud_client.generation += 1
                with patch.object(app, 'open_remote_document', new=AsyncMock()) as opened:
                    self.assertFalse(await open_button.on_press())
                    opened.assert_not_awaited()
                password.value = 'retired-password'
                app.clear_private_catalog()
                self.assertEqual(password.value, '')
                self.assertEqual(len(app.remote_item_view.children), 1)
                self.assertIn('Connection closed', app.remote_item_view.children[0].text)
            try:
                app.loop.run_until_complete(check())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_folder_hub_comic_tap_shows_loading_then_opens_reader(self):
        from PIL import Image
        image = BytesIO()
        Image.new('RGB', (24, 32), 'blue').save(image, 'PNG')
        comic = BytesIO()
        with ZipFile(comic, 'w') as archive:
            archive.writestr('page.png', image.getvalue())
        with TemporaryDirectory() as folder:
            LogisticsMobile.storage_root = Path(folder)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            client = RemoteClient()
            row = dict(path='folder/comic.cbz', directory=False, size=len(comic.getvalue()))
            client.files[row['path']] = comic.getvalue()
            client.entries = lambda remote, path='': [row]
            app.cloud_client = client
            async def check():
                app.show_cloud(present=False)
                app.cloud_remote.items = ['Cloud', 'Secret']
                app.cloud_open_remote = 'Cloud'
                entry = dict(kind='remote', value=('Secret', 'folder'), source='Remote', remote='Secret')
                self.assertTrue(await app.open_picker_folder(entry))
                self.assertEqual(app.cloud_path, 'folder')
                browser = app.remote_browser
                item = browser.entries[0]
                started, release = asyncio.Event(), asyncio.Event()
                original = app.open_crypt
                async def delayed_open(**kwargs):
                    started.set()
                    await release.wait()
                    return await original(**kwargs)
                with patch.object(app, 'open_crypt', side_effect=delayed_open):
                    task = browser.buttons[item.identity].on_press()
                    await started.wait()
                    self.assertIn('Opening remote file:', app.cloud_status.value)
                    release.set()
                    await task
                owner = app.private_sessions.active
                self.assertIsNotNone(owner)
                self.assertIn(owner.crypt_view, app.body.children)
                self.assertEqual(owner.crypt_reader.page(0), ('image', image.getvalue()))
                self.assertIn('Opened remote file:', app.cloud_status.value)
                owner.close_crypt()
                with patch.object(app, 'open_crypt', new=AsyncMock(side_effect=PermissionError('Setup denied'))), \
                        patch.object(app.main_window, 'dialog', new=AsyncMock()) as dialog:
                    self.assertFalse(await app.open_remote_document(row))
                    self.assertIn('Setup denied', app.cloud_status.value)
                    dialog.assert_awaited_once()
                with patch.object(app, 'open_crypt', new=AsyncMock(return_value=False)):
                    self.assertFalse(await app.open_remote_document(row))
                    self.assertIn('could not open', app.cloud_status.value)
            try:
                app.loop.run_until_complete(check())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_direct_text_is_read_only_and_unsupported_open_only_shows_dialog(self):
        with TemporaryDirectory() as folder:
            LogisticsMobile.storage_root = Path(folder)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            client = RemoteClient()
            app.cloud_client = client
            try:
                app.show_cloud()
                app.cloud_remote.items = ['Files']
                self.assertTrue(app.loop.run_until_complete(app.browse_cloud()))
                self.assertNotIn('\n', app.cloud_status.value)
                self.assertFalse(hasattr(app.remote_browser.search_provider, 'list'))
                client.calls.clear()
                app.remote_browser.search.value = 'note'
                self.assertFalse(any(action == 'list' for action, _ in client.calls))
                with patch.object(app.main_window, 'dialog', new=AsyncMock()) as dialog:
                    self.assertFalse(app.loop.run_until_complete(app.open_remote_document(
                        dict(path='movie.mp4', directory=False, size=200))))
                    dialog.assert_awaited_once()
                self.assertEqual(client.calls, [])
                self.assertTrue(app.loop.run_until_complete(app.open_remote_document(
                    dict(path='note.txt', directory=False, size=len(client.text)))))
                owner = app.private_sessions.active
                assert_preview_only_ui(self, owner)
                self.assertTrue(owner.crypt_reader.read_only)
                self.assertTrue(owner.crypt_text.readonly)
                self.assertFalse(owner.crypt_save.enabled)
                app.loop.run_until_complete(owner.save_crypt())
                self.assertFalse(any('write' in action for action, _ in client.calls))
                for path in Path(folder).rglob('*'):
                    if path.is_file():
                        self.assertNotIn(client.text, path.read_bytes(), str(path))
            finally:
                app.main_window.close()
                app.loop.close()

    def test_failed_navigation_restores_unselected_listing_and_rejects_stale_credentials(self):
        with TemporaryDirectory() as folder:
            LogisticsMobile.storage_root = Path(folder)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            app.cloud_client = RemoteClient()
            try:
                app.show_cloud()
                app.cloud_remote.items = ['Files']
                self.assertTrue(app.loop.run_until_complete(app.browse_cloud()))
                app.browser_cloud_selected(None)
                previous = dict(app.cloud_rows)
                app.cloud_location.value = 'unavailable'
                with patch.object(app.cloud_client, 'entries', side_effect=ValueError('Synthetic read failure')):
                    self.assertFalse(app.loop.run_until_complete(app.browse_cloud(preserve_path=True)))
                self.assertEqual(app.cloud_rows, previous)
                self.assertEqual(app.cloud_entries.value, 'Select an item…')
                self.assertIn('Synthetic read failure', app.cloud_status.value)
                def replace(remote, path):
                    app.cloud_client.generation += 1
                    return []
                with patch.object(app.cloud_client, 'entries', side_effect=replace):
                    self.assertFalse(app.loop.run_until_complete(app.browse_cloud()))
                self.assertEqual(app.cloud_rows, {})
                self.assertIsNone(app.remote_browser.tree)
                self.assertIsNone(app.cloud_open_remote)
                self.assertFalse(app.remote_browser.buttons)
            finally:
                app.main_window.close()
                app.loop.close()

    def test_remote_markdown_returns_to_readonly_text_without_edit_label(self):
        with TemporaryDirectory() as folder:
            LogisticsMobile.storage_root = Path(folder)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            app.cloud_client = RemoteClient()
            app.cloud_client.files['note.md'] = b'# Remote note'
            try:
                app.show_cloud()
                app.cloud_remote.items = ['Files']
                app.cloud_open_remote = 'Files'
                self.assertTrue(app.loop.run_until_complete(app.open_remote_document(dict(path='note.md', size=13, directory=False))))
                owner = app.private_sessions.active
                assert_preview_only_ui(self, owner)
                owner.toggle_private_preview()
                self.assertEqual(owner.crypt_preview_button.accessible_name, 'View source text')
                owner.toggle_private_preview()
                self.assertTrue(owner.crypt_text.readonly)
            finally:
                app.main_window.close()
                app.loop.close()

    def test_cached_ranges_fail_after_credential_revocation(self):
        client = RemoteClient()
        source = RemoteSource(client, 'Files', 'note.txt')
        with source.open('note.txt') as stream:
            self.assertEqual(stream.read(3), b'REM')
            client.generation += 1
            with self.assertRaisesRegex(ValueError, 'Credentials'):
                stream.seek(0)

    def test_direct_comic_and_image_share_read_only_private_sessions(self):
        from PIL import Image
        image = BytesIO()
        Image.new('RGB', (24, 32), 'blue').save(image, 'PNG')
        comic = BytesIO()
        with ZipFile(comic, 'w') as archive:
            archive.writestr('page.png', image.getvalue())
        with TemporaryDirectory() as folder:
            LogisticsMobile.storage_root = Path(folder)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            client = RemoteClient()
            client.files.update({'page.png': image.getvalue(), 'comic.cbz': comic.getvalue()})
            app.cloud_client = client
            try:
                app.show_cloud()
                app.cloud_remote.items = ['Files']
                app.cloud_open_remote = 'Files'
                for name in ('comic.cbz', 'page.png'):
                    self.assertTrue(app.loop.run_until_complete(app.open_remote_document(
                        dict(path=name, directory=False, size=len(client.files[name])))))
                    owner = app.private_sessions.active
                    assert_preview_only_ui(self, owner)
                    self.assertTrue(owner.crypt_reader.read_only)
                    self.assertFalse(owner.crypt_save.enabled)
                    self.assertIsNone(owner.edit_crypt_metadata())
                    owner.close_crypt()
            finally:
                app.main_window.close()
                app.loop.close()

    def test_remote_browser_has_no_standalone_copy_or_download_actions(self):
        with TemporaryDirectory() as folder:
            LogisticsMobile.storage_root = Path(folder)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = RemoteClient()
                app.show_cloud()
                for name in ('download_cloud', 'download_crypt', 'choose_cloud_copy',
                             'cloud_download', 'crypt_download', 'cloud_copy_button',
                             'copy_current_folder', 'download_current_folder_crypt', 'confirm_cloud_copy'):
                    self.assertFalse(hasattr(app, name), name)
                from features.rclone.mobile.cloud import CloudClient
                from features.rclone.localcrypt.mobile.copies import LocalCryptCopies
                for name in ('download', 'download_into', 'download_decrypted_into'):
                    self.assertFalse(hasattr(CloudClient, name), name)
                self.assertFalse(hasattr(app.downloads, 'save'))
                self.assertFalse(hasattr(app.downloads, 'fetch'))
                self.assertFalse(hasattr(LocalCryptCopies, 'fetch'))
                self.assertFalse(hasattr(LocalCryptCopies, 'fetch_folder'))
                self.assertEqual(app.downloads.items(), [])
            finally:
                app.main_window.close()
                app.loop.close()
