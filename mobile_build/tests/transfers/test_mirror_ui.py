import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import AsyncMock, patch
from mobile.app import LogisticsMobile
from mobile_build.tests.transfers.test_mirror_jobs import MirrorClient


class ProgressDeliveryTests(unittest.TestCase):
    def test_worker_bursts_queue_one_callback_with_latest_values(self):
        from threading import Thread
        from types import SimpleNamespace
        from unittest.mock import Mock
        from features.rclone.transfers.mobile.ui import coalesced_progress
        queued, published = [], Mock()
        loop = SimpleNamespace(call_soon_threadsafe=lambda callback: queued.append(callback))
        progress = coalesced_progress(loop, published)
        def worker(start):
            for done in range(start, start + 100):
                progress(done=done)
        workers = [Thread(target=worker, args=(start,)) for start in (0, 100, 200, 300)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        progress(done=400)
        self.assertEqual(len(queued), 1)
        published.assert_not_called()
        queued.pop(0)()
        published.assert_called_once_with({'done': 400})

    def test_arrivals_during_render_queue_one_successor_without_blocking_worker(self):
        from threading import Thread
        from types import SimpleNamespace
        from features.rclone.transfers.mobile.ui import coalesced_progress
        queued, published = [], []
        loop = SimpleNamespace(call_soon_threadsafe=lambda callback: queued.append(callback))
        def publish(values):
            published.append(values['done'])
            if values['done'] == 0:
                def worker():
                    for done in range(1, 101):
                        progress(done=done)
                thread = Thread(target=worker, daemon=True)
                thread.start()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive(), 'Native rendering held the progress worker lock')
        progress = coalesced_progress(loop, publish)
        progress(done=0)
        queued.pop(0)()
        self.assertEqual(published, [0])
        self.assertEqual(len(queued), 1)
        queued.pop(0)()
        self.assertEqual(published, [0, 100])
        self.assertFalse(queued)

    def test_old_queued_progress_cannot_overwrite_terminal_or_new_transfer(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from features.rclone.transfers.mobile.ui import MirrorUI, coalesced_progress
        queued = []
        loop = SimpleNamespace(call_soon_threadsafe=lambda callback: queued.append(callback))
        bar = SimpleNamespace(max=100, value=100, start=Mock(), stop=Mock())
        app = SimpleNamespace(active_host=True, transfer_epoch=1, transfer_busy=True,
            transfer_message='Finished', transfer_notice=SimpleNamespace(text='Finished'),
            cloud_status=SimpleNamespace(value='Finished'), transfer_progress=bar,
            cloud_transfer_progress=None, refresh_transfer_status=Mock())
        values = dict(phase='Transferring', files=1, done=20, total=100)
        old_progress = coalesced_progress(loop, lambda values: MirrorUI.publish_mirror_progress(app, 1, values))
        old_progress(**values)
        app.transfer_epoch, app.transfer_busy = 2, False
        queued.pop(0)()
        self.assertEqual(app.transfer_notice.text, 'Finished')
        self.assertEqual(bar.value, 100)
        app.refresh_transfer_status.assert_not_called()
        old_progress(**dict(values, done=50))
        app.transfer_epoch, app.transfer_busy = 3, True
        new_progress = coalesced_progress(loop, lambda values: MirrorUI.publish_mirror_progress(app, 3, values))
        new_progress(**dict(values, done=30))
        for callback in queued:
            callback()
        self.assertEqual(bar.value, 30)
        app.refresh_transfer_status.assert_called_once()


async def drive_review(app, *, declined=False, early=False):
    for _ in range(200):
        view = getattr(app, '_transfer_review_view', None)
        if view is not None and (early or view.children[-1].children[1].enabled):
            break
        await asyncio.sleep(.01)
    else:
        raise AssertionError('Review was not ready: ' + str(getattr(app, 'cloud_status', None)))
    button = view.children[-2] if early else view.children[-1].children[1]
    await button.on_press()
    if declined:
        view.children[-1].children[0].on_press()
    return await asyncio.wait_for(app.transfer_task, timeout=5)


class MirrorUITests(unittest.TestCase):
    def test_transfer_details_keep_review_endpoints_during_work_and_after_reopening(self):
        from features.rclone.mobile.messages import import_hint
        class Client(MirrorClient):
            def crypt_remotes(self): return ['Secret']
            def cancel(self): pass
        for crypt, push, new in ((False, False, True), (False, True, False),
                                 (True, False, False), (True, True, False)):
            with self.subTest(crypt=crypt, push=push, new=new), TemporaryDirectory() as directory:
                LogisticsMobile.storage_root = Path(directory)
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                try:
                    app.cloud_client = Client()
                    app.show_cloud(present=False)
                    remote, storage = ('Secret', 'LocalCrypt') if crypt else ('Remote', 'Local')
                    store = app.mirror_store()
                    job = store.prepare_review(app.cloud_client, remote, 'folder', storage=storage)
                    if not new:
                        job, _ = store.create(app.cloud_client, remote, 'folder', storage=storage)
                    prefix = job['prefix'] if not new else 'folder'
                    online = remote + ':' + prefix
                    local = storage + '/' + job['target'] + ('/' + prefix if crypt else '')
                    source, destination = (local, online) if push else (online, local)
                    expected = import_hint(f'From: {source}\nTo: {destination}')
                    shown = []
                    original = app.show_transfers
                    def show(*args, **kwargs):
                        original(*args, **kwargs)
                        if getattr(app, 'transfer_endpoints', None):
                            self.assertEqual(app.transfer_view.content.children[1].text, expected)
                            shown.append(app.transfer_busy)
                    async def exercise():
                        with patch.object(app, 'show_transfers', side_effect=show), patch.object(
                                app.main_window, 'dialog', new=AsyncMock(return_value=True)):
                            app.begin_transfer_review(None if new else job['id'], push=push,
                                                      remote=remote, folder='folder', storage=storage)
                            self.assertTrue(await drive_review(app))
                            app.show_locations()
                            app.show_transfers()
                        self.assertIn(True, shown)
                        self.assertIn(False, shown)
                    app.loop.run_until_complete(exercise())
                finally:
                    app.main_window.close()
                    app.loop.close()
                    LogisticsMobile.storage_root = None

    def test_native_review_replaces_partial_snapshots_and_publishes_final_cleanup(self):
        from features.rclone.transfers.review import ReviewScan
        from features.rclone.transfers.mobile.plan import native_scanner
        polled, release, retrying = Event(), Event(), Event()
        class Client:
            def request(self, action, **values):
                if action == 'mirror_review_progress':
                    polled.set()
                    return dict(changes=[] if retrying.is_set() else [['delete', 'stale.txt']])
                if action == 'mirror_review':
                    if not release.wait(5):
                        raise RuntimeError('Comparison fixture was not released')
                    return dict(changes=[['add', 'current.txt']], fingerprint='current')
                if action == 'mirror_review_clear':
                    return True
                raise ValueError(action)
        with TemporaryDirectory() as folder:
            scan = ReviewScan(native_scanner(Client(), dict(remote='Cloud', prefix='', identity='bound',
                crypt=False), Path(folder), push=True, cleanup_plan=lambda cancelled: {'junk': ('junk', 'v1')}))
            try:
                self.assertTrue(polled.wait(2))
                for _ in range(100):
                    if ('delete', 'stale.txt') in scan.snapshot().changes:
                        break
                    Event().wait(.01)
                self.assertIn(('delete', 'stale.txt'), scan.snapshot().changes)
                retrying.set()
                for _ in range(200):
                    if not scan.snapshot().changes:
                        break
                    Event().wait(.01)
                self.assertEqual(scan.snapshot().changes, ())
                self.assertFalse(scan.snapshot().complete)
                release.set()
                self.assertTrue(scan.retired.wait(2))
                result = scan.snapshot()
                self.assertTrue(result.complete, result.error)
                self.assertEqual(set(result.changes), {('add', 'current.txt'), ('cleanup', 'junk')})
            finally:
                release.set()
                scan.stop()
                scan.retired.wait(2)

    def test_options_are_saved_and_frozen_across_review_recheck_and_execution(self):
        class Client(MirrorClient):
            def crypt_remotes(self): return []
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            client = app.cloud_client = Client()
            app.show_cloud(present=False)
            store = app.mirror_store()
            job, _ = store.create(client, 'Remote', 'folder')
            from features.rclone.transfers.transfer_options import TransferOptions, save_options
            path = app.private_root / 'transfer-options.json'
            save_options(path, TransferOptions(track_renames=True, bw_limit=3, excludes=('*.skip',)))
            app.show_transfer_options()
            self.assertEqual(app.transfer_options().bw_limit, 3)
            async def accepted(dialog):
                save_options(path, TransferOptions(bw_limit=9, excludes=()))
                return True
            async def exercise():
                with patch.object(client, 'request', wraps=client.request) as request, patch.object(
                        app.main_window, 'dialog', new=AsyncMock(side_effect=accepted)):
                    app.start_mirror_review(job['id'])
                    self.assertTrue(await drive_review(app))
                calls = [call for call in request.call_args_list if call.args[0] in ('mirror_review', 'mirror_sync')]
                self.assertEqual(len(calls), 3)
                for call in calls:
                    self.assertEqual(call.kwargs['bw_limit'], 3)
                    self.assertTrue(call.kwargs['track_renames'])
                    self.assertEqual(call.kwargs['excludes'], ['*.skip'])
            app.loop.run_until_complete(exercise())

    def test_proceed_early_cancels_and_retires_comparison_before_execution(self):
        started, retired, release = Event(), Event(), Event()
        class Client(MirrorClient):
            def crypt_remotes(self): return []
            def cancel(self): release.set()
            def request(self, action, **values):
                if action == 'mirror_review':
                    started.set()
                    if not release.wait(5):
                        raise RuntimeError('Review fixture timed out')
                    retired.set()
                    raise ValueError('Comparison cancelled')
                if action == 'mirror_sync' and started.is_set():
                    assert retired.is_set(), 'Transfer started before comparison retired'
                return super().request(action, **values)
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            client = app.cloud_client = Client()
            app.show_cloud(present=False)
            job, _ = app.mirror_store().create(client, 'Remote', 'folder')
            async def exercise():
                with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)) as dialog:
                    app.start_mirror_pull(job['id'])
                    # Exercise cancellation of an in-flight comparison, rather
                    # than racing Proceed against its worker's first dispatch.
                    async with asyncio.timeout(5):
                        while not started.is_set():
                            await asyncio.sleep(.01)
                    self.assertTrue(await drive_review(app, early=True))
                    self.assertEqual(dialog.await_count, 1)
                self.assertTrue(retired.is_set())
            try:
                app.loop.run_until_complete(exercise())
            finally:
                release.set()

    def test_proceed_without_review_downloads_missing_local_and_localcrypt_content(self):
        import shutil
        class Client(MirrorClient):
            def crypt_remotes(self): return ['Secret']
            def cancel(self): pass
            def request(self, action, **values):
                if action == 'mirror_review':
                    raise FileNotFoundError('Synthetic incomplete comparison')
                return super().request(action, **values)
        for remote, storage, filename in (('Remote', 'Local', 'note.txt'),
                                          ('Secret', 'LocalCrypt', 'opaque-name')):
            for state in ('new', 'missing-file', 'missing-tree'):
                with self.subTest(storage=storage, state=state), TemporaryDirectory() as directory:
                    LogisticsMobile.storage_root = Path(directory)
                    app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                    try:
                        client = app.cloud_client = Client()
                        app.show_cloud(present=False)
                        store = app.mirror_store()
                        job = store.prepare_review(client, remote, 'folder', storage=storage)
                        target = store.target(job)
                        if state != 'new':
                            job, _ = store.create(client, remote, 'folder', storage=storage)
                            if state == 'missing-file':
                                (target / filename).unlink()
                            else:
                                shutil.rmtree(target)
                        async def exercise():
                            with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
                                app.begin_transfer_review(None if state == 'new' else job['id'],
                                    remote=remote, folder='folder', storage=storage)
                                self.assertTrue(await drive_review(app, early=True), app.transfer_message)
                        app.loop.run_until_complete(exercise())
                        self.assertEqual((target / filename).read_bytes(),
                                         client.data[job['prefix'] + '/' + filename])
                    finally:
                        app.main_window.close()
                        app.loop.close()
                        LogisticsMobile.storage_root = None

    def test_completed_review_detects_changes_after_confirmation(self):
        class Client(MirrorClient):
            def crypt_remotes(self): return []
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            client = app.cloud_client = Client()
            app.show_cloud(present=False)
            job, _ = app.mirror_store().create(client, 'Remote', 'folder')
            async def changed(dialog):
                client.data['folder/added-after-review.txt'] = b'new'
                return True
            async def exercise():
                with patch.object(app.main_window, 'dialog', new=AsyncMock(side_effect=changed)):
                    app.start_mirror_pull(job['id'])
                    for _ in range(200):
                        view = getattr(app, '_transfer_review_view', None)
                        if view is not None and view.children[-1].children[1].enabled:
                            break
                        await asyncio.sleep(.01)
                    await view.children[-1].children[1].on_press()
                    for _ in range(200):
                        if view.children[2].text.startswith('Files changed'):
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(view.children[2].text.startswith('Files changed'))
                    self.assertFalse((app.mirror_store().target(job) / 'added-after-review.txt').exists())
                    view.children[-1].children[0].on_press()
                    self.assertFalse(await app.transfer_task)
            app.loop.run_until_complete(exercise())

    def test_push_comparison_is_read_only_until_confirmed_and_bound_to_connection(self):
        class Client(MirrorClient):
            def restore(self, **kwargs): return []
            def crypt_remotes(self): return []
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            client = app.cloud_client = Client()
            app.show_cloud(present=False)
            store = app.mirror_store()
            job, _ = store.create(client, 'Remote', 'folder')
            (store.target(job) / 'note.txt').write_bytes(b'local edits')

            async def exercise():
                with patch.object(store, 'execute_push', wraps=store.execute_push) as execute:
                    for accepted in (False, True, False, True):
                        client.data['folder/note.txt'] = b'first'
                        before = execute.call_count
                        with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=accepted)) as dialog:
                            app.start_mirror_review(job['id'])
                            self.assertEqual(await drive_review(app, declined=not accepted), accepted)
                            self.assertEqual(dialog.await_count, 1)
                        self.assertEqual(execute.call_count, before + int(accepted))
                        self.assertEqual(client.data['folder/note.txt'], b'local edits' if accepted else b'first')
                    for change in ('connection', 'mapping'):
                        async def changed(dialog):
                            if change == 'connection':
                                client.generation += 1
                            else:
                                job['prefix'] = 'different-folder'
                            return True
                        execute.reset_mock()
                        with patch.object(app.main_window, 'dialog', new=AsyncMock(side_effect=changed)):
                            app.start_mirror_review(job['id'])
                            self.assertFalse(await drive_review(app))
                        execute.assert_not_called()
            app.loop.run_until_complete(exercise())

    def test_unchanged_progress_does_not_repeat_native_layout_updates(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from features.rclone.transfers.mobile.ui import MirrorUI
        bar = SimpleNamespace(max=100, value=0, start=Mock(), stop=Mock())
        app = SimpleNamespace(active_host=True, transfer_epoch=1, transfer_busy=True,
            transfer_message='', transfer_notice=SimpleNamespace(text=''),
            cloud_status=SimpleNamespace(value=''), transfer_progress=bar,
            cloud_transfer_progress=None, refresh_transfer_status=Mock())
        values = dict(phase='Transferring', files=1, done=20, total=100)
        MirrorUI.publish_mirror_progress(app, 1, values)
        self.assertEqual(bar.value, 20)
        for _ in range(10):
            MirrorUI.publish_mirror_progress(app, 1, values)
        app.refresh_transfer_status.assert_called_once()
        MirrorUI.publish_mirror_progress(app, 1, dict(values, done=50))
        self.assertEqual(bar.value, 50)
        # Both small counts round to the same MB text; percentage must advance.
        self.assertIn('0.00 / 0.00 MB', app.transfer_message)
        self.assertEqual(app.refresh_transfer_status.call_count, 2)
        self.assertEqual(app.cloud_status.value.replace(' · ', ' '), ' '.join(app.transfer_notice.text.splitlines()))
        self.assertIn('\n', app.transfer_notice.text)
        app.transfer_progress = replacement = SimpleNamespace(max=100, value=0)
        MirrorUI.publish_mirror_progress(app, 1, dict(values, done=50))
        self.assertEqual(replacement.value, 50)
        self.assertEqual(app.refresh_transfer_status.call_count, 3)

    def test_immersive_banner_hides_without_discarding_transfer_state(self):
        import toga
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        LogisticsMobile.storage_root = Path(directory.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(app.loop.close)
        self.addCleanup(app.main_window.close)
        view = toga.Box()
        app.transfer_busy = True
        app.transfer_notification = True
        app.register_transfer_status(view)
        self.assertIn(view.transfer_banner, view.children)
        view._comic_fullscreen = True
        app.refresh_transfer_status()
        self.assertNotIn(view.transfer_banner, view.children)
        self.assertTrue(app.transfer_busy and app.transfer_notification)
        view._comic_fullscreen = False
        app.refresh_transfer_status()
        self.assertIn(view.transfer_banner, view.children)

    def test_native_confirmation_cancel_accept_and_changed_connection(self):
        class Client(MirrorClient):
            def restore(self, **kwargs): return []
            def crypt_remotes(self): return []
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            app.cloud_client = client = Client()
            app.show_cloud(present=False)
            store = app.mirror_store()
            job, _ = store.create(client, 'Remote', 'folder')
            target = store.target(job) / 'note.txt'
            target.write_bytes(b'keep my local edit')
            async def exercise():
                with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=False)) as dialog:
                    app.start_mirror_pull(job['id'])
                    self.assertFalse(await drive_review(app, declined=True))
                    self.assertEqual(target.read_bytes(), b'keep my local edit')
                    self.assertEqual(dialog.await_count, 1)
                async def changed(dialog):
                    client.generation += 1
                    return True
                with patch.object(app.main_window, 'dialog', new=AsyncMock(side_effect=changed)):
                    app.start_mirror_pull(job['id'])
                    self.assertFalse(await drive_review(app))
                    self.assertEqual(target.read_bytes(), b'keep my local edit')
                with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
                    app.start_mirror_pull(job['id'])
                    self.assertTrue(await drive_review(app))
                    self.assertEqual(target.read_bytes(), b'first')
                target.write_bytes(b'confirmed push')
                with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=False)):
                    app.start_mirror_review(job['id'])
                    self.assertFalse(await drive_review(app, declined=True))
                    self.assertEqual(client.data['folder/note.txt'], b'first')
                with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)) as dialog:
                    app.start_mirror_review(job['id'])
                    self.assertTrue(await drive_review(app))
                    self.assertEqual(dialog.await_count, 1)
                    self.assertEqual(client.data['folder/note.txt'], b'confirmed push')
            try:
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_pull_continues_while_writing_without_taking_documents_away(self):
        started, release = Event(), Event()
        class Client(MirrorClient):
            def cancel(self):
                release.set()
            def restore(self, **kwargs):
                return []
            def crypt_remotes(self):
                return []
            def copy_remote_file(self, path, stream):
                started.set()
                if not release.wait(10):
                    raise RuntimeError('Pull fixture was not released')
                return super().copy_remote_file(path, stream)
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            client = app.cloud_client = Client()
            async def exercise():
                task = asyncio.create_task(app.run_mirror_work(
                    lambda client, cancel, progress: app.mirror_store().create(client, 'Remote', 'folder', cancelled=cancel, progress=progress), 'create'))
                try:
                    for _ in range(100):
                        if started.is_set():
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(started.is_set())
                    self.assertTrue(app.transfer_busy)
                    app.show_documents(destination='documents')
                    owner = app.editor_view
                    self.assertNotIn(owner.document_view.transfer_banner, owner.document_view.children)
                    app.editor.value = 'Draft during pull'
                    self.assertTrue(app.checkpoint())
                    release.set()
                    self.assertTrue(await task)
                    self.assertEqual(app.native_host.state.destination, 'documents')
                    self.assertIs(app.editor_view, owner)
                    self.assertEqual(app.editor.value, 'Draft during pull')
                    self.assertFalse(app.transfer_busy)
                    job = next(iter(app.mirror_store().jobs.values()))
                    self.assertEqual((app.mirror_store().target(job) / 'note.txt').read_bytes(), b'first')
                    self.assertEqual(client.data['folder/note.txt'], b'first')
                    self.assertNotIn(owner.document_view.transfer_banner, owner.document_view.children)
                    app.dismiss_transfer_status()
                    self.assertNotIn(owner.document_view.transfer_banner, owner.document_view.children)
                    self.assertEqual(app.editor.value, 'Draft during pull')
                    app.show_transfers()
                    self.assertEqual(app.transfer_progress.value, 100)
                finally:
                    release.set()
                    await task
            try:
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()
