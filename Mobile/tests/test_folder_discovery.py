"""Workspaces discovery snapshots native state before reading files in a worker."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, get_ident
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from logisticsmobile.app import LogisticsMobile
from logisticsmobile.folder_hub import discover_folder_choices, FolderDiscoveryResult, FolderDiscoverySnapshot


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
        original = discover_folder_choices
        def discover(snapshot):
            threads.append(get_ident())
            return original(snapshot)
        def loaded():
            self.assertEqual(get_ident(), ui_thread)
            return []
        ui_thread = get_ident()
        with patch('logisticsmobile.folder_discovery.discover_folder_choices', side_effect=discover), \
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
                return FolderDiscoveryResult({'SESSION-ONLY-SECRET': dict(source='Remote', copies=[])}, ())
            return FolderDiscoveryResult({}, ())
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
        with patch('logisticsmobile.folder_discovery.discover_folder_choices', side_effect=discover):
            self.app.loop.run_until_complete(exercise())

    def test_lock_invalidation_retires_a_discovery_before_credentials_finish_locking(self):
        started, release = Event(), Event()
        def discover(snapshot):
            started.set()
            if not release.wait(3):
                raise RuntimeError('Synthetic discovery timed out')
            return FolderDiscoveryResult({'SESSION-ONLY-SECRET': dict(source='Remote', copies=[])}, ())
        async def exercise():
            controller = self.app.folder_controller()
            task = controller._schedule_folder_choices()
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                self.app.clear_private_catalog()
                release.set()
                self.assertIsNone(await task)
                self.assertEqual(controller.discovery.cache, {})
            finally:
                release.set()
                await task
        with patch('logisticsmobile.folder_discovery.discover_folder_choices', side_effect=discover):
            self.app.loop.run_until_complete(exercise())

    def test_snapshot_is_detached_from_jobs_and_retained_credential_metadata(self):
        controller = self.app.folder_controller()
        self.app.cloud_client = None
        jobs = {'job': dict(id='job', remote='Drive', options={'filters': ['keep']})}
        retained = [dict(remotes=['Drive'], package_name='Personal.zip')]
        controller.hub_crypt_roots = {'Secret': ('Drive', 'identity')}
        with patch.object(self.app, 'mirror_store', return_value=SimpleNamespace(jobs=jobs)), \
                patch.object(self.app, 'loaded_remote_names', return_value=['Drive']), \
                patch.object(self.app, 'retained_credential_associations', return_value=retained):
            snapshot = controller.discovery_snapshot()
        self.assertIsInstance(snapshot, FolderDiscoverySnapshot)
        jobs['job']['options']['filters'].append('changed')
        retained[0]['remotes'].append('Other')
        controller.hub_crypt_roots.clear()
        self.assertEqual(snapshot.jobs['job']['options']['filters'], ['keep'])
        self.assertEqual(snapshot.retained_packages[0]['remotes'], ['Drive'])
        self.assertEqual(snapshot.crypt_roots, {'Secret': ('Drive', 'identity')})
        self.assertFalse(hasattr(snapshot, 'cloud_client'))
        self.assertFalse(hasattr(snapshot, 'mirror_store'))

    def check_superseded_scan(self, change, *, failure=False, expect_retry=False):
        controller = self.app.folder_controller()
        started, release = Event(), Event()
        calls = []
        def discover(snapshot):
            calls.append(snapshot)
            if len(calls) == 1:
                started.set()
                if not release.wait(3):
                    raise RuntimeError('Synthetic discovery timed out')
                if failure:
                    raise ValueError('OBSOLETE PRIVATE ERROR')
                return FolderDiscoveryResult({'OBSOLETE PRIVATE NAME': dict(source='Remote', copies=[])}, ())
            return discover_folder_choices(snapshot)
        async def exercise():
            task = controller.discovery.request()
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                change(controller, task)
                self.app.folder_hub_error = 'Current status'
                release.set()
                result = await task
                if expect_retry:
                    self.assertIn('All files', result)
                else:
                    self.assertIsNone(result)
                self.assertEqual(self.app.folder_hub_error, 'Current status')
                self.assertNotIn('OBSOLETE PRIVATE NAME', controller.discovery.cache)
                self.assertNotIn('OBSOLETE PRIVATE NAME', controller.folder_picker_choices)
            finally:
                release.set()
                await task
        with patch('logisticsmobile.folder_discovery.discover_folder_choices', side_effect=discover):
            self.app.loop.run_until_complete(exercise())
        self.assertEqual(len(calls), 2 if expect_retry else 1)

    def test_refresh_requests_share_task_and_coalesce_into_one_new_scan(self):
        def refresh(controller, task):
            for _ in range(5):
                self.assertIs(controller.discovery.request(), task)
        self.check_superseded_scan(refresh, expect_retry=True)

    def test_new_request_after_lock_is_not_lost_behind_retired_scan(self):
        def reopen(controller, task):
            controller.invalidate_folder_discovery()
            self.assertIs(controller.discovery.request(), task)
        self.check_superseded_scan(reopen, expect_retry=True)

    def test_old_errors_are_discarded_after_lock_or_shutdown(self):
        for reason in ('lock', 'shutdown'):
            with self.subTest(reason=reason):
                try:
                    def retire(controller, task):
                        if reason == 'lock':
                            self.app.clear_private_catalog()
                        else:
                            self.app.active_host = False
                    self.check_superseded_scan(retire, failure=True)
                finally:
                    self.app.active_host = True

    def test_old_errors_rescan_after_new_request_or_changed_credentials(self):
        for reason in ('request', 'generation', 'client'):
            with self.subTest(reason=reason):
                self.app.cloud_client = SimpleNamespace(generation=1, cancel=lambda: None)
                def change(controller, task):
                    if reason == 'request':
                        self.assertIs(controller.discovery.request(), task)
                    elif reason == 'generation':
                        self.app.cloud_client.generation += 1
                    else:
                        self.app.cloud_client = SimpleNamespace(generation=1, cancel=lambda: None)
                self.check_superseded_scan(change, failure=True, expect_retry=True)

    def test_current_discovery_failure_is_visible_and_retry_recovers(self):
        with patch('logisticsmobile.folder_discovery.discover_folder_choices', side_effect=OSError('Drive disconnected')):
            self.assertFalse(self.app.loop.run_until_complete(self.app.refresh_folder_hub()))
        self.assertEqual(self.app.folder_hub_error, 'Drive disconnected')
        self.assertIn('Drive disconnected', self.app.folder_loading_status.text)
        self.assertTrue(self.app.loop.run_until_complete(self.app.refresh_folder_hub()))
        self.assertEqual(self.app.folder_hub_error, '')
        self.assertEqual(self.app.folder_loading_status.text, '')

    def test_cached_choices_are_copied_and_hide_names_after_credential_change(self):
        controller = self.app.folder_controller()
        self.app.cloud_client = SimpleNamespace(generation=1, cancel=lambda: None)
        self.app.loop.run_until_complete(controller.discovery.request())
        choices = controller.discovery.cached_choices()
        choices['All files']['name'] = 'Caller changed this'
        self.assertEqual(controller.discovery.cached_choices()['All files']['name'], 'Browse All Files')
        controller.discovery.cache['SECRET'] = dict(source='Remote', copies=[])
        self.app.cloud_client.generation += 1
        self.assertEqual(set(controller.discovery.cached_choices()), {'All files'})
        self.assertEqual(controller.discovery.cache, {})

    def test_builder_does_not_mutate_snapshot_or_create_missing_crypt_directories(self):
        from copy import deepcopy
        from features.rclone.mobile.storage_location import collection_path
        snapshot = FolderDiscoverySnapshot(private_root=self.app.private_root, jobs={},
            remote_names=('Drive',), retained_packages=(), crypt_locations=(('Secret', 'Drive'),),
            crypt_roots={'Secret': ('Drive', 'missing-identity')})
        before = deepcopy(snapshot)
        path = collection_path(self.app.private_root, True) / 'missing-identity'
        self.assertFalse(path.exists())
        result = discover_folder_choices(snapshot)
        self.assertEqual(snapshot, before)
        self.assertEqual(result.crypt_locations, ())
        self.assertFalse(path.exists())
        self.assertEqual(set(result.choices), {'All files', 'Drive'})

    def test_shutdown_retires_successful_scan_without_publishing(self):
        try:
            self.check_superseded_scan(lambda controller, task: setattr(self.app, 'active_host', False))
        finally:
            self.app.active_host = True
