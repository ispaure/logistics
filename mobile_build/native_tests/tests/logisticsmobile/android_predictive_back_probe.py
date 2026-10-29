"""Real edge gestures and cold Workspaces unlock, using disposable fixtures."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import base64
import json
from pathlib import Path
import traceback

from types import SimpleNamespace
from services.documents.locations import collection_path
from features.rclone.localcrypt.mobile.resources import CryptFiles
from .android_document_navigation_probe import AndroidDocumentNavigationProbe, BUNDLE


class AndroidPredictiveBackProbe(AndroidDocumentNavigationProbe):
    def publish(self):
        if hasattr(self, 'localcrypt_result'):
            self.state['localcrypt'] = self.localcrypt_result
        super().publish()

    async def action(self, name, action='back'):
        if action == 'back' and name == 'dirty-back-opens-prompt':
            from android.content import Context
            owner = self.private_sessions.active
            native = owner.crypt_text._impl.native
            native.requestFocus()
            manager = self._impl.native.getSystemService(Context.INPUT_METHOD_SERVICE)
            manager.showSoftInput(native, 1)
            await self.wait_until(self.ime_visible, 'Dirty editor keyboard did not appear')
            await self.assert_compact_keyboard()
            routes = tuple(self.routes.screens['files'])
            events = len(self.state['back_events'])
            await super().action('cancel-gesture-with-unsaved-keyboard', 'cancel-gesture')
            assert self.ime_visible()
            assert tuple(self.routes.screens['files']) == routes
            assert len(self.state['back_events']) == events
            await super().action('gesture-dismisses-unsaved-keyboard', 'gesture')
            assert not self.ime_visible()
            assert tuple(self.routes.screens['files']) == routes
            assert len(self.state['back_events']) == events
            assert owner.crypt_text.value == 'Synthetic unsaved draft'
            self.state['checks']['unsaved_keyboard_cancel_and_commit_preserve_draft'] = True
        if action == 'back' and name in ('clean-back-files', 'dirty-back-opens-prompt',
                                        'dirty-prompt-back-keeps-editing', 'back-dismisses-keyboard'):
            destination = self.native_host.state.destination
            routes = tuple(self.routes.screens[destination])
            reader = self.visible_reader()
            ime = self.ime_visible()
            events = len(self.state['back_events'])
            await super().action('cancel-' + name, 'cancel-gesture')
            assert tuple(self.routes.screens[destination]) == routes
            assert self.visible_reader() == reader
            assert self.ime_visible() == ime
            assert len(self.state['back_events']) == events
            self.state['checks']['cancelled_gesture_preserves_' + name] = True
        return await super().action(name, 'gesture' if action == 'back' else action)

    async def press_localcrypt_control(self, name, button):
        return await button.on_press()

    async def check_localcrypt(self):
        # Complete startup's credential restore before seeding native fixtures.
        restore = self.start_cloud_restore()
        if restore is not None:
            await restore
        assert not hasattr(self, 'cloud_view'), 'Probe must start before Home unlock/settings are opened'
        self.prepare_cloud()
        fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
        fixture['package'] = json.loads(Path(__file__).with_name('android_predictive_back_fixture.json').read_text())['package']
        client = self.cloud_client
        await asyncio.to_thread(client.request, 'import', package=fixture['package'],
            password='synthetic-session-password', package_name='Synthetic.zip', session_only=True)
        remote = next(iter(await asyncio.to_thread(client.crypt_remotes)))
        identity = await asyncio.to_thread(client.connection_identity, remote)
        cache = self.retained_packages()
        await asyncio.to_thread(cache.remember,
            SimpleNamespace(name='Synthetic.zip', data=base64.b64decode(fixture['package'])),
            {remote: identity}, crypt_remotes=[remote])
        def seed():
            provider = CryptFiles(collection_path(self.private_root, True), client, remote,
                                  namespace=identity, storage_root=self.private_root)
            provider._physical('text.txt').write_bytes(base64.b64decode(fixture['copies']['text.txt']['ciphertext']))
        await asyncio.to_thread(seed)
        # Seed an existing pulled mapping without running a new transfer.
        store = self.mirror_store()
        job = await asyncio.to_thread(store.prepare_review, client, remote, '', storage='LocalCrypt')
        store.jobs[job['id']] = job
        await asyncio.to_thread(store.save)
        await self.refresh_hub_crypt_locations()
        client.lock()
        self.set_loaded_remote_names([])
        assert not hasattr(self, 'cloud_view')
        self.show_locations()
        await self.wait_until(lambda: remote in self.folder_buttons, 'Locked workspace did not appear')
        assert not await self.press_localcrypt_control('workspace', self.folder_buttons[remote])
        assert self.routes.screens['files'][-1][0] == 'unlock-credential'
        self.credential_unlock_password.value = 'wrong-synthetic-password'
        await self.press_localcrypt_control('wrong-password', self.credential_unlock_button)
        assert 'Unlock failed' in self.credential_unlock_status.text
        assert self.routes.screens['files'][-1][0] == 'unlock-credential'
        self.credential_unlock_password.value = 'synthetic-session-password'
        await self.press_localcrypt_control('correct-password', self.credential_unlock_button)
        await self.wait_until(lambda: getattr(self, 'file_provider', None) is not None
                              and self.file_provider.private, 'Unlock did not resume LocalCrypt browsing')
        assert any(row['name'] == 'text.txt' for row in self.file_rows.values())
        assert self.file_source_tabs.parent is None
        assert self.file_source_buttons == {}
        self.localcrypt_result = dict(cold_workspace_unlock=True, wrong_password_retry=True,
            resumed_encrypted_listing=True, duplicate_source_strip_absent=True)

    async def check(self):
        self.sequence = 0
        self.state = dict(success=False, checks={}, phase='cold-localcrypt', sequence=0, action='wait')
        self.publish()
        try:
            await self.check_localcrypt()
            await self.settle_keyboard()
            await super().check()
        except Exception:
            self.state.update(success=False, phase='failed', action='complete', error=traceback.format_exc())
            self.publish()


def main():
    return AndroidPredictiveBackProbe('Predictive Back QA', BUNDLE)
