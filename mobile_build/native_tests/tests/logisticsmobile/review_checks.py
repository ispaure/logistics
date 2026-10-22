"""Real native controls for complete, cancelled and early transfer reviews."""
import asyncio
from pathlib import Path

from .transfer_fixtures import remote_files
from threading import Event
from unittest.mock import AsyncMock, patch


async def approve_transfer(app, *, timeout=60):
    for _ in range(600):
        view = getattr(app, '_transfer_review_view', None)
        if view is not None and view.children[-1].children[1].enabled:
            break
        if app.transfer_task.done():
            raise AssertionError('Review exited before confirmation: ' + app.cloud_status.value)
        await asyncio.sleep(.05)
    else:
        raise AssertionError('Native review never completed: ' + app.cloud_status.value)
    # A second completed scan can legitimately ask for confirmation again.
    # Follow that visible full-review flow; never use the incomplete-review action.
    deadline = asyncio.get_running_loop().time() + timeout
    confirmations = 0
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
        await view.children[-1].children[1].on_press()
        while not app.transfer_task.done():
            current = getattr(app, '_transfer_review_view', None)
            if (current is not None and current.children[-1].children[1].enabled
                    and current.children[2].text.startswith('Files changed or could not be checked.')):
                assert confirmations < 3, 'Native review kept changing after three fresh confirmations'
                confirmations += 1
                await current.children[-1].children[1].on_press()
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                phase = current.children[2].text if current is not None else app.transfer_message
                raise AssertionError('Native transfer timed out: ' + phase)
            await asyncio.wait([app.transfer_task], timeout=min(.1, remaining))
    assert await app.transfer_task, app.transfer_message


async def wait_for_held_review(app, held, *, timeout=30):
    """Do not click the early action until the native result is actually held."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        view = getattr(app, '_transfer_review_view', None)
        if view is not None and 'incomplete' in view.children[3].value and held.is_set():
            return view
        if app.transfer_task.done():
            raise AssertionError('Native held review exited before its result was held: ' + app.transfer_message)
        await asyncio.sleep(.05)
    raise AssertionError('Native comparison never reached the held-result fixture: ' + app.transfer_message)


async def exercise_reviews(app):
    from features.rclone.localcrypt.mobile.resources import CryptFiles, ManagedCopies
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
    async def finish(phase='review'):
        done, _ = await asyncio.wait([app.transfer_task], timeout=30)
        if not done:
            view = getattr(app, '_transfer_review_view', None)
            status = view.children[2].text if view is not None else 'review closed'
            details = view.children[3].value if view is not None else ''
            raise AssertionError('Native reviewed transfer did not retire: '
                                 + phase + '; status=' + status + '; progress='
                                 + app.transfer_message + '; details=' + details[:2000])
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
    released, returned, held = Event(), Event(), Event()
    request, cancel = client.request, client.cancel
    def delayed(action, **values):
        result = request(action, **values)
        if action == 'mirror_review':
            held.set()
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
            view = await wait_for_held_review(app, held)
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
    from features.rclone.transfers.transfer_options import TransferOptions, save_options
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
    # Fresh validation can ask for another completed review. Follow the same
    # bounded full-confirmation flow used by the other native transfer checks.
    await approve_transfer(app)
    inferred = next(item for item in store.jobs.values() if item['target'] == folder)
    assert inferred['prefix'] == folder and inferred['remote'] == job['remote'] and not inferred['crypt']
    observed = await remote_files(client, inferred, 'linked.txt', 'excluded.skip')
    assert observed['linked.txt'] == target.read_bytes()
    assert observed['excluded.skip'] is None
    assert (local / 'excluded.skip').exists()
    save_options(app.private_root / 'transfer-options.json', TransferOptions())
