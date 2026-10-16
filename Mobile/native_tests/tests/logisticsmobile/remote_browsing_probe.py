"""Targeted native remote-browser validation with synthetic memory backends.

Run as a separate app ID. This is local evidence, not the release CASES suite.
"""
import asyncio
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import traceback
from uuid import uuid4
from zipfile import ZipFile

from commonUtils.runtime.document_access import LocalDocuments
from features.rclone.mobile.cloud import CloudClient
from features.rclone.mobile.remote_readers import RemoteReaders
from logisticsmobile.app import LogisticsMobile
from .reader_parity_probe import image_bytes, book_bytes

BUNDLE = 'io.github.ispaure.logisticsremoteprobe'
SENTINEL = 'Remote validation memory sentinel'


def preview_controls(widget):
    yield str(getattr(widget, 'text', ''))
    for child in getattr(widget, 'children', ()):
        yield from preview_controls(child)
    content = getattr(widget, 'content', None)
    if content is not None:
        yield from preview_controls(content)


class RemoteProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('remote-validation-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def until(self, predicate, message):
        for _ in range(150):
            if predicate():
                return
            await asyncio.sleep(.1)
        raise AssertionError(message)

    async def visit(self, remote, folder='folder'):
        assert await self.open_picker_folder(dict(kind='remote', value=(remote, folder),
            source='Remote', remote=remote)), self.cloud_status.value
        return self.body

    async def listing_responsiveness(self, output, result, cases):
        """Exercise UIKit publication, not just a dummy backend's row count."""
        from threading import Event
        seed = output / ('large-listing-seed-' + uuid4().hex)
        seed.mkdir()
        for index in range(200):
            folder = seed / f'series-{index:03}'
            folder.mkdir()
            (folder / 'nested.txt').write_text('Immediate listing must not include this file')
        measurements = result['large_listing'] = {}
        for remote in ('Cloud', 'Secret'):
            identity = await asyncio.to_thread(self.cloud_client.connection_identity, remote)
            await asyncio.to_thread(self.cloud_client.request, 'mirror_sync', remote=remote, path='mangas',
                identity=identity, local_path=str(seed.resolve()), run=uuid4().hex, push=True, decrypted=True)
            self.cloud_remote.value, self.cloud_location.value = remote, 'mangas'
            self.show_cloud()
            original = self.cloud_client.entries
            started, release = Event(), Event()
            calls = []
            def delayed_listing(name, path=''):
                calls.append((name, path))
                started.set()
                if not release.wait(15):
                    raise TimeoutError('Listing fixture did not resume')
                return original(name, path)
            self.cloud_client.entries = delayed_listing
            loop = asyncio.get_running_loop()
            gaps = []
            async def heartbeat():
                previous = loop.time()
                while True:
                    await asyncio.sleep(.05)
                    now = loop.time()
                    gaps.append(now - previous)
                    previous = now
            beat = asyncio.create_task(heartbeat())
            listing = asyncio.create_task(self.browse_cloud(preserve_path=True))
            try:
                await self.until(started.is_set, 'Listing never reached worker')
                await asyncio.sleep(2.1)
                assert ' · 2s' in self.cloud_status.value, self.cloud_status.value
                self.show_locations()
                await asyncio.sleep(.1)
                other = 'Secret' if remote == 'Cloud' else 'Cloud'
                self.choose_folder(other)
                assert self.folder_picker_selected['remote'] == other
                assert not listing.done()
                release.set()
                assert await listing, self.cloud_status.value
                await asyncio.sleep(.1)
                browser = self.remote_browser
                assert len(browser.entries) == 200
                assert all(entry.container for entry in browser.entries)
                assert len(browser.buttons) == 200
                browser.next_page()
                assert len(browser.buttons) == 200
                await asyncio.sleep(.1)
                browser.show_tiles()
                assert len(browser.buttons) == 200
                await asyncio.sleep(.1)
                browser.search.value = 'series-199'
                assert len(browser.buttons) == 1
                assert calls == [(remote, 'mangas')], calls
                assert self.folder_picker_selected['remote'] == other
                await asyncio.sleep(.1)
                measurements[remote] = dict(max_ui_gap_seconds=max(gaps), listing_calls=len(calls),
                    folders=200, timer_advanced=True, hub_menu_opened=True)
                assert max(gaps) < 1, measurements[remote]
                cases.append(remote.lower() + '_200_folders_timer_menu_and_bounded_publication')
            finally:
                release.set()
                await listing
                self.cloud_client.entries = original
                beat.cancel()
                try:
                    await beat
                except asyncio.CancelledError:
                    pass
                self.remote_browser.mode = 'List'
                self.remote_browser.search.value = ''

    async def probe(self):
        output = Path(self.paths.cache) / 'remote-browser-evidence'
        output.mkdir(exist_ok=True)
        cases = []
        result = dict(success=False, target='android' if type(self._impl).__module__.startswith('toga_android.') else 'ios',
            sys_platform=sys.platform,
            backend=type(self._impl).__module__, cases=cases,
            probe_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
            scope='Synthetic memory remotes in a separate app; simulator/emulator evidence, not physical-device or live-cloud validation.')
        try:
            manifest = Path(__file__).parents[2] / 'source.json'
            if manifest.exists():
                result['source'] = json.loads(manifest.read_text())
            seed = output / ('fixtures-' + uuid4().hex)
            seed.mkdir()
            (seed / 'note.txt').write_text(SENTINEL)
            (seed / 'note.md').write_text(SENTINEL)
            (seed / 'unsupported.bin').write_bytes(b'not directly supported')
            for name in ('broken.png', 'broken.cbz', 'broken.epub'):
                (seed / name).write_bytes(b'Invalid document fixture')
            (seed / 'large.txt').write_bytes(b'x' * (1024 * 1024 + 1))
            (seed / 'nested').mkdir()
            (seed / 'nested/deep.txt').write_text('Nested remote copy')
            (seed / 'empty').mkdir()
            image = image_bytes(b'\x20\x70\xd0\xff', 80, 120)
            (seed / 'page.png').write_bytes(image)
            (seed / 'book.epub').write_bytes(book_bytes(private=SENTINEL))
            with ZipFile(seed / 'comic.cbz', 'w') as archive:
                archive.writestr('page.png', image)
            package = output / 'Synthetic.zip'
            with ZipFile(package, 'w') as archive:
                archive.writestr('Cloud.txt', '[Cloud]\ntype=memory\n')
                archive.writestr('Secret.txt', '[Secret]\ntype=crypt\nremote=Cloud:encrypted\n'
                    'password=kbLdY_D-MRsrDH6_akD3SfOzlJ0VseUk2jfUrywMSTOLmTrSvFOxCkP94a-Ul-w\n')
            self.show_cloud(present=False)
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
            self.cloud_client = CloudClient()
            names = await asyncio.to_thread(self.cloud_client.import_package, LocalDocuments(), package, 'synthetic-session-password', remember=False)
            self.crypt_copies.client = self.cloud_client
            self.set_loaded_remote_names(names)
            self.cloud_crypt_remotes = set(await asyncio.to_thread(self.cloud_client.crypt_remotes))
            for remote in ('Cloud', 'Secret'):
                identity = await asyncio.to_thread(self.cloud_client.connection_identity, remote)
                await asyncio.to_thread(self.cloud_client.request, 'mirror_sync', remote=remote, path='folder',
                    identity=identity, local_path=str(seed.resolve()), run=uuid4().hex, push=True, decrypted=True)

            await self.listing_responsiveness(output, result, cases)

            for remote in ('Cloud', 'Secret'):
                panel = await self.visit(remote)
                browser = self.remote_browser
                assert len(browser.entries) == 11, self.cloud_status.value
                assert browser.thumbnail is None, 'Remote browsing must not enqueue cover reads'
                assert not hasattr(browser.search_provider, 'list')
                browser.search.value = 'deep'
                await asyncio.sleep(.4)
                assert not browser.entries, 'Current-folder search included a nested entry'
                browser.search.value = ''
                from .fixtures import capture_window
                await asyncio.sleep(.3)
                await capture_window(self, output / (remote.lower() + '-browser.png'))
                folder = next(entry for entry in browser.entries if entry.label == 'nested')
                await browser._select_pressed(folder, browser.buttons[folder.identity])
                assert self.cloud_path == 'folder/nested'
                await browser.go_back()
                assert self.cloud_path == 'folder'
                cases.append(remote.lower() + '_navigation_and_current_folder_search')

                for filename in ('note.txt', 'note.md', 'comic.cbz', 'page.png', 'book.epub'):
                    await self.visit(remote)
                    entry = next(entry for entry in browser.entries if entry.payload['path'] == 'folder/' + filename)
                    await browser.buttons[entry.identity].on_press()
                    owner = self.private_sessions.active
                    assert owner is not None and owner.crypt_reader.read_only
                    assert owner.crypt_view in self.body.children, self.cloud_status.value
                    assert not owner.crypt_save.enabled
                    controls = '\n'.join([*preview_controls(owner.crypt_view),
                        *preview_controls(owner.crypt_tools_view),
                        *(label for label, _ in owner.crypt_actions_menu.actions)]).lower()
                    assert not any(label in controls for label in ('save', 'download', 'edit metadata', 'discard changes')), controls
                    if filename in ('note.txt', 'note.md'):
                        assert owner.crypt_text.readonly and owner.crypt_text.value == SENTINEL
                        assert {label for label, _ in owner.crypt_actions_menu.actions} == {'Reader tools…', 'Close private document'}
                        if filename == 'note.md':
                            owner.toggle_private_preview()
                            assert owner.crypt_preview_button.text == 'Text'
                            owner.toggle_private_preview()
                            assert owner.crypt_text.readonly
                    elif filename == 'book.epub':
                        view = owner.provider_epub_view
                        if hasattr(view, 'webview'):
                            rendered = ''
                            for _ in range(150):
                                rendered = await view.webview.evaluate_javascript('document.body ? document.body.textContent : ""')
                                if SENTINEL in str(rendered):
                                    break
                                await asyncio.sleep(.1)
                            assert SENTINEL in str(rendered), str(rendered)[:200]
                        else:
                            assert SENTINEL in view.text.value
                    else:
                        canvas = owner.provider_spread.canvases[0] if hasattr(owner, 'provider_spread') else owner.crypt_image
                        assert canvas.image is not None
                    assert owner.edit_crypt_metadata() is None
                    if filename == 'comic.cbz':
                        from threading import get_ident
                        ui_thread = get_ident()
                        original_request = self.cloud_client.request
                        ui_requests = []
                        def trace_request(action, **values):
                            if get_ident() == ui_thread:
                                ui_requests.append(action)
                            return original_request(action, **values)
                        self.cloud_client.request = trace_request
                        try:
                            self.show_locations()
                            other = 'Secret' if remote == 'Cloud' else 'Cloud'
                            self.choose_folder(other)
                            assert self.folder_picker_selected['remote'] == other
                            assert not ui_requests, ui_requests
                        finally:
                            self.cloud_client.request = original_request
                        cases.append(remote.lower() + '_comic_return_hub_menu_has_no_native_ui_requests')
                        panel = await self.visit(remote)
                        owner.resume_crypt()
                        await asyncio.sleep(0)
                        await self.until(lambda: not owner.operation_busy, 'Cached comic did not resume')
                    labels = {label for label, _ in owner.crypt_actions_menu.actions}
                    assert 'Previous comic' not in labels and 'Next comic' not in labels
                    if filename == 'page.png':
                        assert labels == {'Reader tools…', 'Fit image', 'Close private document'}
                        owner.crypt_actions_menu.invoke(owner.fit_private_page)
                    if filename in ('comic.cbz', 'book.epub'):
                        assert 'Appearance…' in labels
                        owner.crypt_actions_menu.invoke(owner.show_provider_layout)
                        assert owner.provider_appearance in self.body.children
                        assert self.routes.back()
                        assert owner.crypt_view in self.body.children
                    owner.crypt_actions_menu.invoke(owner.show_private_tools)
                    assert owner.crypt_tools_view in self.body.children
                    assert self.routes.back()
                    assert owner.crypt_view in self.body.children
                    if remote == 'Secret' and filename == 'comic.cbz':
                        await asyncio.sleep(.3)
                        await capture_window(self, output / 'crypt-remote-reader.png')
                    assert self.routes.back()
                    assert self.body is panel
                    assert self.private_sessions.close(owner.session.id, discard=True)
                    cases.append(remote.lower() + '_direct_' + filename.replace('.', '_'))

                from unittest.mock import AsyncMock, patch
                await self.visit(remote)
                with patch.object(self.main_window, 'dialog', new=AsyncMock()) as dialog:
                    row = next(row for row in self.cloud_rows.values() if row['path'].endswith('unsupported.bin'))
                    assert not await self.open_remote_document(row)
                    dialog.assert_awaited_once()
                    assert type(dialog.call_args.args[0]).__name__ == 'InfoDialog'
                cases.append(remote.lower() + '_manual_copy_dialog')

                for filename in ('large.txt', 'broken.png', 'broken.cbz', 'broken.epub', 'missing.txt'):
                    panel = await self.visit(remote)
                    row = next((row for row in self.cloud_rows.values() if row['path'] == 'folder/' + filename),
                        dict(path='folder/' + filename, directory=False, size=10))
                    with patch.object(self.main_window, 'dialog', new=AsyncMock()) as dialog:
                        assert not await self.open_remote_document(row), filename
                        dialog.assert_awaited_once()
                    assert not self.private_sessions.controllers, filename
                    assert self.body is panel, filename
                    cases.append(remote.lower() + '_error_' + filename.replace('.', '_'))
                await self.visit(remote)
                previous = dict(self.cloud_rows)
                self.cloud_location.value = '../invalid-directory'
                assert not await self.browse_cloud(preserve_path=True)
                assert self.cloud_rows == previous and self.cloud_path == 'folder'
                cases.append(remote.lower() + '_failed_navigation_keeps_listing')

                for name in ('choose_cloud_copy', 'download_cloud', 'download_crypt',
                             'copy_current_folder', 'download_current_folder_crypt'):
                    assert not hasattr(self, name), name
                assert not self.downloads.items()
                for path in self.private_root.rglob('*'):
                    if path.is_file():
                        assert SENTINEL.encode() not in path.read_bytes(), str(path)
                cases.append(remote.lower() + '_preview_only_without_persisted_plaintext')

            for remote in ('Cloud', 'Secret'):
                reader = await asyncio.to_thread(RemoteReaders(self.cloud_client, remote).open, 'folder/note.txt')
                assert reader.text == SENTINEL
                reader.source.close()
            cases.append('previews_preserve_remote_originals')
            await self.visit('Secret')
            row = next(row for row in self.cloud_rows.values() if row['path'].endswith('note.txt'))
            assert await self.open_remote_document(row), self.cloud_status.value
            owner = self.private_sessions.active
            await asyncio.to_thread(self.cloud_client.lock)
            await asyncio.sleep(.5)
            assert not self.private_sessions.available(owner.session.id)
            cases.append('credential_lock_retires_remote_reader')
            assert not self.remote_browser.buttons and self.remote_browser.tree is None
            names = await asyncio.to_thread(self.cloud_client.import_package, LocalDocuments(), package, 'synthetic-session-password', remember=False)
            self.set_loaded_remote_names(names)
            await self.visit('Cloud')
            row = next(row for row in self.cloud_rows.values() if row['path'].endswith('note.txt'))
            assert await self.open_remote_document(row)
            owner = self.private_sessions.active
            await asyncio.to_thread(self.cloud_client.import_package, LocalDocuments(), package, 'synthetic-session-password', remember=False)
            await asyncio.sleep(.5)
            assert not self.private_sessions.available(owner.session.id)
            cases.append('credential_replacement_retires_remote_reader')
            self.show_cloud()
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
            traceback.print_exc()
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print('REMOTE_BROWSER_RESULT=' + json.dumps(result), flush=True)
        print('REMOTE_BROWSER_PATH=' + str(output), flush=True)
        await asyncio.sleep(.2)
        os._exit(0 if result['success'] else 1)


def main():
    return RemoteProbe('Remote Browser Validation', BUNDLE)
