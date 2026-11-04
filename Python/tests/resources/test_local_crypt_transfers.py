"""Ciphertext mirror, streaming readers/editors, private UI and credential lifetime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from tempfile import TemporaryDirectory
from unittest.mock import patch
from features.rclone.localcrypt import backend as local_crypt
from features.rclone.localcrypt import mapping as copy_mapping
from features.rclone import actions
from features.rclone import session
from tests.local_crypt_fixture import crypt_fixture


from tests.resources.localcrypt_cases import LocalCryptCase


class LocalCryptTransfersTests(LocalCryptCase):
    def test_decrypted_pull_remembers_package_after_session_restart(self):
        from features.rclone.localcrypt import connections as local_connections
        from features.rclone import ui_contributions
        from models.local_folder import LocalFolder
        from services.folders.entries import get_folder_entries
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            self.assertTrue(actions.pull_remote('Secret', f.context))
            item, = local_connections.connections()
            self.assertEqual(item.package, f.package)
            self.assertEqual(item.data.joinpath('note.md').read_bytes(), f.original)
            self.assertEqual(set(json.loads(item.record.read_text())), {'schema', 'package', 'remote'})
            self.assertNotIn(item.record, list(item.data.rglob('*')))
            session.forget(f.context)
            with patch.dict(session.registry._known_packages, {}, clear=True), \
                 patch.object(ui_contributions.credentials, 'get_loaded_credential_config_paths', return_value=[]):
                sources = ui_contributions._get_remote_sources()
                source, = [source for source in sources if source.name.endswith('— Local')]
                entry, = get_folder_entries(source.get_remote_names(), remote_source='rclone',
                                            remote_context=source.context, local_folders=source.get_local_folders(),
                                            include_local_only=False)
                self.assertEqual([action.name for action in ui_contributions._get_actions(entry)], ['Push...', 'Pull'])
                with patch.object(actions, 'pull_remote', return_value=True) as pull:
                    next(action for action in ui_contributions._get_actions(entry) if action.name == 'Pull').callback()
                pull.assert_called_once_with('Secret', item.context, package=f.package, review=True)
                with patch('features.rclone.localcrypt.ui.views.ensure_session', return_value=False) as unlock:
                    self.assertFalse(actions.push_to_cloud(LocalFolder(item.data), f.context))
                    unlock.assert_called_once_with(item.context, package=f.package)
                with patch('features.rclone.localcrypt.ui.views.ensure_session', return_value=True), \
                     patch('features.rclone.transfers.workflow.sync_transfer', return_value=True) as push:
                    self.assertTrue(actions.push_to_cloud(LocalFolder(item.data), f.context))
                    self.assertEqual(push.call_args.args, (item.data, 'Secret:'))
                    self.assertEqual(push.call_args.kwargs['config_path'], item.context)
            other = local_connections.LocalConnection(f.root / 'Other.zip', 'Secret', item.root)
            with self.assertRaisesRegex(ValueError, 'another credential package'):
                other.publish()

    def test_unaccepted_decrypted_pull_does_not_publish_association(self):
        from features.rclone.localcrypt import connections as local_connections
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f, \
             patch('features.rclone.transfers.sync.rclone_sync', return_value=False):
            self.assertFalse(actions.pull_remote('Secret', f.context))
            self.assertEqual(local_connections.connections(include_missing=True), [])

    def test_unloaded_accounts_need_an_existing_local_copy_to_show(self):
        import shutil
        from features.rclone import ui_contributions
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            self.assertTrue(actions.pull_remote('Secret', f.context))
            values = session.credentials(f.context)
            f.provider.close()
            session.forget(f.context)
            with patch.object(ui_contributions.credentials, 'get_loaded_credential_config_paths', return_value=[]):
                self.assertEqual(len(ui_contributions._get_remote_sources()), 2)
                shutil.rmtree(f.item.data)
                shutil.rmtree(f.root / 'Server/Local/Secret')
                self.assertEqual(ui_contributions._get_remote_sources(), [])
            session.remember(f.context, values, package_path=f.package)
            with patch.object(ui_contributions.credentials, 'get_loaded_credential_config_paths', return_value=[f.context]):
                source, = ui_contributions._get_remote_sources()
                self.assertIn('Secret', source.get_remote_names())
                self.assertEqual(source.get_local_folders(), [])

    def test_malformed_records_and_specific_push_never_fall_back_inside_localcrypt(self):
        from types import SimpleNamespace
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            bad = f.item.record.parent / 'malformed.json'
            for text in ('[]', 'null', '123', '"text"', '{broken'):
                bad.write_text(text)
                self.assertEqual(copy_mapping.connections(), [f.item])
            folder = SimpleNamespace(name='Secret')
            with patch('features.rclone.transfers.workflow.sync_transfer', return_value=True) as transfer:
                actions.push_specific_directory(folder, f.context, str(f.item.data))
                self.assertEqual(transfer.call_args.args[1], copy_mapping.push_target(f.item.data, f.context, folder.name, specific=True))
                self.assertFalse(transfer.call_args.kwargs['copy_links'])
                f.item.record.unlink()
                transfer.reset_mock()
                with self.assertRaisesRegex(ValueError, 'no valid credential mapping'):
                    actions.push_specific_directory(folder, f.context, str(f.item.data))
                transfer.assert_not_called()

    def test_specific_push_preview_matches_execution_and_reports_lost_mapping(self):
        from types import SimpleNamespace
        from features.rclone.transfers.ui.push_dialog import RclonePushDialog
        with self.temporary_directory() as directory, crypt_fixture(directory, self.binary) as f:
            entry = SimpleNamespace(name='Secret', local=SimpleNamespace(path=f.plain, name='Secret'),
                                    remote_source='rclone', remote_context=f.context, remote_name='Secret')
            dialog = RclonePushDialog(entry)
            dialog.specific_radio.setChecked(True)
            dialog.specific_path.setText(str(f.item.data))
            self.assertEqual(dialog.result_destination.text(), 'Cloud:' + str(f.cloud))
            f.item.record.unlink()
            with patch('features.rclone.transfers.ui.push_dialog.ui.display_msg_box_ok') as message, \
                 patch('features.rclone.transfers.workflow.sync_transfer') as transfer:
                dialog._push()
                transfer.assert_not_called()
                self.assertIn('no valid credential mapping', message.call_args.args[1])
                self.assertIn('no valid credential mapping', dialog.result_destination.text())
            dialog.close()

    def test_pull_choices_follow_selected_copy(self):
        from features.rclone.ui_contributions import _get_actions, _matching_local_folders
        from models.folder_entry import FolderEntry
        from types import SimpleNamespace
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary) as f:
            entry = FolderEntry('Secret', remote_name='Secret', remote_source='rclone', remote_context=f.context)
            self.assertEqual([a.name for a in _get_actions(entry)], ['Pull'])
            entry.local = SimpleNamespace(name='Secret')
            names = [a.name for a in _get_actions(entry)]
            self.assertIn('Pull', names)
            self.assertEqual(names, ['Push...', 'Pull'])
            with patch.object(actions, 'pull_remote') as plain:
                next(action for action in _get_actions(entry) if action.name == 'Pull').callback()
                plain.assert_called_once_with('Secret', f.context, review=True)
            entry.local = local_crypt.LocalCryptFolder(f.item)
            with patch.object(actions, 'pull_encrypted_copy') as encrypted, patch.object(actions, 'pull_remote') as plain:
                choices = {a.name: a for a in _get_actions(entry)}
                choices['Pull'].callback()
                encrypted.assert_called_once_with('Secret', f.context, item=f.item, review=True)
                plain.assert_not_called()
                self.assertEqual(set(choices), {'Push...', 'Pull'})
            with patch('models.folder_discovery.get_local_folders', return_value=[]):
                self.assertIsInstance(_matching_local_folders(f.context)[0], local_crypt.LocalCryptFolder)
            ordinary = SimpleNamespace(name='Secret')
            with patch('models.folder_discovery.get_local_folders', return_value=[ordinary]):
                self.assertEqual(_matching_local_folders(f.context), [ordinary])
