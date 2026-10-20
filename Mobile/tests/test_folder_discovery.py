"""Workspaces discovery snapshots native state before reading files in a worker."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, get_ident
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from logisticsmobile.app import LogisticsMobile
from logisticsmobile.folder_hub_ui import FolderHubUI


class FolderDiscoveryTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        LogisticsMobile.storage_root = Path(directory.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.app.show_cloud(present=False)

    def test_refresh_reads_files_on_worker_and_native_snapshot_on_ui(self):
        threads = []
        original = FolderHubUI._discover_folder_choices
        def discover(snapshot):
            threads.append(get_ident())
            return original(snapshot)
        def loaded():
            self.assertEqual(get_ident(), ui_thread)
            return []
        ui_thread = get_ident()
        with patch.object(FolderHubUI, '_discover_folder_choices', side_effect=discover), \
                patch.object(self.app, 'loaded_remote_names', side_effect=loaded):
            self.assertTrue(self.app.loop.run_until_complete(self.app.refresh_folder_hub()))
        self.assertTrue(threads)
        self.assertTrue(all(thread != ui_thread for thread in threads))
        self.assertIn('All files', self.app.folder_picker_choices)

    def test_changed_credentials_cannot_publish_old_session_names(self):
        self.app.cloud_client = SimpleNamespace(generation=1, cancel=lambda: None)
        started, release = Event(), Event()
        calls = []
        def discover(snapshot):
            calls.append(1)
            if len(calls) == 1:
                started.set()
                if not release.wait(3):
                    raise RuntimeError('Synthetic discovery timed out')
                return {'SESSION-ONLY-SECRET': dict(source='Remote', copies=[])}
            return {}
        async def exercise():
            task = self.app.folder_controller()._schedule_folder_choices()
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                self.app.cloud_client.generation = 2
                release.set()
                self.assertEqual(await task, {})
                self.assertNotIn('SESSION-ONLY-SECRET', self.app.folder_picker_choices)
            finally:
                release.set()
                await task
        with patch.object(FolderHubUI, '_discover_folder_choices', side_effect=discover):
            self.app.loop.run_until_complete(exercise())

    def test_lock_invalidation_retires_a_discovery_before_credentials_finish_locking(self):
        started, release = Event(), Event()
        def discover(snapshot):
            started.set()
            if not release.wait(3):
                raise RuntimeError('Synthetic discovery timed out')
            return {'SESSION-ONLY-SECRET': dict(source='Remote', copies=[])}
        async def exercise():
            controller = self.app.folder_controller()
            task = controller._schedule_folder_choices()
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                self.app.clear_private_catalog()
                release.set()
                self.assertIsNone(await task)
                self.assertEqual(controller._folder_choices_cache, {})
            finally:
                release.set()
                await task
        with patch.object(FolderHubUI, '_discover_folder_choices', side_effect=discover):
            self.app.loop.run_until_complete(exercise())
