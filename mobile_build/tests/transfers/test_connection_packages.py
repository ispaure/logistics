"""Package navigation, explicit retention decisions and scoped credential removal."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import toga
from unittest.mock import AsyncMock, Mock, patch

from mobile.app import LogisticsMobile
from features.rclone.mobile.credential_dialog import CredentialStorageDialog
from mobile_build.tests.transfers.test_credential_packages import CacheClient, PACKAGE


class PackageClient(CacheClient):
    def __init__(self):
        self.package_records = [dict(package_name='Personal.zip', saved=False, remotes=['Secret']),
                                dict(package_name='Work.zip', saved=True, remotes=['Team'])]
        self.remembered = []

    def import_package(self, access, reference, password, *, remember=True):
        super().import_package(access, reference, password, remember=remember)
        self.remembered.append(remember)
        self.package_records[0]['saved'] = remember
        return ['Secret', 'Team']

    def forget_package(self, name):
        self.package_records = [item for item in self.package_records if item['package_name'] != name]
        self.generation += 1


class ConnectionPackageTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        LogisticsMobile.storage_root = root
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.client = PackageClient()
        self.app.cloud_client = self.client
        self.app.show_cloud(present=False)
        self.store = SimpleNamespace(client=self.client, items={
            'a' * 64: dict(zip='Personal.zip', remotes={'Secret': 'a' * 64}),
            'b' * 64: dict(zip='Work.zip', remotes={'Team': 'b' * 64}),
            'c' * 64: dict(zip='Backups.zip', remotes={'Offline': 'c' * 64})},
            aliases=lambda key: {})
        @contextmanager
        def open_package(key):
            from io import BytesIO
            yield self.store.items[key]['zip'], BytesIO(PACKAGE)
        self.store.open = open_package
        self.store.forget_package = Mock(side_effect=lambda name: setattr(self.store, 'items', {
            key: item for key, item in self.store.items.items() if item['zip'] != name}))
        self.enterContext(patch.object(self.app, 'retained_packages', return_value=self.store))
        self.workflow = self.app.cloud_controller().credential_workflow

    def test_list_and_package_page_keep_correct_names_status_and_scope(self):
        app = self.app
        app.show_cloud_connections()
        labels = [getattr(button, '_settings_source_text', button.text)
                  for button in app.cloud_retained_buttons.values()]
        self.assertTrue(any('Personal' in text and 'Session-Only' in text for text in labels))
        self.assertFalse(any('.zip' in text for text in labels))
        app.cloud_retained_buttons['a' * 64].on_press()
        self.assertEqual(app.routes.screens['settings'][-1][0], 'credential-package')
        self.assertEqual(self.workflow.package_status.text, 'Session-Only')
        self.assertEqual([child.text for child in self.workflow.package_remotes_box.children], ['Secret'])
        app.cloud_retained_buttons['b' * 64].on_press()
        self.assertEqual(self.workflow.package_status.text, 'Persistent save')
        self.assertEqual([child.text for child in self.workflow.package_remotes_box.children], ['Team'])

    def test_unlock_popup_cancel_and_both_choices(self):
        app = self.app
        app.show_cloud_connections()
        for choice in (None, False, True):
            self.workflow.show_credential_package('Personal.zip')
            app.credential_unlock_password.value = 'correct'
            app.main_window._impl.dialog_responses['QuestionDialog'] = [choice]
            with patch.object(app, '_load_crypt_remote_names', new_callable=AsyncMock):
                app.loop.run_until_complete(app.credential_unlock_button.on_press())
            self.assertEqual(app.credential_unlock_password.value, '')
            self.assertEqual(self.client.remembered, [] if choice is None else [False] if choice is False else [False, True])
        self.assertEqual(self.workflow.package_status.text, 'Persistent save')
        text = CredentialStorageDialog('Personal', saved=True).message
        self.assertIn('Session-Only does not delete it', text)
        self.assertIn('not protected by the ZIP password', text)
        self.assertIn('device-protected encrypted storage', text)

    def test_storage_cards_fit_phone_and_choose_directly_with_separate_cancel(self):
        from mobile.settings.forms import CredentialStorageContent
        from mobile.palette import set_eink_enabled
        self.addCleanup(set_eink_enabled, False)
        for high_contrast in (False, True):
            set_eink_enabled(high_contrast)
            choices = []
            content = CredentialStorageContent('Personal', True, choices.append)
            content.reflow(320)
            self.assertEqual(content.children[-1], content.cancel)
            self.assertEqual(len(content.cards), 2)
            for card, choice in zip(content.cards, (False, True)):
                self.assertIn('\n', card._settings_source_text)
                self.assertGreater(card.style.height, 48)
                self.assertTrue(card._impl._surface_roles[2])
                self.assertTrue(card._impl._surface_eink_outlined)
                card.on_press()
                self.assertIs(choices[-1], choice)
            self.assertTrue(content.cancel._impl._surface_roles[2])
            content.cancel.on_press()
            self.assertEqual(choices, [False, True, None])

    def test_forget_package_cancel_then_confirm_keeps_other_credentials_and_local(self):
        app = self.app
        local = app.private_root / 'LocalFiles' / 'Downloaded'
        local.mkdir(parents=True)
        (local / 'keep.txt').write_text('keep')
        app.show_cloud_connections()
        self.workflow.show_credential_package('Personal.zip')
        app.cloud_rows = {'stale': {'path': 'old-folder'}}
        app.cloud_open_remote = 'Secret'
        app.cloud_location.value = app.cloud_path = 'old-folder'
        with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=False)):
            app.loop.run_until_complete(self.workflow.package_forget.on_press())
        self.assertEqual(len(self.client.package_records), 2)
        self.assertEqual(app.cloud_open_remote, 'Secret')
        with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                patch('toga.ConfirmDialog', wraps=toga.ConfirmDialog) as confirm:
            app.loop.run_until_complete(self.workflow.package_forget.on_press())
        self.assertIn('cannot be undone', confirm.call_args.args[1])
        self.assertEqual([item['package_name'] for item in self.client.package_records], ['Work.zip'])
        self.store.forget_package.assert_called_once_with('Personal.zip')
        self.assertEqual(app.loaded_remote_names(), ['Team'])
        self.assertEqual(app.cloud_rows, {})
        self.assertIsNone(app.cloud_open_remote)
        self.assertEqual(app.cloud_path, '')
        self.assertNotIn('Secret', app.folder_choices())
        self.assertEqual((local / 'keep.txt').read_text(), 'keep')
        self.assertEqual(app.routes.screens['settings'][-1][0], 'connections')

    def test_global_forget_requires_confirmation_before_mutating(self):
        app = self.app
        app.show_cloud_connections()
        self.assertEqual(app.cloud_clear.text, 'Forget all saved credentials')
        with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=False)), \
                patch('toga.ConfirmDialog', wraps=toga.ConfirmDialog) as confirm:
            app.loop.run_until_complete(app.cloud_clear.on_press())
        self.assertEqual(len(self.client.package_records), 2)
        self.assertIn('ALL saved and session credentials', confirm.call_args.args[1])

    def test_stale_association_cannot_recreate_forgotten_package_from_equal_remote_name(self):
        import json
        self.app.preferences.save(remote_packages=json.dumps([
            dict(zip='Forgotten.zip', remotes=['Secret'], session_only=False)]))
        self.assertEqual(set(self.app.credential_groups()), {'All', 'Personal', 'Work', 'Backups'})

    def test_other_scene_forgetting_saved_package_removes_cached_settings_row(self):
        import json
        from mobile.preferences import Preferences
        self.app.preferences.save(remote_packages=json.dumps([
            dict(zip='Forgotten.zip', remotes=['Gone'], session_only=False)]))
        self.assertIn('Forgotten.zip', {row[0] for row in self.workflow.package_rows()})
        other_scene = Preferences(self.app.preferences.path.parent)
        other_scene.save(remote_packages='[]')
        self.assertIn('Forgotten.zip', self.app.preferences.values['remote_packages'])
        self.assertNotIn('Forgotten.zip', {row[0] for row in self.workflow.package_rows()})

    def test_another_scene_changing_credentials_retires_the_open_unlock_choice(self):
        self.app.show_cloud_connections()
        self.workflow.show_credential_package('Personal.zip')
        async def replace_while_prompting(dialog):
            self.client.generation += 1
            return True
        self.app.credential_unlock_password.value = 'correct'
        with patch.object(self.app.main_window, 'dialog', side_effect=replace_while_prompting):
            self.app.loop.run_until_complete(self.app.credential_unlock_button.on_press())
        self.assertEqual(self.client.remembered, [])
        self.assertIn('Credentials changed', self.app.credential_unlock_status.text)
        self.assertEqual(self.app.credential_unlock_password.value, '')
