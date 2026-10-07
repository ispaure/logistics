"""Calibre naming and export planning with disposable library/device fixtures."""

import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from commonUtils.dirUtils import Directory
from features.calibre import metadata, launching, actions, library
from features.calibre.export import build_export_plan, execute_export_plan
from commonUtils.osUtils import OS


class CalibreExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.library = self.root / 'Library'
        self.library.mkdir()
        (self.library / 'metadata.db').touch()
        self.destination = self.root / 'Device'

    def book(self, name='Book (1)', content=b'book', title=None):
        book = self.library / 'Author' / name
        book.mkdir(parents=True)
        file = book / 'book.epub'
        file.write_bytes(content)
        if title is not None:
            (book / 'metadata.opf').write_text(f'<package><title>{title}</title></package>')
        return file

    def export(self):
        return execute_export_plan(build_export_plan(self.library, self.destination, ['epub']))

    def test_planning_has_no_writes_and_export_prunes_after_copying(self):
        self.book()
        plan = build_export_plan(self.library, self.destination, ['.EPUB'])
        self.assertFalse(self.destination.exists())
        result = execute_export_plan(plan)
        self.assertEqual(result.copied, 1)
        self.assertEqual((self.destination / 'Author/Book.epub').read_bytes(), b'book')
        stale = self.destination / 'Old/stale.pdf'
        stale.parent.mkdir()
        stale.write_bytes(b'obsolete')
        result = self.export()
        self.assertEqual((result.copied, result.updated, result.deleted), (0, 0, 1))
        self.assertFalse(stale.parent.exists())

    def test_same_size_changed_book_is_updated(self):
        file = self.book(content=b'first')
        self.export()
        file.write_bytes(b'other')
        result = self.export()
        self.assertEqual(result.updated, 1)
        self.assertEqual((self.destination / 'Author/Book.epub').read_bytes(), b'other')

    def test_failed_copy_keeps_all_previous_books_and_obsolete_files(self):
        first = self.book('First (1)', b'old first')
        second = self.book('Second (2)', b'old second')
        self.export()
        stale = self.destination / 'keep.epub'
        stale.write_bytes(b'keep')
        first.write_bytes(b'new first')
        second.write_bytes(b'new second')
        real_copy = shutil.copy2
        calls = []
        def copy(source, target):
            calls.append(source)
            if len(calls) == 2:
                raise OSError('device full')
            return real_copy(source, target)
        with patch('features.calibre.export.shutil.copy2', side_effect=copy):
            with self.assertRaisesRegex(OSError, 'device full'):
                self.export()
        self.assertEqual((self.destination / 'Author/First.epub').read_bytes(), b'old first')
        self.assertEqual((self.destination / 'Author/Second.epub').read_bytes(), b'old second')
        self.assertTrue(stale.exists())
        self.assertFalse(list(self.destination.rglob('.logistics-calibre-*')))

    def test_collision_is_rejected_before_destination_changes(self):
        self.book('Book (1)')
        self.book('book (2)')
        with self.assertRaisesRegex(ValueError, 'collision'):
            self.export()
        self.assertFalse(self.destination.exists())

    def test_invalid_library_extensions_and_overlap_do_not_write(self):
        for source, destination, extensions in (
            (self.root, self.destination, ['epub']),
            (self.library, self.library / 'inside', ['epub']),
            (self.library, self.root, ['epub']),
            (self.library, self.destination, []),
        ):
            with self.subTest(source=source, destination=destination, extensions=extensions):
                with self.assertRaises(ValueError):
                    build_export_plan(source, destination, extensions)
        self.assertFalse(self.destination.exists())

    def test_links_are_rejected_without_touching_their_targets(self):
        self.book()
        external = self.root / 'External'
        external.mkdir()
        data = external / 'important.epub'
        data.write_bytes(b'important')
        self.destination.mkdir()
        (self.destination / 'linked').symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'links'):
            self.export()
        self.assertEqual(data.read_bytes(), b'important')

    def test_source_and_destination_changes_abort_before_writes(self):
        file = self.book()
        self.export()
        for changed in (file, self.destination / 'Author/Book.epub'):
            plan = build_export_plan(self.library, self.destination, ['epub'])
            changed.write_bytes(b'changed')
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                execute_export_plan(plan)

    def test_unicode_equivalent_destination_is_preserved(self):
        self.book(title='Café')
        self.destination.mkdir()
        author = self.destination / 'Author'
        author.mkdir()
        existing = author / 'Cafe\u0301.epub'
        existing.write_bytes(b'book')
        result = self.export()
        self.assertEqual((result.copied, result.updated, result.deleted), (0, 0, 0))
        self.assertTrue(existing.exists())

    def test_metadata_series_and_existing_volume_are_not_duplicated(self):
        file = self.book()
        metadata_file = file.parent / 'metadata.opf'
        for title, expected in [('Title', 'Series - Title - Vol 5'),
                                ('Series: Title Volume 5', 'Series - Title Volume 5')]:
            metadata_file.write_text('<package xmlns:dc="urn:dc"><dc:title>' + title + '</dc:title>'
                                     '<meta name="calibre:series" content="Series"/>'
                                     '<meta name="calibre:series_index" content="5.00"/></package>')
            self.assertEqual(metadata.get_metadata_book_name(Directory(file.parent)), expected)

    def test_malformed_metadata_uses_sanitized_folder_name(self):
        file = self.book('Title: Name (7)' if os.name != 'nt' else 'Title - Name (7)')
        (file.parent / 'metadata.opf').write_text('<broken')
        plan = build_export_plan(self.library, self.destination, ['epub'])
        self.assertEqual(plan.files[0].destination.name, 'Title - Name.epub')
        self.assertTrue(plan.warnings)

    def test_truncated_copy_does_not_replace_previous_export(self):
        file = self.book(content=b'original')
        self.export()
        file.write_bytes(b'new book')
        with patch('features.calibre.export.shutil.copy2', side_effect=lambda source, target: target.write_bytes(b'partial')):
            with self.assertRaisesRegex(RuntimeError, 'copy failed'):
                self.export()
        self.assertEqual((self.destination / 'Author/Book.epub').read_bytes(), b'original')

    def test_replacement_failure_keeps_obsolete_files_and_cleans_staging(self):
        file = self.book(content=b'original')
        self.export()
        stale = self.destination / 'stale.epub'
        stale.touch()
        file.write_bytes(b'changed')
        with patch('features.calibre.export.os.replace', side_effect=OSError('device unavailable')):
            with self.assertRaisesRegex(OSError, 'device unavailable'):
                self.export()
        self.assertEqual((self.destination / 'Author/Book.epub').read_bytes(), b'original')
        self.assertTrue(stale.exists())
        self.assertFalse(list(self.destination.rglob('.logistics-calibre-*')))

    def test_external_destination_change_during_staging_is_preserved(self):
        file = self.book(content=b'original')
        self.export()
        target = self.destination / 'Author/Book.epub'
        file.write_bytes(b'updated')
        real_copy = shutil.copy2
        def copy(source, temporary):
            real_copy(source, temporary)
            target.write_bytes(b'external change')
        with patch('features.calibre.export.shutil.copy2', side_effect=copy):
            with self.assertRaisesRegex(RuntimeError, 'changed since planning'):
                self.export()
        self.assertEqual(target.read_bytes(), b'external change')

    def test_replaced_destination_is_not_populated_or_pruned(self):
        self.book()
        self.export()
        plan = build_export_plan(self.library, self.destination, ['epub'])
        self.destination.rename(self.root / 'Disconnected Device')
        self.destination.mkdir()
        keep = self.destination / 'keep.epub'
        keep.write_bytes(b'keep')
        with self.assertRaisesRegex(RuntimeError, 'destination was replaced'):
            execute_export_plan(plan)
        self.assertEqual(keep.read_bytes(), b'keep')
        self.assertFalse((self.destination / 'Author').exists())

    def test_disconnected_boox_volume_is_not_created(self):
        with patch.object(Path, 'is_mount', return_value=False), patch.object(actions.CalibreLibrary, 'echo_book_formats') as echo:
            with self.assertRaisesRegex(OSError, 'not mounted'):
                actions.echo_epubs_to_boox_sd(actions.CalibreLibrary(self.library))
        echo.assert_not_called()


class CalibreLaunchTests(unittest.TestCase):
    def test_windows_launch_uses_bundled_executable_without_a_shell(self):
        root = Path('/bundled software')
        with patch.object(launching, 'get_os', return_value=OS.WIN), patch.object(
                launching.config, 'LogisticsConfig', return_value=SimpleNamespace(path_logistics_software_win=root)), patch.object(
                Path, 'is_file', return_value=True), patch.object(launching.subprocess, 'Popen') as start:
            launching.launch_library(Path('/books'))
        self.assertEqual(start.call_args.args[0],
                         [str(root / 'Calibre2/calibre.exe'), '--with-library', str(Path('/books'))])

    def test_mac_installation_is_checked_before_launch(self):
        with patch.object(launching, 'get_os', return_value=OS.MAC), patch.object(
                launching.config, 'LogisticsConfig', return_value=SimpleNamespace(path_logistics_software_mac=Path('/software'))), patch.object(
                Path, 'is_file', side_effect=[False, True]), patch.object(
                launching.zipUtils, 'unzip_file', return_value=True) as extract, patch.object(
                launching.subprocess, 'Popen') as start:
            launching.launch_library(Path('/books'))
        extract.assert_called_once_with(Path('/software/calibre.app.zip'), Path('/Applications'))
        self.assertEqual(start.call_args.args[0][0], str(Path('/Applications/calibre.app/Contents/MacOS/calibre')))

    def test_failed_mac_extraction_does_not_launch(self):
        with patch.object(launching, 'get_os', return_value=OS.MAC), patch.object(
                launching.config, 'LogisticsConfig', return_value=SimpleNamespace(path_logistics_software_mac=Path('/software'))), patch.object(
                Path, 'is_file', return_value=False), patch.object(
                launching.zipUtils, 'unzip_file', return_value=False), patch.object(launching.subprocess, 'Popen') as start:
            with self.assertRaisesRegex(OSError, 'Could not install'):
                launching.launch_library(Path('/books'))
        start.assert_not_called()

    def test_launcher_timeout_is_reported_by_library_facade(self):
        with patch.object(library, 'launch_library', side_effect=subprocess.TimeoutExpired(['flatpak'], 5)), patch.object(
                library, 'log') as message:
            self.assertFalse(library.CalibreLibrary(Path('/books')).open_in_calibre())
        self.assertTrue(message.call_args.kwargs['popup'])

    def test_linux_native_launcher_preserves_spaces_and_shell_characters(self):
        path = Path('/library with spaces/$(example)')
        with patch.object(launching, 'get_os', return_value=OS.LINUX), patch.object(
                launching.shutil, 'which', return_value='/usr/bin/calibre'), patch.object(
                launching.subprocess, 'Popen') as start:
            launching.launch_library(path)
        self.assertEqual(start.call_args.args[0], ['/usr/bin/calibre', '--with-library', str(path)])
        self.assertNotIn('shell', start.call_args.kwargs)

    def test_linux_flatpak_checks_user_or_system_install(self):
        with patch.object(launching, 'get_os', return_value=OS.LINUX), patch.object(
                launching.shutil, 'which', side_effect=[None, '/usr/bin/flatpak']), patch.object(
                launching.subprocess, 'run') as info, patch.object(launching.subprocess, 'Popen') as start:
            info.return_value.returncode = 0
            launching.launch_library(Path('/books'))
        self.assertEqual(start.call_args.args[0][:3], ['/usr/bin/flatpak', 'run', 'com.calibre_ebook.calibre'])

    def test_missing_flatpak_application_does_not_launch(self):
        with patch.object(launching, 'get_os', return_value=OS.LINUX), patch.object(
                launching.shutil, 'which', side_effect=[None, '/usr/bin/flatpak']), patch.object(
                launching.subprocess, 'run') as info, patch.object(launching.subprocess, 'Popen') as start:
            info.return_value.returncode = 1
            with self.assertRaises(FileNotFoundError):
                launching.launch_library(Path('/books'))
        start.assert_not_called()


class CalibreDialogFailureTests(unittest.TestCase):
    def test_management_dialog_reports_export_failure(self):
        from features.calibre.ui.manage_dialog import CalibreManageDialog
        from commonUtils.ui import pyside as qt
        from models.local_folder import LocalFolder
        from features.calibre import actions
        app = qt.QApplication.instance() or qt.QApplication([])
        book_library = library.CalibreLibrary(Path('/books/<literal>'))
        with patch.object(actions, 'get_libraries', return_value=[book_library]):
            dialog = CalibreManageDialog(LocalFolder('/local/Books'))
        self.addCleanup(dialog.deleteLater)
        with patch('features.calibre.ui.manage_dialog.ui.display_msg_box_ok_cancel', return_value=True), patch.object(actions, 'echo_epubs_to_boox_sd', side_effect=OSError('device disconnected')), patch('features.calibre.ui.manage_dialog.ui.display_msg_box_ok') as message:
            dialog._echo_to_boox()
        message.assert_called_once_with('Calibre Export Failed', 'device disconnected')
        app.processEvents()
