"""Downloader config parsing and mocked processes; no downloads or pip updates."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from commonUtils.osUtils import OS
from commonUtils.wrappers.cmdShellWrapper import CommandResult
from features.youtube_downloader import settings, downloader, detection


class DownloaderTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.directory = self.root / 'Download Config'
        self.directory.mkdir()
        self.ini = self.directory / 'channel.ini'
        self.write_config()

    def write_config(self, channel='Example Channel', season='10', url='https://example.test/watch?v=one&list=two', extra='--match-filter "duration > 20"'):
        self.ini.write_text(f'[Youtube-DL]\nchannel_name={channel}\nseason_number={season}\ndownload_url={url}\nadditional_params={extra}\n', encoding='utf-8')

    def test_arguments_preserve_quotes_ampersands_and_template_percent(self):
        value = settings.DownloadSettings.read(self.ini)
        argv = settings.download_arguments(value, self.directory, '/Some Path/ffmpeg', playlist_end=3)
        self.assertEqual(argv[-2:], ['--', value.url])
        self.assertIn('duration > 20', argv)
        self.assertEqual(argv[argv.index('--playlist-end') + 1], '3')
        self.assertIn('s10e%(autonumber)s', argv[argv.index('-o') + 1])
        self.assertEqual(argv.count('--no-overwrites'), 1)
        self.assertFalse((self.root / value.channel).exists())

    def test_bom_percent_and_missing_optional_params(self):
        self.ini.write_text('[Youtube-DL]\nchannel_name=Channel\nseason_number=1\ndownload_url=https://example.test/a%20b\n', encoding='utf-8-sig')
        value = settings.DownloadSettings.read(self.ini)
        self.assertEqual(value.additional_arguments, ())
        self.assertIn('%20', value.url)

    def test_invalid_channel_season_url_and_options(self):
        cases = [{'channel': '../escape'}, {'channel': '/absolute'}, {'channel': r'C:\escape'},
                 {'channel': 'CON'}, {'season': '-1'}, {'season': 'one'}, {'url': '--exec=bad'},
                 {'extra': '--title "unclosed'}]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                self.write_config(**kwargs)
                with self.assertRaises(ValueError):
                    settings.DownloadSettings.read(self.ini)

    def test_existing_mp4_count_ignores_folders_and_sidecars(self):
        value = settings.DownloadSettings.read(self.ini)
        destination = value.destination(self.directory)
        destination.mkdir(parents=True)
        (destination / 'Example - s10e01.mp4').touch()
        (destination / 'Example - s10e01.mp4.info.json').touch()
        (destination / 'Example - s10folder.mp4').mkdir()
        argv = settings.download_arguments(value, self.directory, 'ffmpeg')
        self.assertEqual(argv[argv.index('--autonumber-start') + 1], '2')

    def test_invalid_playlist_end(self):
        value = settings.DownloadSettings.read(self.ini)
        for end in (0, -1, True, 1.5):
            with self.subTest(end=end), self.assertRaises(ValueError):
                settings.download_arguments(value, self.directory, 'ffmpeg', playlist_end=end)

    def test_linux_uses_path_without_private_config(self):
        with patch.object(settings, 'get_os', return_value=OS.LINUX), patch.object(settings.shutil, 'which', return_value='/usr/bin/ffmpeg'):
            self.assertEqual(settings.find_ffmpeg(), '/usr/bin/ffmpeg')
        with patch.object(settings, 'get_os', return_value=OS.LINUX), patch.object(settings.shutil, 'which', return_value=None):
            with self.assertRaises(FileNotFoundError):
                settings.find_ffmpeg()

    def test_bundled_windows_ffmpeg_fallback(self):
        executable = self.root / 'ffmpeg_win/ffmpeg.exe'
        executable.parent.mkdir()
        executable.touch()
        with patch.object(settings.shutil, 'which', return_value=None), patch.object(settings, 'get_os', return_value=OS.WIN), patch('config.LogisticsConfig', return_value=SimpleNamespace(path_logistics_software=self.root)):
            self.assertEqual(settings.find_ffmpeg(), str(executable))

    def test_download_success_and_failed_exit(self):
        with patch.object(downloader, 'find_ffmpeg', return_value='ffmpeg'), patch.object(downloader, 'run_command', return_value=CommandResult(0)) as run, patch.object(downloader, 'log'):
            self.assertTrue(downloader.download(self.directory, self.ini))
            self.assertIsInstance(run.call_args.args[0], list)
            self.assertIn('cancelled', run.call_args.kwargs)
            self.assertTrue((self.directory / 'CompleteLists').is_dir())
            run.return_value = CommandResult(1, stderr=('Download failed',))
            self.assertFalse(downloader.download(self.directory, self.ini))

    def test_invalid_config_does_not_launch_process(self):
        self.write_config(channel='../escape')
        with patch.object(downloader, 'run_command', return_value=CommandResult(0)) as run, patch.object(downloader, 'log'):
            self.assertFalse(downloader.download(self.directory, self.ini))
        run.assert_not_called()

    def test_missing_and_empty_batch_do_not_update_packages(self):
        with patch.object(downloader, 'update_yt_dlp') as update, patch.object(downloader, 'log'):
            self.assertFalse(downloader.download_all(self.root / 'missing'))
            self.ini.unlink()
            self.assertTrue(downloader.download_all(self.directory))
        update.assert_not_called()

    def test_batch_continues_and_reports_any_failure(self):
        second = self.directory / 'second.INI'
        second.write_text(self.ini.read_text())
        with patch.object(downloader, 'update_yt_dlp', return_value=False) as update, patch.object(downloader, 'download', side_effect=[False, True]) as download:
            self.assertFalse(downloader.download_all(self.directory))
        update.assert_not_called()
        self.assertEqual(download.call_count, 2)

    def test_updater_timeout_is_nonfatal(self):
        with patch.object(downloader, 'run_command', return_value=CommandResult(-1, timed_out=True)) as run, patch.object(downloader, 'log'):
            self.assertFalse(downloader.update_yt_dlp())
        self.assertEqual(run.call_args.kwargs['timeout'], 180)

    def test_config_sub_path_normalizes_and_rejects_escape(self):
        folder = SimpleNamespace(path=self.root)
        remote = self.root / 'remoteConfig.ini'
        for path in ('../outside', '/absolute', 'C:/absolute', '', '.'):
            with self.subTest(path=path):
                remote.write_text(f'[Youtube-Download]\nconfig_sub_path={path}\n')
                self.assertIsNone(detection.get_config_path(folder))
        remote.write_text('[Youtube-Download]\nconfig_sub_path=Configs\\YouTube\n')
        self.assertEqual(detection.get_config_path(folder), self.root / 'Configs/YouTube')

    def test_channel_symlink_cannot_redirect_downloads_outside_root(self):
        outside = self.root.parent / f'{self.root.name}-outside'
        # A symlink target need not exist for path containment validation.
        (self.root / 'Example Channel').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            settings.DownloadSettings.read(self.ini).destination(self.directory)


    def test_season_sync_filters_names_and_preserves_remote_context(self):
        from features.youtube_downloader import sync
        folder = SimpleNamespace(path=self.root, name='Videos')
        (self.root / 'remoteConfig.ini').write_text('[Youtube-Download]\nconfig_sub_path=Download Config\n')
        for name in ('Season 1', 'Seasonal Extras', 'Old Season 2'):
            (self.root / 'Channel' / name).mkdir(parents=True)
        (self.root / 'Channel/Season 3').symlink_to(self.root / 'Channel/Season 1', target_is_directory=True)
        with patch('features.rclone.sync.rclone_sync') as transfer:
            sync.push_seasons(folder, '/credentials.ini')
        transfer.assert_called_once_with(self.root / 'Channel/Season 1', 'Videos:Channel/Season 1',
                                         config_path='/credentials.ini', wait_for_output=True)

    def test_config_sync_uses_normalized_relative_path(self):
        from features.youtube_downloader import sync
        folder = SimpleNamespace(path=self.root, name='Videos')
        (self.root / 'remoteConfig.ini').write_text('[Youtube-Download]\nconfig_sub_path=Configs\\YouTube\n')
        with patch('features.rclone.sync.rclone_sync') as transfer:
            sync.push_config(folder, '/credentials.ini')
            transfer.assert_called_with(self.root / 'Configs/YouTube', 'Videos:Configs/YouTube', config_path='/credentials.ini')
            sync.pull_config(folder, '/credentials.ini')
            transfer.assert_called_with('Videos:Configs/YouTube', self.root / 'Configs/YouTube', config_path='/credentials.ini')


    def test_numbering_continues_after_highest_episode_despite_gaps(self):
        value = settings.DownloadSettings.read(self.ini)
        destination = value.destination(self.directory)
        destination.mkdir(parents=True)
        for name in ('Example - s10e00002 - title.mp4', 'Example - s10e00009 - title.mp4',
                     'Example - s11e00100 - other.mp4', 'Example - s10e00009 - title.mp4.info.json'):
            (destination / name).touch()
        argv = settings.download_arguments(value, self.directory, 'ffmpeg')
        self.assertEqual(argv[argv.index('--autonumber-start') + 1], '10')
