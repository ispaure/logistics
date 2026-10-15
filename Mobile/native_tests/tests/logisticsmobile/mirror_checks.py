"""Native managed folders, background document use and verified writeback."""
import asyncio
from threading import Event
from unittest.mock import patch


async def exercise_mirrors(app, comic_key):
    started, release = Event(), Event()
    client = app.cloud_client
    request = client.request
    def gated(action, **values):
        if action == 'mirror_sync' and not started.is_set():
            started.set()
            # Cold native widget/layout startup is slower on hosted emulators.
            # Keep the synthetic transfer pending until the test releases it,
            # with a bounded escape so a deadlock still fails the native gate.
            if not release.wait(120):
                raise RuntimeError('Native background transfer fixture timed out.')
        return request(action, **values)
    original = app.editor.value
    with patch.object(client, 'request', side_effect=gated):
        task = asyncio.create_task(app.run_mirror_work(lambda client, cancel, progress:
            app.mirror_store().create(client, 'Fixture', 'logistics-native-check', cancelled=cancel, progress=progress), 'create'))
        try:
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(.05)
            assert started.is_set() and app.transfer_busy
            # Local directory browsing must not consume the cloud busy state or
            # overwrite the live transfer's cancellation handle.
            local = app.private_root / 'LocalFiles' / 'Browse during pull'
            local.mkdir(parents=True, exist_ok=True)
            (local / 'Local note.txt').write_text('Unrelated local file')
            cancel = app._crypt_cancel
            app.show_locations()
            assert 'Browse during pull' in app.folder_picker_choices
            assert 'Fixture' in app.folder_picker_choices
            app.choose_folder('Fixture')
            assert not app.folder_browse_button.enabled
            assert not await app.open_picker_folder(app.folder_picker_selected)
            app.show_locations()
            await app.folder_buttons['Browse during pull'].on_press()
            assert app.file_path == 'Browse during pull'
            assert app._crypt_cancel is cancel
            assert await app.browser_file_location(('Local files', 'Browse during pull'))
            assert any(item.label == 'Local note.txt' for item in app.file_browser.entries)
            await app.parent_file_folder()
            assert app.file_path == ''
            assert app.cloud_busy and app.transfer_busy and app._crypt_cancel is cancel
            assert not cancel.is_set()
            import base64
            from zipfile import ZipFile
            webp = base64.b64decode('UklGRhwAAABXRUJQVlA4TA8AAAAvAYAAEAcQ/Y8CBiKi/wEA')
            comic = local / 'Local comic.cbz'
            with ZipFile(comic, 'w') as archive:
                archive.writestr('page2.webp', webp)
                archive.writestr('page10.webp', webp)
            original_comic = comic.read_bytes()
            async def tap(name):
                await app.show_local_location()
                assert await app.browser_file_location(('Local files', 'Browse during pull'))
                browser = app.file_browser
                entry = next(item for item in browser.entries if item.label == name)
                await browser._select_pressed(entry, browser.buttons[entry.identity])
                assert app.cloud_busy and app.transfer_busy and app._crypt_cancel is cancel, app.transfer_message
                assert not cancel.is_set()
            await tap('Local note.txt')
            local_editor = app.private_sessions.active
            assert local_editor.crypt_text.value == 'Unrelated local file'
            local_editor.crypt_text.value = 'Unsaved local draft while pulling'
            # This case checks file access during a transfer. Keep page-sized
            # bitmap assertions independent of automatic wide-screen spreads.
            with patch.dict(app.preferences.values, comic_layout='single'):
                await tap('Local comic.cbz')
                assert app.reader_manager().active.book_reader.pages == ['page2.webp', 'page10.webp']
                view = app.reader_manager().active.book_content.children[0]
                canvas = view.canvases[0] if hasattr(view, 'canvases') else view
                assert (canvas.image.width, canvas.image.height) == (2, 3)
                await app.next_book_page()
                assert app.reader_manager().active.book_record['position'] == 1
            await tap('Local note.txt')
            assert app.private_sessions.active is local_editor
            assert local_editor.crypt_text.value == 'Unsaved local draft while pulling'
            assert comic.read_bytes() == original_comic
            assert (local / 'Local note.txt').read_text() == 'Unrelated local file'
            # Close the synthetic draft to keep later crypt fixtures isolated.
            assert app.private_sessions.close(local_editor.session.id, discard=True)
            assert app._crypt_cancel is cancel
            app.show_documents()
            app.editor.value = 'Ordinary draft during a native pull\n'
            assert app.checkpoint()
            await app.open_book(comic_key)
            await app.previous_book_page()
            await app.next_book_page()
            reader = app.reader_manager().active
            assert reader.book_reader is not None and reader.book_record['position'] == 1
            release.set()
            assert await task, app.transfer_message
            assert app.native_host.state.destination == 'documents'
            assert app.reader_manager().active is reader
            assert app.editor.value == 'Ordinary draft during a native pull\n'
        finally:
            release.set()
            await task
    store = app.mirror_store()
    job = next(job for job in store.jobs.values() if job['remote'] == 'Fixture')
    note = store.target(job) / 'fixture.txt'
    assert note.read_text() == 'Native rclone fixture\n'
    note.write_text('Edited in Local\n')
    from .review_checks import approve_transfer
    app.start_mirror_review(job['id'])
    await approve_transfer(app)
    from .transfer_fixtures import remote_files
    assert (await remote_files(client, job, 'fixture.txt'))['fixture.txt'] == note.read_bytes()
    assert app.transfer_progress.value == 100
    app.editor.value = original


async def exercise_crypt_mirror(app, fixture):
    from pathlib import Path
    source = fixture['copies']['note.md']
    client = app.cloud_client
    remote = source['record']['remote']
    info = client.request('mirror_info', remote=remote, path='mobile-mirror-fixture')
    mapped = client.request('crypt_path', remote=remote, path='mobile-mirror-fixture/note.md')['path']
    from .transfer_fixtures import seed_ciphertext
    await seed_ciphertext(client, remote, info, mapped, app.crypt_copies.root / source['key'] / 'data')
    store = app.mirror_store()
    assert await app.run_mirror_work(lambda client, cancel, progress:
        store.create(client, remote, 'mobile-mirror-fixture', cancelled=cancel, progress=progress), 'create'), app.transfer_message
    job = next(job for job in store.jobs.values() if job['remote'] == remote)
    assert job['crypt']
    assert b'mobile-mirror-fixture' not in store.path.read_bytes()
    assert b'note.md' not in store.path.read_bytes()
    assert await app.open_mirror_copy(job['id']), app.file_status.value
    row = next(row for row in app.file_rows.values() if Path(row['path']).name == 'note.md')
    app.browser_file_selected(row)
    await app.read_managed_file()
    assert (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None) is not None and (app.provider_sessions().active.crypt_reader if app.provider_sessions().active else None).editable
    app.provider_sessions().active.crypt_text.value = '# Edited in LocalCrypt\n'
    await app.save_crypt()
    assert not app.private_dirty()
    from .review_checks import approve_transfer
    app.start_mirror_review(job['id'])
    await approve_transfer(app)
    assert b'Edited in LocalCrypt' not in store.path.read_bytes()
    target = store.target(job) / Path(mapped).name
    assert b'Edited in LocalCrypt' not in target.read_bytes()
    # A real throttled embedded download must not monopolize local decryption.
    # Inject only its production bandwidth option; do not replace native I/O.
    from features.rclone.mobile.file_resources import CryptFiles
    provider = CryptFiles(app.private_root / 'LocalCryptFolders', client, remote, namespace=job['identity'])
    from io import BytesIO
    library_folder = 'mobile-mirror-fixture/Concurrent library'
    await asyncio.to_thread(provider.mkdir, library_folder)
    await asyncio.to_thread(provider.create_file, 'mobile-mirror-fixture/remoteConfig.ini',
        BytesIO(b'[LogisticsComics]\nlibraries=Concurrent library\n'))
    await asyncio.to_thread(provider.create_file, library_folder + '/library-note.md',
        BytesIO(b'# Library during download\n'))
    app.start_mirror_review(job['id'])
    await approve_transfer(app)
    payload = 'mobile-mirror-fixture/download-probe.bin'
    local_probe = app.private_root / 'LocalFiles' / 'download-probe.bin'
    with local_probe.open('wb') as output:
        # At the real bridge's minimum 1 MiB/s limit, the old 32 MiB
        # fixture could finish while a cold hosted emulator built the reader
        # widgets. Keep native I/O active across all browsing assertions; the
        # test cancels it rather than waiting for this payload to finish.
        for _ in range(256):
            output.write(b'x' * (1024 * 1024))
    with local_probe.open('rb') as source:
        await asyncio.to_thread(provider.create_file, payload, source)
    local_probe.unlink()
    app.start_mirror_review(job['id'])
    await approve_transfer(app)
    provider._locate(payload).unlink()
    assert app.clear_private_reader(discard=True)
    async def files_route():
        app.show_locations()
        entry = next(entry for entry in app.folder_picker_choices.values()
                     if entry['source'] == 'LocalCrypt' and entry.get('remote') == remote)
        app.show_picker_folder(entry)
        assert app.folder_browse_button.enabled
        assert await app.open_picker_folder(entry), app.folder_picker_status.text
        row = next(row for row in app.file_rows.values() if Path(row['path']).name == 'note.md')
        assert not any('.partial' in row['name'] for row in app.file_rows.values())
        app.browser_file_selected(row)
        await app.read_managed_file()

    async def documents_route():
        app.show_documents()
        drawer = app.adaptive.browser('documents')
        label = 'LocalCrypt: ' + remote + ' (pulled)'
        assert await drawer.show_main_browser(label, folder='mobile-mirror-fixture'), drawer.status.text
        assert await drawer.open_file({'path': 'mobile-mirror-fixture/note.md'}), drawer.status.text

    async def library_route():
        catalog = app.reader_manager().catalog
        await catalog.refresh_library_folders()
        await next(button for button in catalog.library_row_buttons if button.text == 'Concurrent library').on_press()
        assert app.file_path == library_folder and app.file_provider.private
        row = next(row for row in app.file_rows.values() if row['name'] == 'library-note.md')
        app.browser_file_selected(row)
        await app.read_managed_file()

    async def documents_library_route():
        drawer = app.adaptive.browser('documents')
        drawer.refresh_menu()
        await next(button for button in drawer.library_buttons if button.text == 'Concurrent library').on_press()
        assert drawer.folder == library_folder and drawer.provider.private, drawer.status.text
        assert await drawer.open_file({'path': library_folder + '/library-note.md'}), drawer.status.text

    request = client.request
    active_run = []
    def throttled(action, **values):
        if action == 'mirror_sync' and not values.get('push'):
            values['bw_limit'] = 1
            active_run[:] = [values['run']]
        return request(action, **values)

    # Each real route gets its own transfer lifetime. A single download must
    # not be expected to outlast four unrelated cold native layout sequences.
    routes = ((files_route, '# Edited in LocalCrypt\n'),
              (documents_route, '# Edited in LocalCrypt\n'),
              (library_route, '# Library during download\n'),
              (documents_library_route, '# Library during download\n'))
    from time import monotonic
    probe = provider._physical(payload)
    for route, expected in routes:
        active_run.clear()
        with patch.object(client, 'request', side_effect=throttled):
            task = asyncio.create_task(app.run_mirror_work(lambda client, cancel, progress:
                store.pull(job['id'], client, cancelled=cancel, progress=progress), 'pull'))
            try:
                for _ in range(300):
                    await asyncio.sleep(.05)
                    if task.done():
                        raise AssertionError('Download ended before concurrent reading could be tested: ' + app.transfer_message)
                    state = request('mirror_progress', run=active_run[0]) if active_run else dict(done=0, total=0)
                    if state['done'] > 0 and state['total'] > state['done']:
                        break
                else:
                    raise AssertionError('Throttled native download did not report live progress')
                cancel = app._crypt_cancel
                started_at = monotonic()
                print('LOGISTICS_NATIVE_TRANSFER_ROUTE=' + route.__name__, flush=True)
                await route()
                print('LOGISTICS_NATIVE_TRANSFER_ROUTE_SECONDS=' + str(round(monotonic() - started_at, 3)), flush=True)
                assert app.private_sessions.active.crypt_reader.text == expected
                assert not task.done(), route.__name__ + ' waited for the download'
                assert app.cloud_busy and app.transfer_busy and app._crypt_cancel is cancel
                assert not cancel.is_set()
                assert not await app.run_mirror_work(lambda *args: (_ for _ in ()).throw(
                    AssertionError('A second transfer was started')), 'pull')
                app.cancel_mirror_transfer()
                assert not await task, app.transfer_message
                assert app.private_sessions.active.crypt_reader.text == expected
            finally:
                if not task.done():
                    app.cancel_mirror_transfer()
                    await task
                # The native writer has retired; remove only this test probe's
                # abandoned bytes so the next route starts a fresh download.
                probe.unlink(missing_ok=True)
                for partial in probe.parent.glob(probe.name + '.*.partial'):
                    partial.unlink()
    # Retire the synthetic remote object through a real reviewed native push.
    # Later remote observations must not repeatedly copy this large probe.
    app.start_mirror_review(job['id'])
    await approve_transfer(app)
