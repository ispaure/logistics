"""Native managed folders, background document use and verified writeback."""
import asyncio
from hashlib import sha256
from threading import Event
from unittest.mock import patch
from uuid import uuid4


async def exercise_mirrors(app, comic_key):
    started, release = Event(), Event()
    client = app.cloud_client
    request = client.request
    def gated(action, **values):
        if action == 'mirror_read' and not started.is_set():
            started.set()
            if not release.wait(30):
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
    app.body.children[0].children[2].on_press()
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
    assert await app.open_mirror_copy(job['id'])
    row = next(row for row in app.file_rows.values() if Path(row['path']).name == 'note.md')
    app.browser_file_selected(row)
    await app.read_managed_file()
    assert app.crypt_reader is not None and app.crypt_reader.editable
    app.crypt_text.value = '# Edited in LocalCrypt\n'
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
