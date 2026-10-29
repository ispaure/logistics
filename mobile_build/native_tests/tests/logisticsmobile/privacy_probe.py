"""Synthetic resume-lock probe for an isolated simulator/emulator bundle.

When phase is ``await_background``, launch Settings and return to this probe.
No user credentials, files or network connections are used.
"""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import base64
import json
import os
from pathlib import Path
import traceback
from uuid import uuid4

from mobile.app import LogisticsMobile
from .fixtures import capture_window

BUNDLE = 'io.github.ispaure.logisticsprivacyprobe'
PASSWORD = 'synthetic-session-password'


class PrivacyProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'privacy-probe-workspace'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        output = Path(self.paths.cache) / 'privacy-probe-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False, cases=[], phase='starting')
        def publish():
            (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        try:
            self.show_cloud(present=False)
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
            privacy = self.screen_privacy
            assert not privacy.sensitive()
            fixture = json.loads(Path(__file__).with_name('localcrypt_fixture.json').read_text())
            self.cloud_client.request('import', package=fixture['package'], password=PASSWORD,
                package_name='Synthetic.zip', session_only=True)
            await asyncio.sleep(.1)
            assert privacy.sensitive()
            report['cases'].append('session_load_activates_privacy_before_view')
            item = fixture['copies']['note.md']
            folder = self.crypt_copies.root / item['key']
            folder.mkdir(exist_ok=True)
            (folder / 'data').write_bytes(base64.b64decode(item['ciphertext']))
            (folder / 'record.json').write_text(json.dumps(item['record']))
            assert await self.open_crypt(copies=self.crypt_copies, key=item['key'])
            owner = self.private_sessions.active
            owner.crypt_text.value = 'Synthetic unsaved private draft'
            original = self.main_window.content
            privacy.conceal()
            privacy.reveal()
            assert self.main_window.content is privacy.lock_view
            self.show_settings()
            assert self.main_window.content is privacy.lock_view
            privacy.lock_password.value = 'wrong'
            await privacy.unlock()
            assert self.main_window.content is privacy.lock_view
            await capture_window(self, output / 'locked.png')
            privacy.lock_password.value = PASSWORD
            await privacy.unlock()
            assert self.main_window.content is original
            assert owner.crypt_text.value == 'Synthetic unsaved private draft'
            report['cases'].append('native_root_lock_wrong_password_and_draft_resume')
            if privacy.backend.startswith('toga_android.'):
                assert self._impl.native.getWindow().getAttributes().flags & 0x2000
                report['cases'].append('android_secure_flag')
            report['phase'] = 'await_background'
            publish()
            for _ in range(600):
                await asyncio.sleep(.1)
                if self.cloud_client.session_privacy.locked and not privacy.inactive:
                    break
            else:
                raise AssertionError('Launch Settings and return to test actual OS lifecycle')
            assert self.main_window.content is privacy.lock_view
            await capture_window(self, output / 'returned-locked.png')
            privacy.lock_password.value = PASSWORD
            await privacy.unlock()
            assert self.main_window.content is original
            assert owner.crypt_text.value == 'Synthetic unsaved private draft'
            report['cases'].append('os_background_return_requires_password')
            await self.show_crypt_save_as(owner=owner)
            self.save_as_name.value = 'exported-' + uuid4().hex + '.md'
            await self.save_text_destination()
            assert self.save_as_data is None, self.save_as_status.value
            exported = self.private_sessions.active
            assert exported is not owner and exported.privacy_gate is owner.privacy_gate
            assert self.private_sessions.close(owner.session.id, discard=True)
            assert privacy.sensitive()
            self.cloud_client.lock()
            await asyncio.sleep(.2)
            assert privacy.sensitive()
            privacy.conceal()
            privacy.reveal()
            assert self.main_window.content is privacy.lock_view
            privacy.lock_password.value = PASSWORD
            await privacy.unlock()
            assert exported.crypt_text.value == 'Synthetic unsaved private draft'
            assert self.private_sessions.close(exported.session.id, discard=True)
            assert not privacy.sensitive()
            if privacy.backend.startswith('toga_android.'):
                assert not self._impl.native.getWindow().getAttributes().flags & 0x2000
            report['cases'].append('protection_released_after_credentials_and_views_clear')
            report.update(success=True, phase='complete')
        except Exception:
            report['error'] = traceback.format_exc()
            traceback.print_exc()
        publish()
        print('PRIVACY_RESULT=' + json.dumps(report), flush=True)
        await asyncio.sleep(.2)
        os._exit(0 if report['success'] else 1)


def main():
    return PrivacyProbe('Privacy validation', BUNDLE)


if __name__ == '__main__':
    main().main_loop()
