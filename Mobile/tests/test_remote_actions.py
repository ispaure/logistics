"""Remote browser feedback and folder-to-local navigation."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from logisticsmobile.app import LogisticsMobile
from test_folder_download import Client


class RemoteActionTests(unittest.TestCase):
    def test_repeatable_pull_has_explicit_refresh_and_conflict_feedback(self):
        class Remote(Client):
            def connection_identity(self, remote):
                return 'a' * 64
            def cancel(self):
                pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = Remote()
                app.show_cloud()
                app.cloud_remote.items = ['remote']
                app.cloud_open_remote = 'remote'
                app.cloud_rows = {'photos': dict(path='photos', directory=True)}
                app.cloud_entries.items = ['photos']
                self.assertTrue(app.loop.run_until_complete(app.create_pull_job()))
                job = next(iter(app.pull_jobs.jobs.values()))
                self.assertTrue(app.loop.run_until_complete(app.run_pull_job(job['id'])))
                self.assertIn('refreshed', app.pull_message)
                local = app.pull_jobs.local / job['target']
                (local / 'note.txt').write_bytes(b'local edits')
                self.assertTrue(app.loop.run_until_complete(app.run_pull_job(job['id'])))
                self.assertIn('Local edits preserved', app.pull_message)
                self.assertEqual((local / 'note.txt').read_bytes(), b'local edits')
                self.assertNotEqual(app.cloud_downloaded_folder, job['target'])
            finally:
                app.main_window.close()
                app.loop.close()

    def test_browse_download_and_open_folder_have_visible_results(self):
        class Remote(Client):
            def entries(self, remote, path):
                if not path:
                    return [dict(path='photos', directory=True, size=0)]
                return super().entries(remote, path)
            def cancel(self):
                pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = Remote()
                app.show_cloud()
                self.assertFalse(app.loop.run_until_complete(app.browse_cloud()))
                self.assertIn('Choose a remote', app.cloud_status.value)
                app.cloud_remote.items = ['remote']
                self.assertTrue(app.loop.run_until_complete(app.browse_cloud()))
                self.assertIn('1 items', app.cloud_status.value)
                app.browser_cloud_selected(dict(path='photos', directory=True))
                self.assertIn('Selected folder', app.cloud_status.value)
                self.assertTrue(app.loop.run_until_complete(app.download_cloud()))
                self.assertTrue(app.cloud_folder_open.enabled)
                self.assertIn('unencrypted local copy', app.cloud_status.value)
                app.loop.run_until_complete(app.open_downloaded_folder())
                self.assertEqual(app.file_path, app.cloud_downloaded_folder)
                self.assertTrue((app.private_root / 'LocalFiles' / app.file_path / 'note.txt').exists())
                app.show_cloud()
                app.cloud_entries.items = []
                self.assertFalse(app.loop.run_until_complete(app.download_cloud()))
                self.assertIn('Select a file or folder', app.cloud_status.value)
            finally:
                app.main_window.close()
                app.loop.close()
