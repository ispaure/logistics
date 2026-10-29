"""Local resources and lazy software provisioning without external transfers."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
from contextlib import contextmanager
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
    @contextmanager
    def resource_config(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, home = root / 'Python', root / 'home'
            source.mkdir(); home.mkdir()
            fake_module = source / 'config.py'
            fake_module.touch()
            (source / 'configFile.ini').write_text(
                '[DirectoryStructure]\nserver_path_macos=Server\n'
                'remote_network_mount_sub_path=Mounts\nremote_local_sub_path=Local\n')
            with patch.object(config, '__file__', str(fake_module)), \
                    patch.object(config, 'get_os', return_value=OS.MAC), \
                    patch.object(Path, 'home', return_value=home):
                yield root, home

    def test_software_lookup_does_not_create_software_or_credential_directories(self):
        with self.resource_config() as (root, home), \
                patch.object(software, 'get_os', return_value=OS.MAC), \
                patch.object(software, 'get_arch', return_value=Arch.ARM_64):
            _, destination = software.get_software('rclone')
            self.assertTrue(destination.is_relative_to(root / 'Software'))
            self.assertFalse((root / 'Software').exists())
            self.assertFalse((root / 'Credentials').exists())

    def test_location_and_connection_metadata_do_not_create_resource_directories(self):
        from desktop.location_context import LocationCatalog
        from features.rclone.localcrypt.connections import storage_root
        from commonUtils.ui import pyside as qt
        self.app = qt.QApplication.instance() or qt.QApplication([])
        for lookup in ('location', 'connection'):
            with self.subTest(lookup=lookup), self.resource_config() as (root, home):
                expected = home / 'Server/Local'
                if lookup == 'connection':
                    self.assertEqual(storage_root(), expected.absolute())
                else:
                    catalog = LocationCatalog(None)
                    try:
                        context = catalog.local(expected / 'Library' / 'guide.txt')
                        self.assertEqual(context.name, 'Library')
                    finally:
                        catalog.deleteLater()
                self.assertFalse((root / 'Software').exists())
                self.assertFalse((root / 'Credentials').exists())

    def test_folder_discovery_keeps_local_bootstrap_without_creating_unrelated_resources(self):
        from models.folder_discovery import get_local_folders
        with self.resource_config() as (root, home):
            self.assertEqual(get_local_folders(), [])
            local = home / 'Server/Local'
            self.assertTrue(local.is_dir())
            (local / 'Example').mkdir()
            self.assertEqual([folder.path for folder in get_local_folders()], [local / 'Example'])
            self.assertFalse((root / 'Software').exists())
            self.assertFalse((root / 'Credentials').exists())

    def test_plex_and_mount_path_queries_create_no_resource_folders(self):
        from features.plex.folders import get_local_pms_data_folder, get_remote_pms_data_folder, get_pms_data_name
        from features.fuse.mounts import get_remote_mount_path
        from models.local_folder import LocalFolder
        with self.resource_config() as (root, home):
            folder = LocalFolder(home / 'Example')
            self.assertEqual(get_local_pms_data_folder(folder).path, home / 'Server/Local' / get_pms_data_name(folder))
            self.assertEqual(get_remote_pms_data_folder(folder).path, home / 'Server/Mounts' / get_pms_data_name(folder))
            self.assertEqual(get_remote_mount_path('Example'), home / 'Server/Mounts/Example')
            self.assertFalse((home / 'Server').exists())
            self.assertFalse((root / 'Software').exists())
            self.assertFalse((root / 'Credentials').exists())

    def test_ffmpeg_bundled_lookup_does_not_create_resource_folders(self):
        from features.youtube_downloader import settings
        with self.resource_config() as (root, home), \
                patch.object(settings.shutil, 'which', return_value=None), \
                patch.object(settings, 'get_os', return_value=OS.MAC):
            with self.assertRaises(FileNotFoundError):
                settings.find_ffmpeg()
            self.assertFalse((root / 'Software').exists())
            self.assertFalse((root / 'Credentials').exists())
            executable = root / 'Software/ffmpeg_macos/ffmpeg'
            executable.parent.mkdir(parents=True)
            executable.touch()
            self.assertEqual(settings.find_ffmpeg(), str(executable))
            self.assertFalse((root / 'Credentials').exists())

    def test_manifest_covers_six_platforms_with_pinned_hashes(self):
        with TemporaryDirectory() as root:
            with patch.object(software.config, 'LogisticsConfig', return_value=SimpleNamespace(path_logistics_software=Path(root))):
                for platform in (OS.WIN, OS.MAC, OS.LINUX):
                    for arch in (Arch.X86_64, Arch.ARM_64):
                        with patch.object(software, 'get_os', return_value=platform), patch.object(software, 'get_arch', return_value=arch):
                            spec, path = software.get_software('rclone')
                        self.assertEqual(spec.version, '1.74.1')
                        self.assertTrue(path.is_relative_to(root))
                        self.assertIn(platform.value, path.parts)
                        self.assertEqual(len(spec.sha256), 64)
                        self.assertEqual(len(spec.installed_sha256), 64)

    def test_rclone_feature_manifest_and_native_pins_agree(self):
        import configparser
        import json
        repo = Path(__file__).resolve().parents[3]
        manifest = json.loads((repo / 'Python/software_manifest.json').read_text())['rclone']
        settings = configparser.ConfigParser()
        settings.read(repo / 'Python/features/rclone/config.ini')
        for platform, values in manifest.items():
            for key in ('version', 'url', 'path', 'archive_member', 'sha256', 'installed_sha256'):
                self.assertEqual(settings[platform][key + '_str'], values[key])
            self.assertEqual(values['version'], '1.74.1')
        native = (repo / 'mobile_build/rclone_bridge/go.mod').read_text()
        self.assertIn('github.com/rclone/rclone v1.74.1', native)
        self.assertIn('fs.Version=v1.74.1', (repo / 'mobile_build/cloud_build.py').read_text())

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
                self.assertEqual(cfg.path_logistics_remote_cred, root / 'Credentials/rclone')

    def test_declining_rclone_does_not_launch_sync_or_create_destination(self):
        from features.rclone.transfers import sync
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
        from commonUtils.ui.tasks import download
        self.app = qt.QApplication.instance() or qt.QApplication([])
        spec = DownloadSpec('Tool','1','https://example.test/tool','0'*64,'0'*64)
        with patch.object(download, 'is_ready', return_value=False), patch.object(qt, 'display_msg_box_yes_no', return_value=False), patch.object(download, '_DownloadDialog') as dialog:
            self.assertIsNone(download.ensure_download(spec, Path('/tool')))
        dialog.assert_not_called()

    def test_background_download_dialog_returns_verified_path(self):
        from commonUtils.ui import pyside as qt
        from commonUtils.ui.tasks import download
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
        from commonUtils.ui.tasks import download
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
        from commonUtils.ui.tasks import download
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
