"""Real native controls for complete, cancelled and early transfer reviews."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path

from .transfer_fixtures import remote_files
from threading import Event
from unittest.mock import AsyncMock, patch


def rendered_review(view):
    return (view is not None and not view.closed and view.ready and view.revision > 0
            and view.delivered_revision == view.revision)


async def press_review(view, action, *, timeout=30):
    """Click the rendered native WebView action, including its revision bridge."""
    selector = {'approve': '#approve', 'early': '#early'}[action]
    script = ('(() => { const button = document.querySelector(' + json.dumps(selector)
              + '); if (!button || button.disabled || !button.getClientRects().length) return false; '
              + 'button.click(); return true; })()')
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if rendered_review(view) and await view.web.evaluate_javascript(script):
            return
        await asyncio.sleep(.05)
    raise AssertionError('Native review action was not rendered/enabled: ' + action)


def cancel_review(app):
    """Review cancellation belongs to the platform Back control."""
    from commonUtils.runtime.platform import get_os, OS
    if get_os() is OS.IOS:
        navigation = app.native_host.adapter.navigation[app.native_host.destinations.index('files')]
        navigation.popViewControllerAnimated(True)
    elif get_os() is OS.ANDROID:
        app.native_host.adapter.impl._native_activity.getOnBackPressedDispatcher().onBackPressed()
    else:
        raise AssertionError('Review cancellation requires a real mobile navigation backend')


async def completed_review(app, *, timeout=30):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        view = getattr(app, '_transfer_review_view', None)
        if rendered_review(view) and view.model.get('can_confirm'):
            return view
        if app.transfer_task.done():
            raise AssertionError('Review exited before confirmation: ' + app.cloud_status.value)
        await asyncio.sleep(.05)
    raise AssertionError('Native review never completed: ' + app.cloud_status.value)


async def approve_transfer(app, *, timeout=60):
    view = await completed_review(app)
    # A second completed scan can legitimately ask for confirmation again.
    # Follow that visible full-review flow; never use the incomplete-review action.
    deadline = asyncio.get_running_loop().time() + timeout
    confirmations = 0
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
        await press_review(view, 'approve')
        while not app.transfer_task.done():
            current = getattr(app, '_transfer_review_view', None)
            if (rendered_review(current) and current.model.get('can_confirm')
                    and current.model.get('notice', '').startswith('Files changed')):
                assert confirmations < 3, 'Native review kept changing after three fresh confirmations'
                confirmations += 1
                await press_review(current, 'approve')
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                phase = current.model.get('notice', '') if current is not None else app.transfer_message
                raise AssertionError('Native transfer timed out: ' + phase)
            await asyncio.wait([app.transfer_task], timeout=min(.1, remaining))
    assert await app.transfer_task, app.transfer_message


async def wait_for_held_review(app, held, *, timeout=30):
    """Do not click the early action until the native result is actually held."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        view = getattr(app, '_transfer_review_view', None)
        if (rendered_review(view) and not view.model.get('complete')
                and view.model.get('can_early') and held.is_set()):
            return view
        if app.transfer_task.done():
            raise AssertionError('Native held review exited before its result was held: ' + app.transfer_message)
        await asyncio.sleep(.05)
    raise AssertionError('Native comparison never reached the held-result fixture: ' + app.transfer_message)


def save_transfer_settings(app):
    """Follow native settings even when adaptive layout moves its actions."""
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
    pending = [app.body]
    while pending:
        candidate = pending.pop()
        if getattr(candidate, 'text', None) == 'Save settings':
            candidate.on_press()
            break
        pending.extend(list(getattr(candidate, 'children', ()) or ()))
        pending.extend(getattr(candidate, '_ios_toolbar_buttons', ()))
    else:
        raise AssertionError('Native transfer settings save button was not presented')


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
        return await completed_review(app)
    async def finish(phase='review'):
        done, _ = await asyncio.wait([app.transfer_task], timeout=30)
        if not done:
            view = getattr(app, '_transfer_review_view', None)
            status = view.model.get('notice', '') if view is not None else 'review closed'
            details = str(view.model.get('rows', ())) if view is not None else ''
            raise AssertionError('Native reviewed transfer did not retire: '
                                 + phase + '; status=' + status + '; progress='
                                 + app.transfer_message + '; details=' + details[:2000])
        return await app.transfer_task
    before = store.path.read_bytes()
    app.start_mirror_pull(key)
    view = await ready()
    assert view.model['operation'] == 'Pull'
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=False)) as declined:
        await press_review(view, 'approve')
        for _ in range(100):
            if declined.await_count:
                break
            await asyncio.sleep(.05)
        assert declined.await_count == 1
    assert store.path.read_bytes() == before
    cancel_review(app)
    assert not await finish()
    app.start_mirror_pull(key)
    view = await ready()
    assert view.model['complete']
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
        await press_review(view, 'approve')
        assert await finish(), app.transfer_message
    copies = ManagedCopies(provider)
    reader = await asyncio.to_thread(copies.open, logical)
    updated = await asyncio.to_thread(copies.save, reader, '# Native shared review writeback\n')
    assert updated.text == '# Native shared review writeback\n'
    app.start_mirror_review(key)
    view = await ready()
    assert view.model['operation'] == 'Push'
    assert ('replace', 'note.md') in view.model['rows'], view.model['rows']
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
        await press_review(view, 'approve')
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
                await press_review(view, 'early')
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
    assert ('cleanup', '.DS_Store') in view.model['rows'], view.model['rows']
    assert ('delete', '.DS_Store') in view.model['rows'], view.model['rows']
    assert physical_junk.exists(), 'Review removed local generated junk'
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
        await press_review(view, 'approve')
        assert await finish(), app.transfer_message
    assert not physical_junk.exists()
    leaf = Path(provider.mapping(junk)).name
    assert (await remote_files(client, job, leaf))[leaf] is None

    # Save actual native settings controls, then infer an ordinary local folder
    # beneath the selected remote, including a followed file link and exclusions.
    from features.rclone.transfers.transfer_options import TransferOptions, save_options
    save_transfer_settings(app)
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
    assert ('add', 'linked.txt') in view.model['rows']
    assert all(path != 'excluded.skip' for _, path in view.model['rows'])
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
