"""Exercise the selected-file picker and restored Transfers controls on Android."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import traceback
from uuid import uuid4

from commonUtils.runtime.resources.documents import LocalDocuments
from commonUtils.testing.stages import TestStage
from features.rclone.mobile.download_recovery import available_jobs
from mobile.app import LogisticsMobile
from . import start_native_check

TEST_STAGE = TestStage.REGRESSION


async def until(condition, description, seconds=50):
    for _ in range(10 * seconds):
        result = condition()
        if result:
            return result
        await asyncio.sleep(0.1)
    raise AssertionError(description)


class AndroidRecoveryProbe(LogisticsMobile):
    def startup(self):
        self.fixture = Path(self.paths.cache) / 'recovery'
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).exercise)

    def write(self, name, value):
        path = self.fixture / name
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(value))
        temp.replace(path)

    async def host_action(self, action, **args):
        token = uuid4().hex
        self.write('action.json', dict(token=token, action=action, **args))
        ack = self.fixture / ('ack-' + token)
        await until(ack.exists, f'Host did not complete {action}: {args}')
        ack.unlink()

    async def tap(self, button):
        from android.graphics import Rect

        native = button._impl.native
        rect = Rect()
        native.requestRectangleOnScreen(Rect(0, 0, native.getWidth(), native.getHeight()), True)
        await until(
            lambda: button.enabled
            and native.isShown()
            and native.getGlobalVisibleRect(rect)
            and rect.width() > 0
            and rect.height() > 0,
            'Button unavailable: ' + button.text,
        )
        await self.host_action('tap', text=button.text, x=rect.centerX(), y=rect.centerY())

    async def login(self, saved, *, wrong=False):
        package = self.fixture / 'Recovery.zip'
        password = self.config['password'] if not wrong else 'incorrect fixture password'
        names = await asyncio.to_thread(
            self.cloud_client.import_package, LocalDocuments(), package, password, remember=saved
        )
        self.set_loaded_remote_names(names)
        self.cloud_crypt_remotes = set(await asyncio.to_thread(self.cloud_client.crypt_remotes))
        assert any(record['saved'] == saved for record in self.cloud_client.package_records)
        return names

    async def start_picker(self, remote, filename, output):
        from mobile.local_sources import device_files_label
        from services.documents.locations import collection_path
        from services.documents.mobile_locations import enabled, phone_path

        self.routes.return_to('files')
        opened = await self.open_picker_folder(
            dict(kind='remote', value=(remote, ''), source='Remote', remote=remote, name=remote)
        )
        assert opened, (self.cloud_status.value, list(self.cloud_rows))
        row = next(row for row in self.cloud_rows.values() if row['name'] == filename)
        await self.download_remote_item(row)
        picker = self.editor_picker()
        if remote == 'Secret':
            from services.folders.labels import encrypted_copy_label

            label = encrypted_copy_label(remote)
            await picker.browser_editor_location((label, ''))
            picker.save_as_name.value = output
            provider = picker.editor_provider(label)
            try:
                physical = provider.transfer_location(output)
                assert provider.private and physical.name != output
            finally:
                provider.close()
            await self.tap(picker.picker_primary)
            return physical
        shared = enabled(self.private_root)
        base = phone_path(self.private_root) if shared else collection_path(self.private_root)
        folder = 'Recovery acceptance'
        (base / folder).mkdir(parents=True, exist_ok=True)
        await picker.browser_editor_location((device_files_label(self) if shared else 'Local', folder))
        picker.save_as_name.value = output
        await self.tap(picker.picker_primary)
        await self.host_action('dialog', title='Download to unencrypted storage?', accept=True)
        return base / folder / output

    def keystore(self):
        from java import jclass

        vault = self.cloud_client.vault
        keys = vault.keys
        alias = keys.alias(vault.metadata()['id'])
        key = keys.store.getKey(alias, None)
        factory = jclass('javax.crypto.SecretKeyFactory').getInstance(key.getAlgorithm(), 'AndroidKeyStore')
        info = factory.getKeySpec(key, jclass('java.lang.Class').forName('android.security.keystore.KeyInfo'))
        properties = jclass('android.security.keystore.KeyProperties')
        level = info.getSecurityLevel()
        levels = {
            getattr(properties, 'SECURITY_LEVEL_' + name): name
            for name in ('SOFTWARE', 'TRUSTED_ENVIRONMENT', 'STRONGBOX')
        }
        result = dict(
            provider=str(factory.getProvider().getName()),
            security_level=levels.get(level, str(level)),
            reported_secure_hardware=bool(info.isInsideSecureHardware()),
            key_bits=info.getKeySize(),
            exportable=key.getEncoded() is not None,
            user_auth_required=bool(info.isUserAuthenticationRequired()),
            strongbox_feature=bool(
                self._impl.native.getPackageManager().hasSystemFeature('android.hardware.strongbox_keystore')
            ),
            block_modes=[str(value) for value in info.getBlockModes()],
        )
        assert result['provider'] == 'AndroidKeyStore' and not result['exportable'] and result['key_bits'] == 256
        return result

    async def exercise(self):
        report_path = self.fixture / 'state.json'
        report = json.loads(report_path.read_text()) if report_path.exists() else dict(cases={})
        phase_path = self.fixture / 'phase'
        phase = phase_path.read_text().strip() if phase_path.exists() else 'session-start'
        try:
            self.config = json.loads((self.fixture / 'config.json').read_text())
            self.show_cloud(present=False)
            restore = getattr(self, 'cloud_restore_task', None)
            if restore is not None:
                await restore
            await asyncio.sleep(0.4)
            if phase == 'session-start':
                await self.login(False)
                await self.begin_case('session', report)
            else:
                mode = phase.removesuffix('-resume')
                assert mode in ('session', 'saved', 'localcrypt'), phase
                case = report['cases'][mode]
                await self.unlock_case(mode, case)
                await self.resume_case(mode, case)
                self.write('state.json', report)
                if mode == 'session':
                    await self.login(True)
                    await self.begin_case('saved', report)
                elif mode == 'saved':
                    await self.begin_case('localcrypt', report)
                else:
                    target = await self.start_picker('Unsupported', 'restart.bin', 'declined.bin')
                    await self.host_action('dialog', title='Download from byte zero?', accept=False)
                    assert not target.exists()
                    report.update(success=True, declined_unsupported=True)
                    self.write_result(report)
        except Exception:
            report.update(success=False, phase=phase, error=traceback.format_exc())
            self.write_result(report)

    def control(self, prefix):
        buttons = self.transfer_view.native_fallback.buttons.children
        return next((button for button in buttons if button.text.startswith(prefix)), None)

    async def unlock_case(self, mode, case):
        case['resumed_pid'] = os.getpid()
        assert case['resumed_pid'] != case['initial_pid']
        if mode != 'session':
            await asyncio.to_thread(self.cloud_client.lock)
        assert not await asyncio.to_thread(available_jobs, self)
        self.show_transfers()
        assert not any(
            b.text.startswith(('Resume ', 'Interrupted downloads'))
            for b in self.transfer_view.native_fallback.buttons.children
        )
        case['locked_rows'] = 0
        if mode == 'session':
            try:
                await self.login(False, wrong=True)
            except (OSError, ValueError):
                pass
            else:
                raise AssertionError('Wrong ZIP password admitted')
            assert not await asyncio.to_thread(available_jobs, self)
            case['wrong_password_refused'] = True
            await self.login(False)
        else:
            names = await asyncio.to_thread(self.cloud_client.restore)
            assert 'Ranged' in names
            self.set_loaded_remote_names(names)
            self.cloud_crypt_remotes = set(await asyncio.to_thread(self.cloud_client.crypt_remotes))
            case['restored_from_android_vault'] = True
            case['keystore'] = self.keystore()

    async def resume_case(self, mode, case):
        self.show_transfers()

        await self.tap(
            await until(lambda: self.control('Interrupted downloads'), 'Missing interrupted-download control')
        )
        resume = await until(lambda: self.control('Resume '), 'No restored row')
        case['row'] = resume.text
        case['status'] = self.transfer_view.native_fallback.status.text
        assert 'after unlocking' not in case['status']
        from android.view import WindowManager
        flags = self._impl.native.getWindow().getAttributes().flags
        case['secure_window'] = bool(flags & WindowManager.LayoutParams.FLAG_SECURE)
        assert f'{self.config["stop"]:,}' in resume.text and f'{self.config["size"]:,}' in resume.text, (
            resume.text
        )
        epoch = self.transfer_epoch
        await self.tap(resume)
        await until(
            lambda: self.transfer_epoch != epoch and not self.transfer_busy,
            'Restored transfer did not finish',
        )
        assert self.transfer_complete, self.transfer_message
        with Path(case['target']).open('rb') as stream:
            physical_digest = (await asyncio.to_thread(file_digest, stream, 'sha256')).hexdigest()
        if mode == 'localcrypt':
            case['ciphertext_sha256'] = physical_digest
            assert physical_digest == self.config['ciphertext_sha256']
            case['sha256'] = await asyncio.to_thread(self.decrypted_digest)
        else:
            case['sha256'] = physical_digest
        assert case['sha256'] == self.config['sha256']
        assert not await asyncio.to_thread(available_jobs, self)
        Path(case.pop('target')).unlink()

    async def begin_case(self, mode, report):
        await self.host_action('arm', mode=mode)
        target = await self.start_picker(
            'Secret' if mode == 'localcrypt' else 'Ranged', 'selected.bin', mode + '.bin'
        )
        assert not target.exists()
        report['cases'][mode] = dict(initial_pid=os.getpid(), target=str(target))
        self.write('state.json', report)
        await self.host_action('can-stop', mode=mode)
        # The host force-stops the process with the next GET held before its body.
        await asyncio.sleep(100)
        raise AssertionError('The owned Android process was not stopped at the checkpoint')

    def decrypted_digest(self):
        from features.rclone.localcrypt.mobile.resources import encrypted_storage

        provider = encrypted_storage(self.private_root, self.cloud_client, 'Secret', create=False)
        try:
            digest = sha256()
            with provider.open('localcrypt.bin') as stream:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
            return digest.hexdigest()
        finally:
            provider.close()

    def write_result(self, report):
        (Path(self.paths.cache) / 'download-recovery-result.json').write_text(json.dumps(report, indent=2))


def main():
    return AndroidRecoveryProbe('Download Recovery QA', 'io.github.ispaure.logisticsnotebookqa')
