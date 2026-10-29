"""Native callback checks for encrypted nested destination saves."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback

from features.rclone.localcrypt.mobile.resources import CryptFiles
from tests.logisticsmobile.destination_probe import DestinationProbe


class DestinationEdgeProbe(DestinationProbe):
    async def check_destinations(self):
        report = dict(success=False, backend=type(self._impl).__module__, cases=[])
        try:
            self.show_cloud(present=False)
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
            picker = self.editor_picker()
            fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
            self.cloud_client.request('import', package=fixture['package'], password='synthetic-session-password',
                                      package_name='Synthetic.zip', session_only=True)
            # Credential publication queues private-catalog invalidation. Let
            # that protection finish before opening a new private draft.
            await asyncio.sleep(.5)
            remote = next(iter(fixture['copies'].values()))['record']['remote']
            provider = CryptFiles(self.private_root / 'EncryptedDestination', self.cloud_client, remote)
            await self.wait(lambda: not self.cloud_busy, timeout=60)
            await picker.show_text_destination('Secret.md', b'# Native encrypted draft')
            assert picker.save_as_data == b'# Native encrypted draft', (self.active_host, self.cloud_busy, picker.active_host, picker._epoch, self.navigation_generation, picker.save_as_status.value)
            await asyncio.sleep(.5)
            picker.editor_storage_roots['Encrypted fixture'] = provider
            picker.save_as_storage.items = list(picker.editor_storage_roots)
            picker.save_as_storage.value = 'Encrypted fixture'
            await picker._storage_refresh
            assert picker.picker_primary.enabled and picker.picker_new_folder.enabled
            for name in ('First', 'Nested'):
                picker.new_folder_name.value = name
                await picker.create_picker_folder()
                assert not picker.save_as_status.value, picker.save_as_status.value
            assert picker.picker_folder.value == 'First/Nested'
            await asyncio.sleep(1)
            picker.save_as_name.value = 'Private copy'
            await picker.confirm_editor_file()
            owner = self.private_sessions.active
            assert owner is not None, (picker.save_as_status.value, picker.save_as_data is None, self.navigation_generation)
            assert owner.crypt_reader.name == 'Private copy.md', picker.save_as_status.value
            assert owner.crypt_text.value == '# Native encrypted draft'
            encrypted = provider._physical('First/Nested/Private copy.md').read_bytes()
            assert encrypted and b'# Native encrypted draft' not in encrypted
            assert not (provider.root / 'First/Nested/Private copy.md').exists()
            report['cases'].append('real-localcrypt-nested-folder-basename-save-encrypted-reopen')
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'destination-edge-result.json').write_text(json.dumps(report, indent=2))
