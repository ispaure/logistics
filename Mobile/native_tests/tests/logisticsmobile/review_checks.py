"""Real native controls for complete, cancelled and early transfer reviews."""
import asyncio
from pathlib import Path

from .transfer_fixtures import remote_files
from threading import Event
from unittest.mock import AsyncMock, patch


async def approve_transfer(app):
    for _ in range(600):
        view = getattr(app, '_transfer_review_view', None)
        if view is not None and view.children[-1].children[1].enabled:
            break
        if app.transfer_task.done():
            raise AssertionError('Review exited before confirmation: ' + app.cloud_status.value)
        await asyncio.sleep(.05)
    else:
        raise AssertionError('Native review never completed: ' + app.cloud_status.value)
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
        await view.children[-1].children[1].on_press()
    assert await asyncio.wait_for(app.transfer_task, timeout=30), app.transfer_message


async def exercise_reviews(app):
    from features.rclone.mobile.file_resources import CryptFiles, ManagedCopies
    store, client = app.mirror_store(), app.cloud_client
    job = next(job for job in store.jobs.values() if job['crypt'])
    key = job['id']
    provider = CryptFiles(app.private_root / 'LocalCryptFolders', client, job['remote'], namespace=job['identity'])
    logical = 'mobile-mirror-fixture/note.md'
    # Remove only this synthetic test's abandoned staging object, if retained.
    for partial in store.target(job).glob('*.partial'):
        partial.unlink()
    async def ready():
        for _ in range(600):
            view = getattr(app, '_transfer_review_view', None)
            if view is not None and view.children[-1].children[1].enabled:
                return view
            if app.transfer_task.done():
                raise AssertionError('Review exited before confirmation: ' + app.cloud_status.value)
            await asyncio.sleep(.05)
        raise AssertionError('Native review never completed: ' + app.cloud_status.value)
    async def finish():
        done, _ = await asyncio.wait([app.transfer_task], timeout=30)
        assert done, 'Native reviewed transfer did not retire'
        return await app.transfer_task
    before = store.path.read_bytes()
    app.start_mirror_pull(key)
    view = await ready()
    assert view.children[0].text == 'Review Pull'
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=False)):
        await view.children[-1].children[1].on_press()
    assert store.path.read_bytes() == before
    view.children[-1].children[0].on_press()
    assert not await finish()
    app.start_mirror_pull(key)
    view = await ready()
    assert 'Review complete' in view.children[3].value
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
        await view.children[-1].children[1].on_press()
    assert await finish(), app.transfer_message
    copies = ManagedCopies(provider)
    reader = await asyncio.to_thread(copies.open, logical)
    updated = await asyncio.to_thread(copies.save, reader, '# Native shared review writeback\n')
    assert updated.text == '# Native shared review writeback\n'
    app.start_mirror_review(key)
    view = await ready()
    assert view.children[0].text == 'Review Push'
    assert 'Replace: note.md' in view.children[3].value, view.children[3].value
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
        await view.children[-1].children[1].on_press()
    assert await finish(), app.transfer_message
    physical = provider._locate(logical)
    leaf = Path(provider.mapping(logical)).name
    assert (await remote_files(client, job, leaf))[leaf] == physical.read_bytes()
    # Hold delivery of an actual native comparison result so the early action
    # can be exercised deterministically. Cancellation must retire it first.
    released, returned = Event(), Event()
    request, cancel = client.request, client.cancel
    def delayed(action, **values):
        result = request(action, **values)
        if action == 'mirror_review':
            if not released.wait(30):
                raise RuntimeError('Native review fixture was not released')
            returned.set()
        if action == 'mirror_sync':
            assert returned.is_set(), 'Transfer started before comparison retired'
        return result
    def stop():
        released.set()
        cancel()
    count = len(store.jobs)
    with patch.object(client, 'request', side_effect=delayed), patch.object(client, 'cancel', side_effect=stop):
        app.begin_transfer_review(remote=job['remote'], folder='mobile-mirror-fixture', storage='Local')
        try:
            for _ in range(600):
                view = getattr(app, '_transfer_review_view', None)
                if view is not None and 'incomplete' in view.children[3].value:
                    break
                await asyncio.sleep(.05)
            assert len(store.jobs) == count, 'Review published a mapping before approval'
            with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
                await view.children[-2].on_press()
            assert await finish(), app.transfer_message
            assert len(store.jobs) == count + 1
        finally:
            released.set()
    # A crypt cleanup must appear as both local cleanup and remote deletion
    # before either side changes, and then authenticate before actual removal.
    junk = 'mobile-mirror-fixture/.DS_Store'
    # Reuse valid ciphertext produced by the native editor above. The text-save
    # bridge intentionally refuses creating a binary .DS_Store by text input.
    physical_junk = provider._physical(junk)
    physical_junk.write_bytes(physical.read_bytes())
    await asyncio.to_thread(store.sync, job, client, push=True,
                           cancelled=lambda: False, progress=lambda **kw: None)
    app.start_mirror_review(key)
    view = await ready()
    assert 'Cleanup: .DS_Store' in view.children[3].value, view.children[3].value
    assert 'Delete: .DS_Store' in view.children[3].value, view.children[3].value
    assert physical_junk.exists(), 'Review removed local generated junk'
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
        await view.children[-1].children[1].on_press()
    assert await finish(), app.transfer_message
    assert not physical_junk.exists()
    leaf = Path(provider.mapping(junk)).name
    assert (await remote_files(client, job, leaf))[leaf] is None

    # Save actual native settings controls, then infer an ordinary local folder
    # beneath the selected remote, including a followed file link and exclusions.
    from features.rclone.transfer_options import TransferOptions, save_options
    app.show_transfer_options()
    pending = [app.body]
    settings = None
    while pending:
        candidate = pending.pop()
        children = list(getattr(candidate, 'children', ()) or ())
        if children and getattr(children[0], 'text', None) == 'Transfer settings':
            settings = candidate
            break
        pending.extend(children)
    assert settings is not None, 'Native transfer settings were not presented'
    settings.children[1].value = True
    settings.children[3].value = '1'
    settings.children[5].value += '\n*.skip'
    settings.children[-2].on_press()
    assert app.transfer_options().track_renames and app.transfer_options().bw_limit == 1
    folder = 'native-options-source'
    local = app.private_root / 'LocalFiles' / folder
    local.mkdir()
    target = app.private_root / 'native-file-link-target.txt'
    target.write_bytes(b'native ordinary linked contents')
    (local / 'linked.txt').symlink_to(target)
    (local / 'excluded.skip').write_bytes(b'keep local excluded bytes')
    app.begin_transfer_review(push=True, local_folder=folder, remote=job['remote'], specific=True)
    view = await ready()
    assert 'Add: linked.txt' in view.children[3].value
    assert 'excluded.skip' not in view.children[3].value
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
        await view.children[-1].children[1].on_press()
    assert await finish(), app.transfer_message
    inferred = next(item for item in store.jobs.values() if item['target'] == folder)
    assert inferred['prefix'] == folder and inferred['remote'] == job['remote'] and not inferred['crypt']
    observed = await remote_files(client, inferred, 'linked.txt', 'excluded.skip')
    assert observed['linked.txt'] == target.read_bytes()
    assert observed['excluded.skip'] is None
    assert (local / 'excluded.skip').exists()
    save_options(app.private_root / 'transfer-options.json', TransferOptions())
