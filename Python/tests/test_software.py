"""Local resources and lazy software provisioning without external transfers."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
from types import SimpleNamespace

import config
from commonUtils.runtime.platform import OS, Arch
from commonUtils.runtime.streams.downloads import DownloadSpec
from services import software


class SoftwareTests(QtTestCase):
    def test_manifest_covers_six_platforms_with_pinned_hashes(self):
        with TemporaryDirectory() as root:
            with patch.object(software.config, 'LogisticsConfig', return_value=SimpleNamespace(path_logistics_software=Path(root))):
                for platform in (OS.WIN, OS.MAC, OS.LINUX):
                    for arch in (Arch.X86_64, Arch.ARM_64):
                        with patch.object(software, 'get_os', return_value=platform), patch.object(software, 'get_arch', return_value=arch):
                            spec, path = software.get_software('rclone')
                        self.assertEqual(spec.version, '1.73.1')
                        self.assertTrue(path.is_relative_to(root))
                        self.assertIn(platform.value, path.parts)
                        self.assertEqual(len(spec.sha256), 64)
                        self.assertEqual(len(spec.installed_sha256), 64)

    def test_rclone_ini_overrides_and_required_hash_validation(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = root / 'config.ini'
            settings.write_text('[osx-arm64]\nversion_str = test-version\nsha256_str = ' + 'a'*64 + '\n')
            with patch.object(software, 'RCLONE_CONFIG_PATH', settings), \
                    patch.object(software, 'get_os', return_value=OS.MAC), \
                    patch.object(software, 'get_arch', return_value=Arch.ARM_64), \
                    patch.object(software.config, 'LogisticsConfig', return_value=SimpleNamespace(path_logistics_software=root)):
                spec, destination = software.get_software('rclone')
                self.assertEqual(spec.version, 'test-version')
                self.assertEqual(spec.sha256, 'a'*64)
                self.assertEqual(len(spec.installed_sha256), 64)
                settings.write_text('[osx-arm64]\nsha256_str = invalid\n')
                with self.assertRaisesRegex(ValueError, 'SHA-256'):
                    software.get_software('rclone')
                settings.write_text('[osx-arm64]\npath_str = ../outside\n')
                with self.assertRaisesRegex(ValueError, 'inside'):
                    software.get_software('rclone')

    def test_empty_root_resources_and_independent_overrides(self):
        with TemporaryDirectory() as root:
            root = Path(root).resolve()
            source = root / 'Python'
            source.mkdir()
            fake_module = source / 'config.py'
            fake_module.touch()
            ini = source / 'configFile.ini'
            ini.write_text('[DirectoryStructure]\nserver_path_macos=Server\nremote_network_mount_sub_path=Mounts\nremote_local_sub_path=Local\n')
            with patch.object(config, '__file__', str(fake_module)), patch.object(config, 'get_os', return_value=OS.MAC):
                cfg = config.LogisticsConfig()
                self.assertEqual(cfg.path_logistics_software, root / 'Software')
                self.assertTrue(cfg.path_logistics_remote_cred.is_dir())
                self.assertEqual(list(cfg.path_logistics_remote_cred.iterdir()), [])
                ini.write_text(ini.read_text() + '[Resources]\nsoftware_path=AlternateSoftware\n')
                cfg = config.LogisticsConfig()
                self.assertEqual(cfg.path_logistics_software, root / 'AlternateSoftware')
                self.assertEqual(cfg.path_logistics_remote_cred, root / 'RemoteCredentials')

    def test_declining_rclone_does_not_launch_sync_or_create_destination(self):
        from features.rclone import sync
        with TemporaryDirectory() as root:
            destination = Path(root) / 'not-created'
            with patch.object(sync.executable, 'ensure_rclone', return_value=None), patch.object(sync.cmdShellWrapper, 'exec_cmd') as command:
                self.assertFalse(sync.rclone_sync('Remote:', destination, config_path='/private.conf'))
            command.assert_not_called()
            self.assertFalse(destination.exists())

    def test_existing_configs_do_not_require_credential_zips(self):
        from features.rclone import configuration, credentials
        with TemporaryDirectory() as root:
            path = Path(root) / 'Personal.conf'
            path.write_text('[Media]\ntype=local\n')
            with patch.object(configuration, 'get_rclone_config_dir', return_value=Path(root)), patch.object(credentials.config, 'LogisticsConfig', side_effect=AssertionError('ZIP discovery must not run')):
                self.assertEqual(credentials.get_loaded_credential_config_paths(), [path])

    def test_declining_fuse_installer_does_not_launch_it(self):
        from features.fuse import actions
        with patch.object(actions.detection, 'get_installer_path', return_value=Path('/missing.msi')), patch.object(actions, 'get_os', return_value=OS.WIN), patch.object(actions.software, 'ensure_software', return_value=None), patch.object(actions.subprocess, 'Popen') as launch:
            self.assertFalse(actions.launch_installer())
        launch.assert_not_called()

    def test_download_prompt_decline_returns_without_network(self):
        from commonUtils.ui import pyside as qt
        from commonUtils.ui import download
        self.app = qt.QApplication.instance() or qt.QApplication([])
        spec = DownloadSpec('Tool','1','https://example.test/tool','0'*64,'0'*64)
        with patch.object(download, 'is_ready', return_value=False), patch.object(qt, 'display_msg_box_yes_no', return_value=False), patch.object(download, '_DownloadDialog') as dialog:
            self.assertIsNone(download.ensure_download(spec, Path('/tool')))
        dialog.assert_not_called()

    def test_background_download_dialog_returns_verified_path(self):
        from commonUtils.ui import pyside as qt
        from commonUtils.ui import download
        self.app = qt.QApplication.instance() or qt.QApplication([])
        spec = DownloadSpec('Tool','1','https://example.test/tool','0'*64,'0'*64)
        with patch.object(download, 'provision', return_value=Path('/verified/tool')):
            dialog = download._DownloadDialog(spec, Path('/tool'))
            dialog.exec()
            self.assertEqual(dialog.result_path, Path('/verified/tool'))
            self.assertFalse(dialog.running)
            dialog.deleteLater()

    def test_download_dialog_cancellation_waits_for_worker(self):
        import time
        from commonUtils.ui import pyside as qt
        from commonUtils.ui import download
        from commonUtils.runtime.streams.downloads import DownloadCancelled
        self.app = qt.QApplication.instance() or qt.QApplication([])
        spec = DownloadSpec('Tool','1','https://example.test/tool','0'*64,'0'*64)
        def work(*args, cancelled, **kwargs):
            deadline = time.monotonic() + 3
            while not cancelled():
                if time.monotonic() > deadline:
                    raise RuntimeError('Test did not cancel')
                time.sleep(.005)
            raise DownloadCancelled('cancelled')
        with patch.object(download, 'provision', side_effect=work):
            dialog = download._DownloadDialog(spec, Path('/tool'))
            qt.QTimer.singleShot(20, dialog.reject)
            dialog.exec()
            self.assertTrue(dialog.cancelled.is_set())
            self.assertFalse(dialog.running)
            self.assertIsNone(dialog.result_path)
            dialog.deleteLater()

    def test_download_failure_is_not_hidden_by_a_late_cancel_request(self):
        from commonUtils.ui import pyside as qt
        from commonUtils.ui import download
        self.app = qt.QApplication.instance() or qt.QApplication([])
        spec = DownloadSpec('Tool','1','https://example.test/tool','0'*64,'0'*64)
        with patch.object(download, 'provision', side_effect=ValueError('SHA-256 verification failed')):
            dialog = download._DownloadDialog(spec, Path('/tool'))
            # Request cancellation before queued worker completion is processed.
            dialog.task.cancelled.set()
            with patch.object(download, 'is_ready', return_value=False), \
                    patch.object(qt, 'display_msg_box_yes_no', return_value=True), \
                    patch.object(download, '_DownloadDialog', return_value=dialog), \
                    patch.object(qt, 'display_msg_box_ok') as message:
                self.assertIsNone(download.ensure_download(spec, Path('/tool')))
                message.assert_called_once()
                self.assertIn('SHA-256 verification failed', message.call_args.args[1])
