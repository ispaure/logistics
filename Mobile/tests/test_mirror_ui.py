import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import AsyncMock, patch
from logisticsmobile.app import LogisticsMobile
from test_mirror_jobs import MirrorClient


class MirrorUITests(unittest.TestCase):
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
                    self.assertFalse(await app.transfer_task)
                    self.assertEqual(target.read_bytes(), b'keep my local edit')
                    self.assertEqual(dialog.await_count, 1)
                async def changed(dialog):
                    client.generation += 1
                    return True
                with patch.object(app.main_window, 'dialog', new=AsyncMock(side_effect=changed)):
                    app.start_mirror_pull(job['id'])
                    self.assertFalse(await app.transfer_task)
                    self.assertEqual(target.read_bytes(), b'keep my local edit')
                with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
                    app.start_mirror_pull(job['id'])
                    self.assertTrue(await app.transfer_task)
                    self.assertEqual(target.read_bytes(), b'first')
                target.write_bytes(b'confirmed push')
                plan = app.mirror_push_plan = store.push_plan(job['id'], client)
                app.show_mirror_push_review()
                confirm = app.mirror_review_view.children[2].on_press
                with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=False)):
                    await confirm()
                    self.assertIs(app.mirror_push_plan, plan)
                    self.assertEqual(client.data['folder/note.txt'], b'first')
                with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)) as dialog:
                    await confirm()
                    self.assertEqual(dialog.await_count, 1)
                    self.assertEqual(client.data['folder/note.txt'], b'confirmed push')
            try:
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_credentials_invalidate_the_old_review_and_its_confirm_callback(self):
        class Client(MirrorClient):
            def restore(self, **kwargs):
                return []
            def crypt_remotes(self):
                return []
            def cancel(self):
                pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            client = app.cloud_client = Client()
            app.show_cloud(present=False)
            store = app.mirror_store()
            job, _ = store.create(client, 'Remote', 'folder')
            (store.target(job) / 'note.txt').write_bytes(b'local edits')
            app.mirror_push_plan = store.push_plan(job['id'], client)
            app.show_mirror_push_review()
            confirm = app.mirror_review_view.children[2].on_press
            app.clear_private_catalog()
            app.loop.run_until_complete(confirm())
            self.assertIsNone(app.mirror_push_plan)
            self.assertEqual(len(app.mirror_review_view.children), 1)
            self.assertEqual(client.data['folder/note.txt'], b'first')
    def test_pull_continues_while_writing_without_taking_documents_away(self):
        started, release = Event(), Event()
        class Client(MirrorClient):
            def cancel(self):
                release.set()
            def restore(self, **kwargs):
                return []
            def crypt_remotes(self):
                return []
            def request(self, action, **values):
                if action == 'mirror_read':
                    started.set()
                    if not release.wait(10):
                        raise RuntimeError('Transfer fixture was not released')
                return super().request(action, **values)
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
