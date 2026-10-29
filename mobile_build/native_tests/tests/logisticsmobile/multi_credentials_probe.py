"""Disposable native proof of mixed credential modes; synthetic ZIPs only."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import base64
import json
from pathlib import Path
import traceback
from uuid import uuid4

from commonUtils.runtime.resources.documents import LocalDocuments
from features.rclone.mobile.cloud_ui import SelectedCredentialZIP
from mobile.app import LogisticsMobile

# Existing encrypted test fixture: one synthetic in-memory remote, no server.
PACKAGE = base64.b64decode('UEsDBBQAAQBjACcuTV3J2bwINgAAABgAAAALAAsAZml4dHVyZS50eHQBmQcAAQBBRQMIAJ7Y0pSWyQhai4Ta0J12uXz0ODn7tWsc5tNblcWra+jflD6LxE8HzcWxhN7eUoRY9Fl3gDAmjVBLAQIUAxQAAQBjACcuTV3J2bwINgAAABgAAAALAAsAAAAAAAAAAACAAQAAAABmaXh0dXJlLnR4dAGZBwABAEFFAwgAUEsFBgAAAAABAAEARAAAAGoAAAAAAA==')
PASSWORD = 'synthetic-fixture-password'


class MultiCredentialProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('multi-credentials-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def load_fixture(self, label, saved):
        path = self.private_root / label
        path.write_bytes(PACKAGE)
        self.cloud_pending_zip = SelectedCredentialZIP(LocalDocuments(), path)
        self.cloud_password.value = PASSWORD
        self.cloud_remember.value = saved
        await self.import_cloud_package()
        assert label in self.cloud_package.text, self.cloud_import_message.text

    async def probe(self):
        report = dict(success=False, cases=[], backend=type(self._impl).__module__)
        try:
            await asyncio.sleep(.7)
            self.show_cloud_connections()
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
            self.show_legacy_choice.value = True
            await self.load_fixture('Personal.zip', True)
            saved_file = self.cloud_client.vault.ciphertext
            saved_bytes = saved_file.read_bytes()
            await self.load_fixture('Legacy.zip', False)
            assert saved_file.read_bytes() == saved_bytes, 'Session package changed saved vault'
            records = self.cloud_client.package_records
            assert {item['package_name']:item['saved'] for item in records} == {'Personal.zip':True, 'Legacy.zip':False}, records
            assert len(self.loaded_remote_names()) == 2
            personal = self.cloud_client.package_remotes('Personal.zip')[0]
            legacy = self.cloud_client.package_remotes('Legacy.zip')[0]
            assert personal != legacy, 'Duplicate remote names overlap'
            self.show_locations()
            assert {'Personal','Legacy'} <= set(self.folder_credentials), self.folder_credentials
            saved_associations = json.loads(self.preferences.values['remote_packages'])
            assert [item['zip'] for item in saved_associations] == ['Personal.zip'], saved_associations
            report['cases'].append('saved_and_session_packages_side_by_side')
            await self.restore_cloud()
            assert len(self.loaded_remote_names()) == 2
            assert self.cloud_client.package_remotes('Legacy.zip') == [legacy]
            report['cases'].append('saved_reload_preserves_session_package')
            cache = self.retained_packages()
            key = next(key for key,item in cache.items.items() if item['zip']=='Legacy.zip')
            assert cache.items[key].get('aliases'), cache.items
            self.cloud_client.request('clear')
            await self.restore_cloud()
            assert self.loaded_remote_names() == [personal], self.loaded_remote_names()
            assert not self.cloud_client.session_privacies
            self.show_retained_unlock(key, destination='settings', resume=self.show_locations)
            self.credential_unlock_password.value = 'wrong-fixture-password'
            await self.credential_unlock_button.on_press()
            assert self.loaded_remote_names() == [personal]
            self.credential_unlock_password.value = PASSWORD
            await self.credential_unlock_button.on_press()
            assert self.cloud_client.package_remotes('Legacy.zip') == [legacy]
            assert len(self.loaded_remote_names()) == 2
            report['cases'].append('restart_saved_only_then_password_unlock_with_stable_alias')
            await self.load_fixture('Work.zip', True)
            assert len(self.loaded_remote_names()) == 3
            self.cloud_client.request('clear')
            await self.restore_cloud()
            assert {item['package_name'] for item in self.cloud_client.package_records} == {'Personal.zip','Work.zip'}
            assert len(self.loaded_remote_names()) == 2
            report['cases'].append('multiple_saved_packages_restore_without_session_secrets')
            self.show_retained_unlock(key, destination='settings', resume=self.show_locations)
            self.credential_unlock_password.value = PASSWORD
            await self.credential_unlock_button.on_press()
            assert len(self.loaded_remote_names()) == 3
            self.show_locations()
            assert {'Personal','Legacy','Work'} <= set(self.folder_credentials)
            report['cases'].append('three_package_folder_hub')
            report['package_modes'] = {item['package_name']:item['saved'] for item in self.cloud_client.package_records}
            report['success'] = True
        except Exception:
            traceback.print_exc()
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'multi-credentials-result.json').write_text(json.dumps(report, indent=2))
        print('MULTI_CREDENTIALS_PROOF=' + json.dumps(report), flush=True)


def main():
    MultiCredentialProbe('Logistics Mobile', 'io.github.ispaure.logisticsmobile').main_loop()
