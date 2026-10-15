import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import AsyncMock, patch
from logisticsmobile.app import LogisticsMobile
from test_mirror_jobs import MirrorClient


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
    def test_native_review_replaces_partial_snapshots_and_publishes_final_cleanup(self):
        from features.rclone.review import ReviewScan
        from features.rclone.mobile.transfer_review_ui import native_scanner
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
                crypt=False, _push=True), Path(folder), cleanup_plan=lambda cancelled: {'junk': ('junk', 'v1')}))
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
            from features.rclone.transfer_options import TransferOptions, save_options
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
                    self.assertTrue(await drive_review(app, early=True))
                    self.assertEqual(dialog.await_count, 1)
                self.assertTrue(retired.is_set())
            try:
                app.loop.run_until_complete(exercise())
            finally:
                release.set()

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
        from features.rclone.mobile.mirror_ui import MirrorUI
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
        self.assertEqual(app.cloud_status.value, ' '.join(app.transfer_notice.text.splitlines()))
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
                    app.show_documents()
                    owner = app.editor_view
                    self.assertIn(owner.document_view.transfer_banner, owner.document_view.children)
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
                    self.assertIn(owner.document_view.transfer_banner, owner.document_view.children)
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
