"""Controller ownership and operation cancellation remain independent."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mobile.app import LogisticsMobile
from features.lm.mobile.ui import ChatUI
from features.rclone.mobile.cloud_ui import CloudUI


class WorkflowOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')

    def tearDown(self):
        self.app.main_window.close()
        close_loop(self.app.loop)
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_feature_state_has_one_owner_and_host_access_is_explicit(self):
        app = self.app
        app.cloud_client = None
        owner = app.cloud_controller()
        self.assertIs(app.cloud_controller(), owner)
        self.assertIsNone(owner.cloud_client)
        self.assertIs(owner.state.client, app.cloud_client)
        app.cloud_busy = True
        self.assertTrue(owner.state.busy)
        app.cloud_busy = False
        app.show_smb_connection()
        self.assertIs(app.smb_password, owner.smb_form.smb_password)
        self.assertNotIn('smb_password', app.__dict__)
        self.assertNotIn('smb_password', owner.__dict__)
        self.assertNotIn('cloud_client', app.__dict__)
        self.assertNotIsInstance(app, (ChatUI, CloudUI))
        with self.assertRaises(AttributeError):
            getattr(owner, 'undeclared_host_service')

    def test_chat_state_aliases_share_one_owner_and_hosts_stay_independent(self):
        from features.lm.mobile.controller import ChatController
        app = self.app
        owner = app.chat_controller()
        other = ChatController(SimpleNamespace(active_host=True))
        record = {'id': 'fixture', 'messages': [], 'draft': ''}
        app.chat_current = record
        self.assertIs(owner.state.current, record)
        owner.state.busy = True
        self.assertTrue(app.chat_busy)
        app.chat_render_entries = [{'text': 'Retained transcript'}]
        self.assertIs(app.chat_render_entries, owner.transcript.entries)
        self.assertEqual(other.transcript.entries, [])
        self.assertIsNone(other.state.current)
        self.assertFalse(other.state.busy)
        self.assertNotIn('chat_current', app.__dict__)
        self.assertNotIn('chat_current', owner.__dict__)
        with self.assertRaises(AttributeError):
            other.active_host = False
        other.app.active_host = False
        self.assertFalse(other.active_host)
        app.chat_busy = False
        app.chat_current = None

    def test_transfer_cancel_does_not_cancel_an_independent_file_operation(self):
        app = self.app
        file_cancel, transfer_cancel = Event(), Event()
        app._crypt_cancel = file_cancel
        app.cloud_client = None
        owner = app.transfer_controller()
        owner._transfer_cancel = transfer_cancel
        app.transfer_busy = True
        app.show_transfers()
        app.cancel_mirror_transfer()
        self.assertTrue(transfer_cancel.is_set())
        self.assertFalse(file_cancel.is_set())
        app.cancel_cloud()
        self.assertTrue(file_cancel.is_set())

    def test_native_credential_vaults_receive_the_application_host(self):
        app = self.app
        client = SimpleNamespace(vault=None, generation=0, cancel=lambda: None)
        vault = SimpleNamespace(root=Path(self.directory.name) / 'packages')
        with patch('features.rclone.mobile.credential_vault.ProtectedVault.for_app', return_value=vault) as factory, patch(
                'features.rclone.mobile.cloud_ui.CloudClient', return_value=client) as engine:
            app.show_cloud(present=False)
            factory.assert_called_once_with(app)
            engine.assert_called_once_with(vault=vault)
            client.vault = vault
            factory.reset_mock()
            cache = app.retained_packages()
            factory.assert_called_once_with(app, packages=True)
            self.assertIs(cache.client, client)
            self.assertIs(cache.vault, vault)

    def test_import_controls_use_the_credential_owner_and_keep_app_compatibility(self):
        from unittest.mock import AsyncMock

        app = self.app
        app.cloud_client = SimpleNamespace(vault=None, generation=0, cancel=lambda: None)
        app.show_cloud_connections()
        owner = app.cloud_controller()
        workflow = owner.credential_workflow
        self.assertIs(owner.credential_state, workflow.state)
        archive = object()
        app.cloud_pending_zip = archive
        self.assertIs(workflow.state.cloud_pending_zip, archive)
        self.assertNotIn('cloud_pending_zip', app.__dict__)

        with patch.object(workflow, 'choose_cloud_package', new_callable=AsyncMock) as choose, \
                patch.object(workflow, 'import_cloud_package', new_callable=AsyncMock) as unlock, \
                patch.object(owner, 'choose_cloud_package', new_callable=AsyncMock) as choose_forwarder, \
                patch.object(owner, 'import_cloud_package', new_callable=AsyncMock) as unlock_forwarder:
            app.loop.run_until_complete(app.cloud_import_entry.on_press())
            choose.assert_awaited_once_with(automatic=True)
            app.loop.run_until_complete(app.cloud_import.on_press())
            unlock.assert_awaited_once_with(interactive=True)
            choose_forwarder.assert_not_awaited()
            unlock_forwarder.assert_not_awaited()
            app.loop.run_until_complete(app.choose_cloud_package())
            app.loop.run_until_complete(app.import_cloud_package())
            choose_forwarder.assert_awaited_once_with()
            unlock_forwarder.assert_awaited_once_with()

        self.assertIsNone(workflow.state.cloud_pending_zip)

    def test_global_cancel_closes_an_active_transfer_review(self):
        app = self.app
        app.cloud_client = None
        owner = app.transfer_controller()
        owner._transfer_cancel = Event()
        retired = []
        owner._cancel_transfer_review = lambda: retired.append(True)
        app.cancel_cloud()
        self.assertEqual(retired, [True])
        self.assertTrue(owner._transfer_cancel.is_set())
