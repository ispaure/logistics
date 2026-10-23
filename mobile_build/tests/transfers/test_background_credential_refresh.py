from features.rclone.mobile.credentials_ui import CredentialWorkflow
"""Credential publication updates retained Home controls and uses published metadata."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, IsolatedAsyncioTestCase
from unittest.mock import Mock, patch

from features.rclone.mobile.cloud_ui import CloudUI
from features.rclone.transfers.mobile.ui import MirrorUI
from mobile.app import LogisticsMobile
from mobile.workspace import Session


class HomeCredentialRefreshTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        LogisticsMobile.storage_root = Path(directory.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.app.cloud_client = SimpleNamespace(package_records=(), cancel=Mock())
        self.source = dict(type='remote', remote='Cloud', identity='a' * 64, key='note.md')
        self.session = Session('recent', 'file-reference', 'reference', 'markdown', 'note.md')
        self.app.recent_documents.remember_file(self.session, self.source)
        self.app.refresh_hub('home')

    def test_unlock_and_lock_update_same_native_buttons_and_home_root(self):
        app = self.app
        root = app.home_content
        button = app.hub_controller()._home_recent_buttons[0]
        self.assertEqual(button.leading_icons[-1][0], 'storage_crypt')
        app.cloud_client.package_records = (dict(package_name='Saved.zip', saved=True, remotes=['Cloud'], identities={'Cloud': 'a' * 64}, crypt_identities={}),)
        app.refresh_hub('home')
        self.assertIs(app.home_content, root)
        self.assertIs(app.hub_controller()._home_recent_buttons[0], button)
        self.assertEqual(button.leading_icons[-1][0], 'storage_unlocked')
        app.cloud_client.package_records = ()
        app.refresh_hub('home')
        self.assertIs(app.home_content, root)
        self.assertEqual(button.leading_icons[-1][0], 'storage_crypt')

    def test_changed_history_and_notices_still_rebuild_home(self):
        app = self.app
        root = app.home_content
        self.session.title = 'renamed.md'
        app.recent_documents.remember_file(self.session, self.source)
        app.refresh_hub('home')
        self.assertIsNot(app.home_content, root)
        self.assertEqual(app.hub_controller()._home_recent_buttons[0].text, 'renamed.md')
        root = app.home_content
        app.workspace.error = 'Recovery needs attention'
        app.refresh_hub('home')
        self.assertIsNot(app.home_content, root)

    def test_unlock_action_changes_still_rebuild_home(self):
        root = self.app.home_content
        with patch.object(CloudUI, 'home_unlock_candidates', return_value=[('key', {})]):
            self.app.refresh_hub('home')
        self.assertIsNot(self.app.home_content, root)


class CredentialMetadataPreparationTests(TestCase):
    def test_local_discovery_uses_published_identity_without_bridge_call(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            identity = 'a' * 64
            folder = base / identity
            folder.mkdir()
            (folder / 'encrypted.bin').write_bytes(b'ciphertext')
            client = SimpleNamespace(package_records=(dict(crypt_identities={'Secret': identity}),), request=Mock())
            app = SimpleNamespace(cloud_client=client, cloud_crypt_remotes={'Secret'}, private_root=base,
                rclone_ui=SimpleNamespace(visible_remotes=lambda names: names))
            roots = {}
            with patch('features.rclone.transfers.mobile.ui.collection_path', return_value=base):
                locations = MirrorUI.existing_crypt_locations(app, roots=roots)
            self.assertEqual(locations, {'LocalCrypt: Secret': 'Secret'})
            self.assertEqual(roots, {'LocalCrypt: Secret': ('Secret', identity)})
            client.request.assert_not_called()

    def test_unchanged_association_does_not_rewrite_preferences(self):
        association = dict(zip='Saved.zip', remotes=['Cloud'], session_only=False)
        preferences = SimpleNamespace(values={'remote_packages': json.dumps([association])}, save=Mock())
        app = SimpleNamespace(preferences=preferences)
        CredentialWorkflow(app).remember_credential_association('Saved.zip', ['Cloud'], session_only=False)
        preferences.save.assert_not_called()
        CredentialWorkflow(app).remember_credential_association('Saved.zip', ['Changed'], session_only=False)
        preferences.save.assert_called_once()

class PublishedCryptMetadataTests(TestCase):
    def test_crypt_names_use_published_metadata_without_threaded_bridge_query(self):
        import asyncio
        from unittest.mock import AsyncMock
        client = SimpleNamespace(package_records=(dict(crypt_identities={'Secret': 'a' * 64}),),
            crypt_remotes=Mock(side_effect=AssertionError('redundant bridge query')))
        app = SimpleNamespace(cloud_client=client, active_host=True, retained_packages=lambda: None,
            refresh_hub_crypt_locations=AsyncMock(), refresh_cloud_remote_help=Mock())
        asyncio.run(CredentialWorkflow(app)._load_crypt_remote_names())
        self.assertEqual(app.cloud_crypt_remotes, {'Secret'})
        client.crypt_remotes.assert_not_called()
        app.refresh_hub_crypt_locations.assert_awaited_once()


class CredentialFreshnessTests(IsolatedAsyncioTestCase):
    async def test_late_crypt_lookup_cannot_replace_new_generation_metadata(self):
        from unittest.mock import AsyncMock
        client = SimpleNamespace(generation=1, package_records=())
        def lookup():
            client.generation = 2
            return ['Obsolete']
        client.crypt_remotes = lookup
        app = SimpleNamespace(cloud_client=client, active_host=True, cloud_crypt_remotes={'Current'},
            retained_packages=Mock(), refresh_hub_crypt_locations=AsyncMock(), refresh_cloud_remote_help=Mock())
        self.assertFalse(await CredentialWorkflow(app)._load_crypt_remote_names())
        self.assertEqual(app.cloud_crypt_remotes, {'Current'})
        app.retained_packages.assert_not_called()
        app.refresh_cloud_remote_help.assert_not_called()

    async def test_restore_rechecks_generation_after_metadata_preparation(self):
        from unittest.mock import AsyncMock
        from features.rclone.credential_loading import CredentialResult
        client = SimpleNamespace(generation=1)
        async def metadata():
            client.generation = 2
        app = SimpleNamespace(cloud_client=client, active_host=True, cloud_busy=False,
            set_cloud_busy=Mock(), _load_crypt_remote_names=metadata, set_loaded_remote_names=Mock(),
            _publish_restored_connections=Mock())
        result = CredentialResult('Original.zip', ('Original',), True, 1)
        with patch('features.rclone.mobile.credentials_ui.native_service'), \
             patch('features.rclone.mobile.credentials_ui.run_credentials', new=AsyncMock(return_value=result)):
            await CredentialWorkflow(app).restore_cloud(initial=True)
        app.set_loaded_remote_names.assert_not_called()
        app._publish_restored_connections.assert_not_called()
        app.set_cloud_busy.assert_called_once_with(False)

    async def test_import_rechecks_generation_before_preferences_or_retention(self):
        from unittest.mock import AsyncMock
        from features.rclone.credential_loading import CredentialResult
        client = SimpleNamespace(generation=1)
        selected = SimpleNamespace(name='Original.zip')
        async def metadata():
            client.generation = 2
        app = SimpleNamespace(cloud_client=client, active_host=True, cloud_busy=False,
            navigation_generation=1, cloud_pending_zip=selected,
            cloud_password=SimpleNamespace(value='synthetic'), cloud_remember=SimpleNamespace(value=False),
            cloud_import_message=SimpleNamespace(text=''), set_cloud_busy=Mock(),
            clear_private_reader=lambda: True, clear_private_catalog=Mock(),
            _load_crypt_remote_names=metadata, remember_loaded_packages=Mock(), retained_packages=Mock())
        result = CredentialResult('Original.zip', ('Original',), False, 1)
        with patch('features.rclone.mobile.credentials_ui.native_service'), \
             patch('features.rclone.mobile.credentials_ui.run_credentials', new=AsyncMock(return_value=result)):
            await CredentialWorkflow(app).import_cloud_package()
        app.remember_loaded_packages.assert_not_called()
        app.retained_packages.assert_not_called()
        self.assertIs(app.cloud_pending_zip, selected)
        self.assertEqual(app.cloud_password.value, '')
        app.set_cloud_busy.assert_called_with(False)
