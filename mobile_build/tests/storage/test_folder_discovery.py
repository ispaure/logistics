"""Workspaces discovery snapshots native state before reading files in a worker."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, get_ident
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from mobile.app import LogisticsMobile
from mobile.folder_hub import discover_folder_choices, FolderDiscoveryResult, FolderDiscoverySnapshot


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
        with patch('mobile.folder_discovery.discover_folder_choices', side_effect=discover), \
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
        with patch('mobile.folder_discovery.discover_folder_choices', side_effect=discover):
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
        with patch('mobile.folder_discovery.discover_folder_choices', side_effect=discover):
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
        with patch('mobile.folder_discovery.discover_folder_choices', side_effect=discover):
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
        with patch('mobile.folder_discovery.discover_folder_choices', side_effect=OSError('Drive disconnected')):
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

    def test_shared_remote_names_are_plain_and_visible_under_each_credential(self):
        from mobile.folder_hub import credential_choices, source_choices, folder_browse_copy
        from services.folders.catalog import CredentialScope
        from services.documents.locations import use_shared_local, _shared_local_roots
        shared_directory = TemporaryDirectory()
        self.addCleanup(shared_directory.cleanup)
        shared = Path(shared_directory.name)
        (shared / 'Drive').mkdir(parents=True)
        use_shared_local(self.app.private_root, shared)
        self.addCleanup(_shared_local_roots.pop, self.app.private_root, None)
        snapshot = FolderDiscoverySnapshot(private_root=self.app.private_root, jobs={},
            remote_names=('Drive',), retained_packages=(), crypt_locations=(), crypt_roots={},
            source_packages=tuple(dict(package_name=name, remotes=['Drive'], identities={'Drive': 'a' * 64})
                                  for name in ('One.zip', 'Two.zip')))
        choices = discover_folder_choices(snapshot).choices
        self.assertEqual(set(choices), {'All files', 'Drive', 'Received Files'})
        cloud = source_choices(choices, 'rclone')
        for package in ('One.zip', 'Two.zip'):
            self.assertEqual(list(credential_choices(cloud, CredentialScope(['Drive'], package))), ['Drive'])
        local = source_choices(choices, 'Local')
        self.assertIn('Drive', local)
        self.assertEqual(folder_browse_copy(local['Drive'], 'Local')['kind'], 'shared-local')

    def test_stale_sync_mapping_does_not_hide_loaded_cloud_credentials(self):
        from mobile.folder_hub import folder_browse_copy, folder_row_presentation, credential_choices
        from services.folders.catalog import CredentialScope
        from features.rclone.transfers.mobile.jobs import copy_target, remote_location
        remote = 'Server-Lib-Calibre'
        job = dict(id='1' * 32, remote=remote, identity='a' * 64, cipher_identity='',
                   crypt=False, prefix='', target=remote)
        copy_target(self.app.private_root, job).mkdir(parents=True)
        package = dict(package_name='Server.zip', remotes=[remote, 'Sibling'],
                       identities={remote: 'b' * 64, 'Sibling': 'c' * 64})
        snapshot = FolderDiscoverySnapshot(self.app.private_root, {job['id']: job},
            tuple(package['remotes']), (), (), {}, (package,))
        entry = discover_folder_choices(snapshot).choices[remote]
        cloud = folder_browse_copy(entry, 'rclone')
        self.assertEqual(cloud['kind'], 'remote')
        self.assertEqual(cloud['value'], (remote, ''))
        self.assertEqual(cloud['connection_identity'], 'b' * 64)
        self.assertEqual(folder_browse_copy(entry, 'Local')['kind'], 'job')
        scoped = credential_choices({remote: entry}, CredentialScope([remote], 'Server.zip'))
        self.assertIn(remote, scoped)
        self.assertEqual(folder_row_presentation(remote, scoped[remote], 'rclone',
                         set(package['remotes']), {remote}).state, 'unlocked')
        # Cloud browsing may use the loaded connection; the old transfer must
        # still reject it instead of silently retargeting existing local files.
        client = SimpleNamespace(connection_identity=lambda name: 'b' * 64)
        with self.assertRaisesRegex(ValueError, 'matching connection'):
            remote_location(client, job)
        self.assertEqual(job['identity'], 'a' * 64)

    def test_matching_sync_replaces_only_its_own_package_cloud_target(self):
        from mobile.folder_hub import folder_browse_copy, credential_choices
        from services.folders.catalog import CredentialScope
        from features.rclone.transfers.mobile.jobs import copy_target
        job = dict(id='1' * 32, remote='Calibre', identity='a' * 64, cipher_identity='',
                   crypt=False, prefix='', target='Calibre')
        copy_target(self.app.private_root, job).mkdir(parents=True)
        packages = tuple(dict(package_name=name, remotes=['Calibre'], identities={'Calibre': identity * 64})
                         for name, identity in [('Mapped.zip', 'a'), ('Other.zip', 'b')])
        snapshot = FolderDiscoverySnapshot(self.app.private_root, {job['id']: job},
                                           ('Calibre',), (), (), {}, packages)
        entry = discover_folder_choices(snapshot).choices['Calibre']
        for package, kind, identity in [('Mapped.zip', 'job-remote', 'a'), ('Other.zip', 'remote', 'b')]:
            scoped = credential_choices({'Calibre': entry}, CredentialScope(['Calibre'], package))
            self.assertIn('Calibre', scoped)
            target = folder_browse_copy(scoped['Calibre'], 'rclone')
            self.assertEqual(target['kind'], kind)
            self.assertEqual(target['connection_identity'], identity * 64)
            self.assertFalse(target['locked'])

    def test_builder_does_not_mutate_snapshot_or_create_missing_crypt_directories(self):
        from copy import deepcopy
        from services.documents.locations import collection_path
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
        self.assertEqual(set(result.choices), {'All files', 'Drive', 'Received Files'})

    def test_shutdown_retires_successful_scan_without_publishing(self):
        try:
            self.check_superseded_scan(lambda controller, task: setattr(self.app, 'active_host', False))
        finally:
            self.app.active_host = True
