import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from features.rclone import executable
from features.rclone.transfers import push_policy
from features.rclone.transfers import sync
from tests.local_crypt_fixture import crypt_fixture


class PushPolicyTests(unittest.TestCase):
    def test_settings_and_filter_arguments_are_separate_from_cleanup(self):
        with TemporaryDirectory() as directory, patch.object(push_policy, 'settings_path', return_value=Path(directory) / 'push.json'):
            self.assertIn('.DS_Store', push_policy.load_excludes())
            push_policy.save_excludes(['*.pdf', '.DS_Store', '*.pdf'])
            self.assertEqual(push_policy.load_excludes(), ('*.pdf', '.DS_Store'))
            args = sync.build_sync_arguments('rclone', 'source', 'Remote:', config_path='config', excludes=push_policy.load_excludes())
            self.assertEqual(args[args.index('--exclude'):], ['--exclude', '*.pdf', '--exclude', '.DS_Store', '--', 'source', 'Remote:'])
            self.assertNotIn('--delete-excluded', args)
            with self.assertRaises(ValueError): push_policy.save_excludes(['a\nb'])
            push_policy.save_excludes([])
            self.assertEqual(push_policy.load_excludes(), ())

    def test_cleanup_names_plaintext_masquerade_and_corruption(self):
        binary = executable.get_rclone_path()
        if not binary.is_file(): self.skipTest('Pinned rclone unavailable')
        with TemporaryDirectory() as directory, crypt_fixture(directory, binary) as f:
            junk = f.item.data / '.DS_Store'
            junk.write_bytes(b'generated junk')
            thumb = f.item.data / 'Thumbs.db'
            thumb.write_bytes(b'generated thumb cache')
            self.assertEqual(push_policy.validate_localcrypt_push(f.item, binary), 2)
            self.assertFalse(junk.exists()); self.assertFalse(thumb.exists())
            stray = f.item.data / 'unexpected.txt'
            stray.write_bytes(b'plaintext must never push')
            with self.assertRaisesRegex(ValueError, 'push refused'):
                push_policy.validate_localcrypt_push(f.item, binary)
            self.assertTrue(stray.exists())
            stray.unlink()
            physical = f.provider.encrypted_path('note.md')
            encrypted = physical.read_bytes()
            physical.write_bytes(b'plaintext with a valid encrypted name')
            with self.assertRaises(ValueError): push_policy.validate_localcrypt_push(f.item, binary)
            damaged = bytearray(encrypted); damaged[-1] ^= 1
            physical.write_bytes(damaged)
            with self.assertRaises(ValueError): push_policy.validate_localcrypt_push(f.item, binary)
            physical.write_bytes(encrypted)
            junk.write_bytes(b'preview must not delete')
            with self.assertRaises(ValueError): push_policy.validate_localcrypt_push(f.item, binary, cleanup=False)
            self.assertTrue(junk.exists())
            with self.assertRaises(Exception): push_policy.validate_localcrypt_push(f.item, binary, cancelled=lambda: True)
            self.assertTrue(junk.exists())

    def test_raw_and_decoded_junk_cleanup_preserves_folders_and_other_files(self):
        from io import BytesIO
        from features.rclone import actions
        from features.rclone.localcrypt import backend as local_crypt
        binary = executable.get_rclone_path()
        if not binary.is_file(): self.skipTest('Pinned rclone unavailable')
        with TemporaryDirectory() as directory, crypt_fixture(directory, binary) as f:
            f.provider.mkdir('nested')
            f.provider.mkdir('Thumbs.db')  # A folder is never generated-file cleanup.
            for name in ('.DS_Store', 'nested/tHuMbS.Db', 'nested/keep.pdf'):
                f.provider.create_file(name, BytesIO(b'fixture content'))
            encoded = [f.provider.encrypted_path(name) for name in ('.DS_Store', 'nested/tHuMbS.Db')]
            folder = f.provider._physical('nested', True)
            raw = folder / '.DS_Store'
            raw.write_bytes(b'local Finder junk')
            with patch.object(push_policy, 'load_excludes', return_value=('*.pdf',)):
                self.assertEqual(push_policy.validate_localcrypt_push(f.item, binary), 3)
            self.assertFalse(raw.exists())
            self.assertTrue(all(not path.exists() for path in encoded))
            self.assertTrue(f.provider.entry('Thumbs.db')['directory'])
            self.assertEqual(f.provider.read_bytes('nested/keep.pdf'), b'fixture content')
            self.assertEqual(f.provider.read_bytes('note.md'), f.original)
            # Simulate junk already on the cloud: the ciphertext sync removes it.
            for path in encoded:
                remote = f.cloud / path.relative_to(f.item.data)
                remote.parent.mkdir(parents=True, exist_ok=True)
                remote.write_bytes(b'previous remote junk')
            self.assertTrue(actions.push_to_cloud(local_crypt.LocalCryptFolder(f.item), f.context))
            self.assertTrue(all(not (f.cloud / path.relative_to(f.item.data)).exists() for path in encoded))

    def test_encrypted_junk_preview_cancel_and_corruption_preserve_file(self):
        from io import BytesIO
        binary = executable.get_rclone_path()
        if not binary.is_file(): self.skipTest('Pinned rclone unavailable')
        with TemporaryDirectory() as directory, crypt_fixture(directory, binary) as f:
            f.provider.create_file('.DS_Store', BytesIO(b'old Finder junk'))
            path = f.provider.encrypted_path('.DS_Store')
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'encrypted generated junk'):
                push_policy.validate_localcrypt_push(f.item, binary, cleanup=False)
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(Exception):
                push_policy.validate_localcrypt_push(f.item, binary, cancelled=lambda: True)
            self.assertEqual(path.read_bytes(), before)
            damaged = bytearray(before); damaged[-1] ^= 1
            path.write_bytes(damaged)
            with self.assertRaises(ValueError): push_policy.validate_localcrypt_push(f.item, binary)
            self.assertEqual(path.read_bytes(), damaged)
            path.write_bytes(before)
            from threading import Event
            stopped = Event()
            def cancel_cleanup(done, total, message):
                if message.startswith('Removing encrypted'):
                    stopped.set()
            with self.assertRaises(Exception):
                push_policy.validate_localcrypt_push(f.item, binary, cancelled=stopped.is_set, report=cancel_cleanup)
            self.assertEqual(path.read_bytes(), before)
            replacement = f.provider.encrypted_path('note.md').read_bytes()
            def change_cleanup(done, total, message):
                if message.startswith('Removing encrypted'):
                    path.write_bytes(replacement)
            with self.assertRaisesRegex(ValueError, 'changed'):
                push_policy.validate_localcrypt_push(f.item, binary, report=change_cleanup)
            self.assertEqual(path.read_bytes(), replacement)

    def test_ordinary_push_filters_preserve_excluded_destination_files(self):
        binary = executable.get_rclone_path()
        if not binary.is_file(): self.skipTest('Pinned rclone unavailable')
        real_sync = sync.rclone_sync
        with TemporaryDirectory() as directory, crypt_fixture(directory, binary) as f:
            source = f.root / 'ordinary'; source.mkdir()
            destination = f.root / 'ordinary-cloud'; destination.mkdir()
            (source / '.DS_Store').write_bytes(b'junk')
            (source / 'keep.txt').write_text('push me')
            (source / 'skip.pdf').write_text('exclude me')
            (destination / 'existing.pdf').write_text('preserve me')
            with patch.object(push_policy, 'load_excludes', return_value=('.DS_Store', '*.pdf')):
                self.assertTrue(real_sync(source, 'Cloud:' + str(destination), config_path=f.context,
                                          wait_for_output=True, executable_path=binary))
            self.assertEqual((destination / 'keep.txt').read_text(), 'push me')
            self.assertEqual((destination / 'existing.pdf').read_text(), 'preserve me')
            self.assertFalse((destination / '.DS_Store').exists())
            self.assertFalse((destination / 'skip.pdf').exists())
            self.assertTrue((source / '.DS_Store').exists())

    def test_disabled_content_encryption_is_rejected(self):
        binary = executable.get_rclone_path()
        if not binary.is_file(): self.skipTest('Pinned rclone unavailable')
        with TemporaryDirectory() as directory, crypt_fixture(directory, binary) as f:
            from features.rclone.localcrypt import backend as local_crypt
            values = local_crypt.unlock(f.item)
            values = {name: dict(settings) for name, settings in values.items()}
            values[f.item.remote]['no_data_encryption'] = 'true'
            with patch.object(local_crypt, 'unlock', return_value=values):
                with self.assertRaisesRegex(ValueError, 'requires content encryption'):
                    push_policy.validate_localcrypt_push(f.item, binary)

    def test_invalid_source_never_starts_sync_even_when_excluded(self):
        binary = executable.get_rclone_path()
        if not binary.is_file(): self.skipTest('Pinned rclone unavailable')
        real_sync = sync.rclone_sync
        with TemporaryDirectory() as directory, crypt_fixture(directory, binary) as f:
            (f.item.data / 'skip-me.txt').write_text('unencrypted')
            with patch.object(push_policy, 'load_excludes', return_value=('skip-me.txt',)), patch.object(sync, '_run_sync') as transfer:
                with self.assertRaises(ValueError):
                    real_sync(f.item.data, 'Cloud:' + str(f.cloud), config_path=f.context,
                              wait_for_output=True, executable_path=binary)
                transfer.assert_not_called()


from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt


class PushPolicyUITests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def test_cancelled_preflight_never_launches_transfer(self):
        import time
        from commonUtils.runtime.operations import check_cancelled
        binary = executable.get_rclone_path()
        if not binary.is_file(): self.skipTest('Pinned rclone unavailable')
        real_sync = sync.rclone_sync
        with self.temporary_directory() as directory, crypt_fixture(directory, binary) as f:
            def validate(item, binary, *, cancelled, **kwargs):
                while not cancelled():
                    time.sleep(.01)
                check_cancelled(cancelled)
            def cancel():
                from commonUtils.ui.resources.picker import ResourceTaskDialog
                for widget in self.app.topLevelWidgets():
                    if isinstance(widget, ResourceTaskDialog):
                        widget.reject()
            with patch.object(push_policy, 'validate_localcrypt_push', side_effect=validate), patch.object(sync, '_run_sync') as transfer:
                qt.QTimer.singleShot(40, cancel)
                self.assertFalse(real_sync(f.item.data, 'Cloud:' + str(f.cloud), config_path=f.context,
                                           executable_path=binary))
                transfer.assert_not_called()

    def test_settings_widget_saves_filters_without_changing_cleanup_names(self):
        from features.rclone.transfers.ui.push_settings import PushSettings
        with self.temporary_directory() as directory, patch.object(push_policy, 'settings_path', return_value=Path(directory) / 'rules.json'):
            widget = PushSettings()
            widget.patterns.setPlainText('*.pdf\ncustom.tmp')
            widget.save()
            self.assertEqual(push_policy.load_excludes(), ('*.pdf', 'custom.tmp'))
            self.assertNotIn('*.pdf', push_policy.CLEANUP_NAMES)
            widget.close()
