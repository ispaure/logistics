"""Plex database copies, package staging and simulated platform operations."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from commonUtils.osUtils import OS
from features.plex import database, packages, actions, detection


class PlexDatabaseTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name).resolve() / 'library.db'
        with sqlite3.connect(self.path) as connection:
            connection.executescript('''
                CREATE TABLE metadata_items (id INTEGER, metadata_type INTEGER, library_section_id INTEGER,
                    parent_id INTEGER, guid TEXT, title TEXT, year INTEGER, hash TEXT, "index" INTEGER, deleted_at INTEGER);
                CREATE TABLE media_items (id INTEGER, metadata_item_id INTEGER, duration INTEGER);
                CREATE TABLE media_parts (media_item_id INTEGER, file TEXT, hash TEXT);
                CREATE TABLE library_sections (id INTEGER, section_type INTEGER, language TEXT);
                INSERT INTO library_sections VALUES (1, 1, 'en'), (2, 1, 'xn');
                INSERT INTO metadata_items VALUES
                    (1, 1, 1, NULL, 'movie', 'Movie', 2020, NULL, NULL, NULL),
                    (2, 2, 3, NULL, 'show', 'Show', 2020, NULL, NULL, NULL),
                    (3, 3, 3, 2, NULL, 'Season', 2020, NULL, 0, NULL),
                    (4, 4, 3, 3, NULL, 'Special', 2020, NULL, 1, NULL),
                    (5, 4, 3, 999, NULL, 'Orphan', 2020, NULL, 2, NULL),
                    (6, 1, 2, NULL, 'video', 'Other', 2020, NULL, NULL, NULL),
                    (7, 1, 1, NULL, 'deleted', 'Deleted', 2020, NULL, NULL, 1);
                INSERT INTO media_items VALUES (10, 1, 43200000), (11, 4, 1000);
                INSERT INTO media_parts VALUES (10, '/movie.mp4', 'abc'), (11, '/special.mp4', 'def');
            ''')

    def test_read_only_connection_and_missing_file(self):
        connection = database._connect(self.path)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute('DELETE FROM media_items')
        finally:
            connection.close()
        missing = self.path.with_name('missing.db')
        with self.assertRaises(FileNotFoundError):
            database.get_plex_db_table_media_items(missing)
        self.assertFalse(missing.exists())

    def test_optional_columns_are_none_and_required_columns_fail(self):
        self.assertIsNone(database.get_plex_db_table_metadata_items(self.path)[0]['edition_title'])
        with sqlite3.connect(self.path) as connection:
            connection.execute('ALTER TABLE media_items RENAME COLUMN metadata_item_id TO broken')
        with self.assertRaisesRegex(ValueError, 'missing required columns'):
            database.get_plex_db_table_media_items(self.path)

    def test_fractional_duration_and_empty_database(self):
        self.assertAlmostEqual(database.get_plex_db_total_duration_days(self.path), 0.5 + 1000 / 86400000)
        with sqlite3.connect(self.path) as connection:
            connection.execute('DELETE FROM media_items')
        self.assertEqual(database.get_plex_db_total_duration_days(self.path), 0)

    def test_movie_other_filters_and_deleted_items(self):
        self.assertEqual([item.title for item in database.get_metadata_item_cls_lst(self.path, 'Movies')], ['Movie'])
        self.assertEqual([item.title for item in database.get_metadata_item_cls_lst(self.path, 'Other Videos')], ['Other'])
        with self.assertRaises(ValueError):
            database.get_plex_db_table_metadata_items(self.path, 'typo')
        with self.assertRaises(NotImplementedError):
            database.get_plex_db_table_metadata_items(self.path, 'Photo')

    def test_episode_indices_and_missing_parents_or_media(self):
        episode, orphan = database.get_metadata_item_cls_lst(self.path, 'Episodes')
        self.assertEqual((episode.tv_series_guid, episode.tv_series_season_int, episode.tv_series_episode_int), ('show', 0, 1))
        self.assertEqual(episode.media_part[0]['Hash'], 'def')
        self.assertIsNone(orphan.tv_series_title)
        self.assertEqual(orphan.media_part, [])
        result = database.diff_metadata_item_cls_lsts_by_info([episode, orphan], [episode, orphan])
        self.assertEqual(len(result['Match']), 1)
        self.assertEqual(result['Only in 1'], [orphan])
        self.assertEqual(result['Only in 2'], [orphan])

    def test_duplicate_guids_match_once_and_null_hashes_do_not_match(self):
        def item(guid, hashes):
            return SimpleNamespace(guid=guid, media_part=[{'Hash': value} for value in hashes])
        left = [item('same', ['a']), item('same', ['b']), item(None, [None])]
        right = [item('same', ['b']), item('same', ['a']), item(None, [None])]
        result = database.diff_metadata_item_cls_lsts_by_guid(left, right, True)
        self.assertEqual(len(result['Match']), 2)
        self.assertIs(result['Match'][0][1], right[1])
        self.assertEqual(result['Only in 1'], [left[2]])
        self.assertEqual(result['Only in 2'], [right[2]])

    def test_debug_database_picker_cancel_does_not_query(self):
        with patch('commonUtils.ui.pyside.QFileDialog.getOpenFileName', return_value=('', '')), patch.object(database, '_connect') as connect:
            self.assertIsNone(database.test_script())
        connect.assert_not_called()


    def test_hash_matching_reassigns_ambiguous_duplicates(self):
        def item(hashes):
            return SimpleNamespace(guid='same', media_part=[{'Hash': value} for value in hashes])
        left = [item(['a', 'b']), item(['a'])]
        right = [item(['a']), item(['b'])]
        result = database.diff_metadata_item_cls_lsts_by_guid(left, right, True)
        self.assertEqual(result['Match'], [[left[0], right[1]], [left[1], right[0]]])
        self.assertEqual(result['Only in 1'], [])
        self.assertEqual(result['Only in 2'], [])


class PlexPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.data = self.root / 'Plex Media Server'
        self.data.mkdir()
        (self.data / 'metadata.db').write_bytes(b'old data')
        self.package = self.root / 'Library-PMSDATA'
        self.package.mkdir()

    def test_linux_package_and_restore_retains_previous_data(self):
        packages.package_data(self.data, self.package, OS.LINUX)
        (self.data / 'metadata.db').write_bytes(b'changed data')
        previous = packages.restore_data(self.package, self.data, OS.LINUX)
        self.assertEqual((self.data / 'metadata.db').read_bytes(), b'old data')
        self.assertEqual((previous / 'metadata.db').read_bytes(), b'changed data')

    def test_failed_package_keeps_previous_archive_and_unrelated_files(self):
        archive = self.package / 'pms_data_mac.zip'
        archive.write_bytes(b'previous package')
        extra = self.package / 'other.plist'
        extra.write_bytes(b'unrelated')
        with self.assertRaises(FileNotFoundError):
            packages.package_data(self.data, self.package, OS.MAC, preferences=self.root / 'missing.plist')
        self.assertEqual(archive.read_bytes(), b'previous package')
        self.assertEqual(extra.read_bytes(), b'unrelated')
        self.assertFalse(list(self.package.glob('.logistics-plex-*')))

    def test_corrupt_or_traversing_restore_keeps_existing_data(self):
        archive = self.package / 'pms_data_linux.zip'
        archive.write_bytes(b'broken')
        from zipfile import BadZipFile
        with self.assertRaises(BadZipFile):
            packages.restore_data(self.package, self.data, OS.LINUX)
        for name in ('../outside', '/absolute', 'Plex Media Server/../../outside', 'Other/file', 'Plex Media Server/C:/file'):
            with self.subTest(name=name):
                with ZipFile(archive, 'w') as output:
                    output.writestr(name, b'bad')
                with self.assertRaises(ValueError):
                    packages.restore_data(self.package, self.data, OS.LINUX)
        self.assertEqual((self.data / 'metadata.db').read_bytes(), b'old data')
        self.assertFalse((self.root / 'outside').exists())

    def test_restore_swap_failure_rolls_back(self):
        packages.package_data(self.data, self.package, OS.LINUX)
        real_replace = os.replace
        def replace(source, destination):
            if '.logistics-plex-restore-' in str(source):
                raise OSError('device failure')
            return real_replace(source, destination)
        with patch.object(packages.os, 'replace', side_effect=replace), self.assertRaises(OSError):
            packages.restore_data(self.package, self.data, OS.LINUX)
        self.assertEqual((self.data / 'metadata.db').read_bytes(), b'old data')

    def test_links_overlap_and_unsupported_platform_are_rejected(self):
        link = self.data / 'external'
        link.symlink_to(self.package, target_is_directory=True)
        with self.assertRaises(ValueError):
            packages.package_data(self.data, self.package, OS.LINUX)
        link.unlink()
        with self.assertRaises(ValueError):
            packages.package_data(self.data, self.data / 'package', OS.LINUX)
        with self.assertRaises(ValueError):
            packages.package_data(self.data, self.package, None)

    def test_windows_commands_are_checked_and_include_root_files(self):
        executable = self.root / '7z.exe'
        executable.touch()
        def run(argv, **kwargs):
            self.assertTrue(kwargs['check'])
            if argv[0] == 'reg':
                Path(argv[3]).write_bytes(b'registry')
            elif argv[1] == 'a':
                Path(argv[5] + '.001').write_bytes(b'archive')
                self.assertEqual(kwargs['cwd'], self.data)
                self.assertEqual(argv[-1], './*')
            return subprocess.CompletedProcess(argv, 0)
        with patch.object(packages.subprocess, 'run', side_effect=run):
            packages.package_data(self.data, self.package, OS.WIN, executable)
        self.assertTrue((self.package / 'pms_data.7z.001').is_file())

    def test_failed_windows_archiver_preserves_package(self):
        executable = self.root / '7z.exe'
        executable.touch()
        old = self.package / 'pms_data.7z.001'
        old.write_bytes(b'old')
        with patch.object(packages.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'reg')):
            with self.assertRaises(subprocess.CalledProcessError):
                packages.package_data(self.data, self.package, OS.WIN, executable)
        self.assertEqual(old.read_bytes(), b'old')

    def test_missing_windows_environment_has_home_fallback(self):
        with patch.object(detection, 'get_os', return_value=OS.WIN), patch.dict(os.environ, {}, clear=True), patch.object(detection.Path, 'home', return_value=self.root):
            self.assertEqual(detection.get_pms_data_path(), self.root / 'AppData/Local/Plex Media Server')

    def test_platform_data_override(self):
        with patch.dict(os.environ, {'PLEX_MEDIA_SERVER_APPLICATION_SUPPORT_DIR': str(self.root)}):
            self.assertEqual(detection.get_pms_data_path(), self.data)

    def test_action_failure_is_reported(self):
        with patch.object(actions.plex_detection, 'get_pms_data_path', return_value=None), patch.object(actions, 'log') as log:
            self.assertFalse(actions.package_pms(None))
        self.assertTrue(log.call_args.kwargs['popup'])


    def test_windows_failed_extraction_does_not_import_registry_or_replace_data(self):
        executable = self.root / '7z.exe'
        executable.touch()
        (self.package / 'pms_data.7z.001').write_bytes(b'archive')
        registry = self.package / 'pms_registry.reg'
        registry.write_bytes(b'registry')
        with patch.object(packages.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, '7z')) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                packages.restore_data(self.package, self.data, OS.WIN, executable, registry)
        self.assertEqual(run.call_count, 1)
        self.assertEqual((self.data / 'metadata.db').read_bytes(), b'old data')

    def test_missing_episode_index_does_not_match_fake_indices(self):
        # Optional index columns on incomplete/older copies must remain unknown.
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'database.db'
            with sqlite3.connect(path) as connection:
                connection.execute('CREATE TABLE metadata_items (id, metadata_type, parent_id, library_section_id)')
                connection.execute('INSERT INTO metadata_items VALUES (1, 4, NULL, 1)')
            self.assertIsNone(database._table(path, 'metadata_items', ['id', 'index'])[0]['index'])


    def test_unreadable_source_directory_does_not_replace_package(self):
        blocked = self.data / 'unreadable'
        blocked.mkdir()
        (blocked / 'important.db').write_bytes(b'important')
        archive = self.package / 'pms_data_linux.zip'
        archive.write_bytes(b'previous package')
        original_scan = os.scandir
        def scan(path):
            if not isinstance(path, int) and Path(path) == blocked:
                raise PermissionError('cannot scan source')
            return original_scan(path)
        with patch.object(packages.os, 'scandir', side_effect=scan):
            with self.assertRaises(PermissionError):
                packages.package_data(self.data, self.package, OS.LINUX)
        self.assertEqual(archive.read_bytes(), b'previous package')

    @unittest.skipIf(os.name == 'nt', 'Unix permission behavior')
    def test_zip_restore_preserves_file_and_directory_permissions(self):
        (self.data / 'metadata.db').chmod(0o600)
        restricted = self.data / 'private'
        restricted.mkdir(mode=0o700)
        (restricted / 'tool').write_bytes(b'tool')
        (restricted / 'tool').chmod(0o750)
        packages.package_data(self.data, self.package, OS.LINUX)
        packages.restore_data(self.package, self.data, OS.LINUX)
        self.assertEqual((self.data / 'metadata.db').stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.data / 'private').stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.data / 'private/tool').stat().st_mode & 0o777, 0o750)


class PlexDialogTests(unittest.TestCase):
    def test_manage_dialog_constructs_and_displays_local_and_remote_paths(self):
        from commonUtils.ui import pyside as qt
        from features.plex.ui.manage_pms_dialog import PlexManagePMSDialog
        from models.folder_entry import FolderEntry
        app = qt.QApplication.instance() or qt.QApplication([])
        folder = SimpleNamespace(path=Path('/local/Library'), name='Library')
        entry = FolderEntry('Library', local=folder, remote_name='Library', remote_source='rclone', remote_context='/config.ini')
        local = SimpleNamespace(path=Path('/local/Library-PMSDATA'), name='Library-PMSDATA')
        remote = SimpleNamespace(path=Path('/remote/Library-PMSDATA'), name='Library-PMSDATA')
        with patch.object(actions, 'get_local_cls_pmsdata', return_value=local), patch.object(actions, 'get_remote_cls_pmsdata', return_value=remote), patch.object(detection, 'get_pms_data_path', return_value=None):
            dialog = PlexManagePMSDialog(entry)
        self.assertEqual(dialog.windowTitle(), 'Manage PMS - Library')
        self.assertIs(dialog.folder, folder)
        self.assertTrue(any(label.text() == '/local/Library-PMSDATA' for label in dialog.findChildren(qt.QLabel)))
        dialog.deleteLater()
        app.processEvents()
