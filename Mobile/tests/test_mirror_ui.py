import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from logisticsmobile.app import LogisticsMobile
from test_mirror_jobs import MirrorClient


class MirrorUITests(unittest.TestCase):
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
            confirm()
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
