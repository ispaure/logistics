"""Disposable reset app. Never launch this harness under the production bundle."""
import asyncio
import json
from pathlib import Path
import traceback
from unittest.mock import patch

import mobile
from mobile.app import LogisticsMobile
from mobile.app_reset import RESET_MARKER
from commonUtils.runtime.platform import get_os, OS
from commonUtils.runtime.protected_keys import IOSKeys, AndroidKeys, KeyStoreUnavailable
from .fixtures import capture_window
from mobile.screen_privacy import native_value

BUNDLE = 'io.github.ispaure.logisticsresetqa'
IDENTITY = 'd6d11e31c8ce45e7b5f5679a4d39d15b'
KEY = bytes(range(32))


def ios_key(service):
    return IOSKeys(service=service, label='Logistics disposable reset test', label_prefix='Reset QA:')


class Audit(LogisticsMobile):
    def startup(self):
        try:
            super().startup()
        except BaseException:
            path = Path(self.paths.cache)
            path.mkdir(parents=True, exist_ok=True)
            (path / 'reset-startup-error.txt').write_text(traceback.format_exc())
            raise

    def on_running(self):
        self.loop.create_task(self.audit())

    async def audit(self):
        report = dict(success=False, source=json.loads(Path(mobile.__file__).with_name('source.json').read_text()))
        output = Path(self.paths.cache) / 'reset-audit'
        output.mkdir(exist_ok=True)
        try:
            ios = get_os() is OS.IOS
            if ios:
                import os
                from rubicon.objc import ObjCClass
                assert str(native_value(native_value(ObjCClass('NSBundle'), 'mainBundle'), 'bundleIdentifier')) == BUNDLE
                phase = os.environ.get('LOGISTICS_RESET_AUDIT_PHASE', 'seed')
            else:
                assert str(self._impl.native.getPackageName()) == BUNDLE
                phase = str(self._impl.native.getIntent().getStringExtra('reset_phase') or 'seed')
            report['phase'] = phase
            if phase == 'seed':
                self.preferences.save(font_size='28')
                self.create_chosen_document('md')
                self.name.value = 'Reset QA unsaved.md'
                self.editor.value = '# Disposable unsaved draft'
                assert self.checkpoint()
                for root in (self.private_root, Path(self.paths.config), Path(self.paths.cache), Path(self.paths.data)):
                    root.mkdir(parents=True, exist_ok=True)
                    (root / 'reset-qa-file.txt').write_text('erase this')
                if ios:
                    defaults = native_value(ObjCClass('NSUserDefaults'), 'standardUserDefaults')
                    defaults.setObject('erase this', forKey='LogisticsResetQA')
                    for service in ('io.github.ispaure.logisticsmobile.credentials', 'io.github.ispaure.logisticsmobile.packages', BUNDLE + '.other'):
                        keys = ios_key(service)
                        keys.delete(IDENTITY)
                        keys.create(IDENTITY, KEY)
                else:
                    keys = AndroidKeys(alias_prefix='Logistics.resetqa.', aad_prefix='Reset QA:')
                    keys.delete(IDENTITY)
                    keys.create(IDENTITY, KEY)
                    report['storage'] = await self.storage_audit(output)
                self.settings_navigation.choose('Reset')
                await asyncio.sleep(.2)
                await capture_window(self, output / 'reset-category.png')
                self.show_app_reset()
                await asyncio.sleep(.4)
                await capture_window(self, output / 'reset-scope.png')
                scroll = self.routes.body('settings').children[0]
                scroll.vertical_position = scroll.max_vertical_position
                await asyncio.sleep(.4)
                await capture_window(self, output / 'reset-confirmation-input.png')
                assert not self.reset_button.enabled
                if ios:
                    self.reset_phrase.value = 'ERASE'
                    assert self.reset_button.enabled
                    await self.accept_dialogs(self.confirm_app_reset(), output, 'reset-final-confirmation')
                    assert (self.private_root / RESET_MARKER).is_file()
                    assert self._reset_scheduled and not self.active_host
                    assert self.checkpoint() and self.exit_app(self)
                    await capture_window(self, output / 'reset-restart-notice.png')
                report['ready_for_reset'] = True
            else:
                assert phase == 'after'
                assert not (self.private_root / RESET_MARKER).exists()
                assert self.preferences.values['font_size'] != '28'
                assert self.store.documents() == ([], [])
                for root in (self.private_root, Path(self.paths.config), Path(self.paths.cache), Path(self.paths.data)):
                    assert not (root / 'reset-qa-file.txt').exists(), str(root)
                if ios:
                    from rubicon.objc import ObjCClass
                    assert native_value(ObjCClass('NSUserDefaults'), 'standardUserDefaults').objectForKey('LogisticsResetQA') is None
                    for service in ('io.github.ispaure.logisticsmobile.credentials', 'io.github.ispaure.logisticsmobile.packages'):
                        try:
                            ios_key(service).load(IDENTITY, {})
                        except KeyStoreUnavailable:
                            pass
                        else:
                            raise AssertionError('A Logistics Keychain key survived reset')
                    other = ios_key(BUNDLE + '.other')
                    assert other.load(IDENTITY, {}) == KEY
                    other.delete(IDENTITY)
                    report['unrelated_keychain_service_preserved'] = True
                else:
                    keys = AndroidKeys(alias_prefix='Logistics.resetqa.', aad_prefix='Reset QA:')
                    assert not keys.store.containsAlias(keys.alias(IDENTITY))
                    card = Path('/storage/emulated/0/LogisticsResetQA')
                    assert (card / 'Logistics/Local/keep-after-reset.txt').read_text() == 'shared files stay'
                    report['shared_collection_preserved'] = True
                report['files_config_metadata_and_keys_erased'] = True
                await capture_window(self, output / 'reset-fresh-home.png')
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print('LOGISTICS_RESET_AUDIT=' + json.dumps(report), flush=True)

    async def accept_dialogs(self, action, output, name):
        original = self.main_window.dialog
        index = 0
        async def accept(dialog):
            nonlocal index
            task = asyncio.create_task(original(dialog))
            await asyncio.sleep(.35)
            index += 1
            await capture_window(self, output / (name + '-' + str(index) + '.png'))
            if get_os() is OS.IOS:
                dialog._impl.native.dismissViewControllerAnimated(False, completion=None)
                dialog._impl.response(True)
            else:
                dialog._impl.native.getButton(-1).performClick()
            return await task
        with patch.object(self.main_window, 'dialog', side_effect=accept):
            return await action

    async def storage_audit(self, output):
        from features.rclone.mobile.storage_location import collection_path, selection
        from mobile import storage_ui
        card = Path('/storage/emulated/0/LogisticsResetQA')
        card.mkdir(exist_ok=True)
        old = collection_path(self.private_root)
        old.mkdir(exist_ok=True)
        (old / 'internal-original.txt').write_text('original')
        crypt = collection_path(self.private_root, True)
        crypt.mkdir(exist_ok=True)
        (crypt / 'ciphertext.bin').write_bytes(b'opaque encrypted fixture')
        with patch.object(storage_ui, 'android_drives', return_value={'App internal storage': None, 'QA shared drive': card}), patch.object(self, 'exit', return_value=None):
            self.show_collection_storage()
            self.collection_drive.value = 'QA shared drive'
            await asyncio.sleep(.3)
            await capture_window(self, output / 'storage-options.png')
            await self.accept_dialogs(self.change_collection_storage(), output, 'storage-copy')
            assert selection(self.private_root)['volume'] == str(card)
            assert (card / 'Logistics/Local/internal-original.txt').read_text() == 'original'
            assert (old / 'internal-original.txt').is_file()
            self.collection_drive.value = 'App internal storage'
            await self.accept_dialogs(self.recover_collection_storage(), output, 'storage-existing')
            assert selection(self.private_root) is None
            self.collection_drive.value = 'QA shared drive'
            await self.accept_dialogs(self.wipe_collection_storage(), output, 'storage-erase')
            assert not (card / 'Logistics/Local').exists()
            assert (old / 'internal-original.txt').is_file()
            await self.accept_dialogs(self.start_empty_collection(), output, 'storage-empty')
            assert selection(self.private_root)['volume'] == str(card)
            assert not list((card / 'Logistics/Local').iterdir())
            (card / 'Logistics/Local/keep-after-reset.txt').write_text('shared files stay')
            assert (self.private_root / 'reset-qa-file.txt').is_file()
        return dict(copy_verified=True, existing_switch_without_copy=True, inactive_erase_scoped=True,
                    start_empty_keeps_originals=True, private_data_preserved=True)


def main():
    return Audit('Logistics Reset QA', BUNDLE)
