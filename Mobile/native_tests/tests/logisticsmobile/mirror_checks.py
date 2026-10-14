"""Native managed folders, background document use and verified writeback."""
import asyncio
from hashlib import sha256
from threading import Event
from unittest.mock import patch, AsyncMock
from uuid import uuid4


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
            from pathlib import Path
            local = app.private_root / 'LocalFiles' / 'Browse during pull'
            local.mkdir(parents=True, exist_ok=True)
            (local / 'Local note.txt').write_text('Unrelated local file')
            cancel = app._crypt_cancel
            app.show_locations()
            assert 'Browse during pull' in app.folder_picker_choices
            assert 'Fixture' in app.folder_picker_choices
            app.folder_choice.value = 'Fixture'
            assert not app.folder_browse_button.enabled
            assert not await app.open_picker_folder(app.folder_picker_selected)
            app.show_locations()
            app.folder_choice.value = 'Browse during pull'
            assert app.folder_browse_button.enabled
            await app.folder_browse_button.on_press()
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
            await tap('Local comic.cbz')
            assert app.reader_manager().active.book_reader.pages == ['page2.webp', 'page10.webp']
            assert (app.reader_manager().active.book_content.children[0].image.width, app.reader_manager().active.book_content.children[0].image.height) == (2, 3)
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
    assert await app.run_mirror_work(lambda client, cancel, progress:
        store.push_plan(job['id'], client, cancelled=cancel, progress=progress), 'review')
    plan = app.mirror_push_plan
    assert len(plan['writes']) == 1
    app.show_mirror_push_review()
    assert 'replacement' in app.body.children[0].children[1].text
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)) as dialog:
        await app.body.children[0].children[2].on_press()
        assert dialog.await_count == 1
    assert await app.transfer_task, app.transfer_message
    assert client.request('mirror_stat', remote='Fixture', path='logistics-native-check/fixture.txt',
                          identity=job['identity']) == sha256(note.read_bytes()).hexdigest()
    assert app.transfer_progress.value == 100
    app.editor.value = original


async def exercise_crypt_mirror(app, fixture):
    from pathlib import Path
    source = fixture['copies']['note.md']
    client = app.cloud_client
    remote = source['record']['remote']
    info = client.request('mirror_info', remote=remote, path='mobile-mirror-fixture')
    mapped = client.request('crypt_path', remote=remote, path='mobile-mirror-fixture/note.md')['path']
    with (app.crypt_copies.root / source['key'] / 'data').open('rb') as stream:
        client.request('mirror_write', remote=remote, path=mapped, identity=info['identity'], expected='',
                       run=uuid4().hex, fd=stream.fileno())
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
    assert await app.run_mirror_work(lambda client, cancel, progress:
        store.push_plan(job['id'], client, cancelled=cancel, progress=progress), 'review'), app.transfer_message
    plan = app.mirror_push_plan
    assert plan['writes']
    assert await app.run_mirror_work(lambda client, cancel, progress:
        store.push(plan, client, cancelled=cancel, progress=progress), 'push'), app.transfer_message
    assert b'Edited in LocalCrypt' not in store.path.read_bytes()
    target = store.target(job) / Path(mapped).name
    assert b'Edited in LocalCrypt' not in target.read_bytes()
