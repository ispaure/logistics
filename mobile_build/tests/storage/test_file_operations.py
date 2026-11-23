"""Captured file commands, shared cancellation and late UI publication boundaries."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, get_ident
import unittest
from unittest.mock import AsyncMock, patch

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.operations import check_cancelled, MutationIncomplete, MutationResult
from mobile.app import LogisticsMobile
from mobile.file_operations import FileDestination, FileOperationRequest, FileOperations, FileOperationsHost
from mobile import file_operations


class FileOperationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        LogisticsMobile.storage_root = self.root
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.run_async = self.app.loop.run_until_complete
        self.run_async(self.app.show_files(location=('Local files', '')))
        self.source = self.app.file_provider
        (self.source.root / 'first.txt').write_text('First')
        (self.source.root / 'second.txt').write_text('Second')
        destination = self.root / 'destination'
        destination.mkdir()
        self.destination = LocalFiles(destination)
        self.app.file_roots['Destination'] = self.destination
        self.app.file_destination.items = ['Destination']
        self.app.file_destination.value = 'Destination'
        self.run_async(self.app.browse_files())
        self.select('first.txt')

    def tearDown(self):
        self.app.main_window.close()
        close_loop(self.app.loop)
        LogisticsMobile.storage_root = None
        self.temporary.cleanup()

    def select(self, name):
        self.app.file_selection.value = next(key for key, row in self.app.file_rows.items() if row['name'] == name)

    def test_sibling_copy_verifies_files_and_dotted_folders_beside_source(self):
        self.assertIn('Duplicate…', dict(self.app.file_item_commands()))
        for _ in range(2):
            FileOperationRequest('copy', self.source, 'first.txt').execute(lambda: False)
        for name in ('first.txt', 'first - Copy.txt', 'first - Copy (2).txt'):
            self.assertEqual((self.source.root / name).read_text(), 'First')
        folder = self.source.root / 'Folder.v1'
        folder.mkdir()
        (folder / 'child.txt').write_text('Child')
        self.run_async(self.app.browse_files())
        self.select('Folder.v1')
        self.assertIn('Duplicate…', dict(self.app.file_item_commands()))
        FileOperationRequest('copy', self.source, folder.name).execute(lambda: False)
        self.assertEqual((self.source.root / 'Folder.v1 - Copy/child.txt').read_text(), 'Child')
        self.assertEqual((folder / 'child.txt').read_text(), 'Child')
        self.assertFalse(list(self.source.root.glob('.notes-copy-*')))
        with patch.object(self.app.file_provider, 'remote_storage', True, create=True):
            self.select('first.txt')
            self.assertNotIn('Duplicate…', dict(self.app.file_item_commands()))
            with self.assertRaises(PermissionError):
                FileOperationRequest('copy', self.app.file_provider, 'first.txt').execute(lambda: False)

    def test_overflow_separates_folder_commands_and_eligible_item_actions(self):
        from mobile.local_sources import SharedFiles

        (self.source.root / 'chapter.CBZ').write_bytes(b'Archive menu fixture')
        (self.source.root / 'comic folder').mkdir()
        self.run_async(self.app.browse_files())
        folder_commands = dict(self.app.file_actions.actions)
        self.assertEqual(set(folder_commands), {'New folder…', 'Change location…', 'Select items'})

        for name in ('first.txt', 'chapter.CBZ', 'comic folder'):
            with self.subTest(name=name):
                row = self.source.entry(name)
                titles = dict(self.app.file_item_commands(row=row))
                self.assertTrue({'Open', 'Details', 'Rename…', 'Move…', 'Duplicate…', 'Delete…'} <= titles.keys())
                self.assertEqual('Archive password…' in titles, name == 'chapter.CBZ')
                self.assertFalse({'New folder…', 'Edit comics in this folder…', 'Add to Favourites',
                                  'Pin this folder', 'Cut', 'Copy'} & titles.keys())
                self.assertEqual(list(titles)[-1], 'Delete…')
        provider = self.app.file_provider
        with patch.object(provider, 'read_only', True, create=True):
            read_only_commands = dict(self.app.file_item_commands(row=provider.entry('first.txt')))
            self.assertTrue({'Open', 'Details'} <= read_only_commands.keys())
            self.assertFalse({'Rename…', 'Move…', 'Duplicate…', 'Delete…'} & read_only_commands.keys())
            self.assertNotIn('New folder…', dict(self.app.current_folder_commands()))

        shared = SharedFiles(self.destination.root)
        (shared.root / 'Received Files').mkdir()
        collection, = shared.list()
        commands = self.app.file_item_commands(context=(shared, 'Shared files', collection))
        self.assertEqual([title for title, _ in commands], ['Open'])

    def test_selection_starts_in_folder_menu_and_back_clears_it(self):
        app = self.app
        row = self.source.entry('second.txt')
        self.assertNotIn('Select items', dict(app.file_item_commands(row=row)))
        dict(app.current_folder_commands())['Select items']()
        self.assertFalse(app.file_checked)
        browser = app.file_browser
        self.assertEqual(browser.location_bar.parent_button.accessible_name, 'Exit selection')
        self.assertEqual([control.style.display for control in
                          (browser.search_button, browser.view_switch, app.file_actions_button)], ['none'] * 3)
        entry = next(entry for entry in browser.entries if entry.payload['path'] == 'second.txt')
        app.check_file_entry(entry)
        self.assertEqual(list(app.file_checked), [entry.identity])
        self.assertEqual(app.file_selection_count.text, '1 selected')
        self.assertEqual(app.file_archive_button.accessible_name, 'Archive selected items')
        self.assertTrue(app.file_delete_button.enabled)
        path = app.file_path
        self.assertTrue(self.run_async(app.parent_file_folder()))
        self.assertEqual(app.file_path, path)
        self.assertFalse(app.file_checked)
        self.assertIsNone(browser.on_check_entry)
        self.assertEqual(app.file_actions_button.style.display, 'pack')

    def test_delete_selection_confirms_then_removes_only_selected_items(self):
        app = self.app
        app.begin_file_selection()
        app.check_file_entry(next(entry for entry in app.file_browser.entries if entry.label == 'second.txt'))
        with patch.object(app.main_window, 'dialog', new=AsyncMock(side_effect=[False, True])):
            self.run_async(app.delete_checked_files())
            self.assertTrue((self.source.root / 'second.txt').is_file())
            self.assertEqual(len(app.file_checked), 1)
            self.run_async(app.delete_checked_files())
        self.assertFalse((self.source.root / 'second.txt').exists())
        self.assertEqual((self.source.root / 'first.txt').read_text(), 'First')
        self.assertFalse(app.file_checked)

    def test_file_details_dismisses_without_changing_the_folder_route(self):
        app = self.app
        browser = app.file_browser
        entry = next(entry for entry in browser.entries if entry.label == 'second.txt')
        self.run_async(browser.select(entry))
        screens = list(app.routes.screens['files'])
        app.show_file_details()
        panel = browser.details_panel
        self.assertIsNotNone(panel.overlay)
        self.assertIsNone(panel.parent)
        self.assertEqual(app.routes.screens['files'], screens)
        self.assertTrue(app.routes.system_back())
        self.assertIsNone(browser.details_panel)
        self.assertEqual(browser.selected, entry.identity)
        self.assertEqual(app.routes.screens['files'], screens)

    def test_selection_indicators_leave_filenames_and_group_actions_intact(self):
        app, browser = self.app, self.app.file_browser
        dictionary = {entry.payload['path']: entry for entry in browser.entries}
        app.begin_file_selection()
        app.check_file_entry(dictionary['first.txt'])
        self.assertEqual(browser.native_list.checked_indices, {browser._list_indices[dictionary['first.txt'].identity]})
        self.assertEqual({row.title for row in browser.native_list.data}, {'first.txt', 'second.txt'})
        self.assertTrue(app.file_move_button.enabled)
        browser.show_tiles()
        for name, entry in dictionary.items():
            _, card, title, *_ = browser._tile_cards[entry.identity]
            self.assertEqual(title.text, name)
            self.assertEqual(card._tile_selection.style.visibility, 'visible')
            self.assertEqual(card._tile_command.style.visibility, 'hidden')
            self.assertEqual(card._tile_selection.accessible_name,
                ('Deselect ' if name == 'first.txt' else 'Select ') + name)
        app.end_file_selection()
        for _, card, *_ in browser._tile_cards.values():
            self.assertEqual(card._tile_selection.style.visibility, 'hidden')
            self.assertEqual(card._tile_command.style.visibility, 'visible')

    def test_drag_moves_a_folder_and_its_contents_into_a_sibling_folder(self):
        from mobile.file_drag import FileDrag

        source = self.source.root / 'Folder'
        source.mkdir()
        (source / 'note.txt').write_text('Nested content')
        target = self.source.root / 'Destination'
        target.mkdir()
        self.run_async(self.app.browse_files())
        browser = self.app.file_browser
        entries = {entry.payload['path']: entry for entry in browser.entries}
        drag = FileDrag(self.app, browser)

        async def drop():
            token = drag.begin(entries['Folder'])
            self.assertIsNotNone(token)
            self.assertFalse(drag.drop(token, entries['Folder']))
            self.assertFalse(drag.drop(token, entries['first.txt']))
            self.assertFalse(drag.drop('retired-token', entries['Destination']))
            self.assertTrue(drag.drop(token, entries['Destination']))
            self.assertFalse(drag.drop(token, entries['Destination']))
            return await drag.task

        self.assertTrue(self.run_async(drop()))
        self.assertFalse(source.exists())
        self.assertEqual((target / 'Folder' / 'note.txt').read_text(), 'Nested content')
        self.assertEqual(self.app.file_status.value, 'Moved to Destination.')

    def test_drag_preserves_originals_when_folder_changes_or_item_exists(self):
        from mobile.file_drag import FileDrag

        target = self.source.root / 'Destination'
        target.mkdir()
        self.run_async(self.app.browse_files())
        browser = self.app.file_browser
        drag = FileDrag(self.app, browser)

        async def drop(replace_folder=False):
            entries = {entry.payload['path']: entry for entry in browser.entries}
            token = drag.begin(entries['first.txt'])
            if replace_folder:
                target.rename(target.with_name('Original folder'))
                target.mkdir()
            self.assertTrue(drag.drop(token, entries['Destination']))
            return await drag.task

        self.assertFalse(self.run_async(drop(replace_folder=True)))
        self.assertIn('destination folder changed', self.app.file_status.value)
        self.assertFalse((target / 'first.txt').exists())
        (target / 'first.txt').write_text('Existing destination')
        self.run_async(self.app.browse_files())
        self.assertFalse(self.run_async(drop()))
        self.assertEqual((target / 'first.txt').read_text(), 'Existing destination')
        self.assertEqual((self.source.root / 'first.txt').read_text(), 'First')

    def test_drag_spring_opens_nested_folders_and_drops_in_the_open_folder(self):
        from mobile.file_drag import FileDrag

        nested = self.source.root / 'Destination' / 'Nested'
        nested.mkdir(parents=True)
        self.run_async(self.app.browse_files())
        browser = self.app.file_browser
        drag = FileDrag(self.app, browser)
        flashes = []

        def entry(path):
            return next(entry for entry in browser.entries if entry.payload['path'] == path)

        async def drop():
            token = drag.begin(entry('first.txt'))
            drag.hover(token, entry('Destination'), flashes.append, (20, 40))
            await drag.hover_task
            self.assertEqual(self.app.file_path, 'Destination')
            self.assertIsNone(drag.target_entry(entry('Destination/Nested'), (21, 41)))
            row = drag.target_entry(entry('Destination/Nested'), (50, 70))
            drag.hover(token, row, flashes.append, (50, 70))
            await drag.hover_task
            self.assertEqual(self.app.file_path, 'Destination/Nested')
            self.assertTrue(drag.drop(token, None))
            return await drag.task

        with patch('mobile.file_drag.SPRING_DELAY', 0), patch('mobile.file_drag.SPRING_FLASH', 0):
            self.assertTrue(self.run_async(drop()))
        self.assertEqual(flashes, [True, False, True, False] * 2)
        self.assertEqual((nested / 'first.txt').read_text(), 'First')
        self.assertFalse((self.source.root / 'first.txt').exists())

    def test_collection_name_listing_avoids_metadata_formatting(self):
        from services.documents.locations import CollectionFiles
        provider = CollectionFiles(self.root)
        with patch('services.documents.locations._modified_time', side_effect=AssertionError('No timestamps')):
            rows = provider.list_names()
        self.assertTrue({'first.txt', 'second.txt'} <= {row['name'] for row in rows})
        self.assertTrue(all(set(row) == {'name', 'path', 'directory', 'size'} for row in rows))

    def test_collection_name_listing_rejects_folder_replacement(self):
        from contextlib import contextmanager
        import os
        from services.documents.locations import CollectionFiles
        provider = CollectionFiles(self.root)
        folder = provider.root / 'Moving'
        folder.mkdir()
        scan = os.scandir
        @contextmanager
        def replaced(path):
            with scan(path) as entries:
                yield entries
            folder.rename(provider.root / 'Previous')
            folder.mkdir()
        with patch('services.documents.locations.os.scandir', side_effect=replaced):
            with self.assertRaisesRegex(ValueError, 'changed during listing'):
                provider.list_names('Moving')

    def test_create_rename_move_and_confirmed_delete_use_existing_resource_operations(self):
        app = self.app
        app.file_name.value = 'New folder'
        self.run_async(app.new_file_folder())
        self.assertTrue((self.source.root / 'New folder').is_dir())
        self.select('first.txt')
        app.file_name.value = 'renamed.txt'
        self.run_async(app.rename_file())
        self.assertEqual((self.source.root / 'renamed.txt').read_text(), 'First')
        self.select('renamed.txt')
        app.file_target.value = 'moved.txt'
        self.run_async(app.move_file())
        self.assertEqual((self.destination.root / 'moved.txt').read_text(), 'First')
        self.assertFalse((self.source.root / 'renamed.txt').exists())
        self.select('New folder')
        with patch.object(app.main_window, 'dialog', AsyncMock(return_value=True)):
            self.run_async(app.delete_file())
        self.assertFalse((self.source.root / 'New folder').exists())
        self.assertFalse(app.cloud_busy)
        self.assertIsNone(app._crypt_cancel)

    def test_row_actions_stay_in_browser_and_retire_when_listing_changes(self):
        browser = self.app.file_browser
        row = next(row for row in browser.native_list.data if row.entry.payload['name'] == 'first.txt')
        view = self.app.body
        self.run_async(browser._select_row(row))
        menu = browser._item_menu
        self.assertIs(self.app.body, view)
        titles = [title for title, _ in menu.actions]
        self.assertIn('Rename…', titles)
        self.assertIn('Move…', titles)
        with patch.object(self.app, 'show_file_actions') as show:
            menu.invoke(next(callback for title, callback in menu.actions if title == 'Rename…'))
            show.assert_called_once_with(operation='rename')
        self.run_async(self.app.browse_files())
        self.assertTrue(menu.disposed)
        self.assertEqual(menu.actions, ())

    def test_rename_updates_closed_favourites_and_recent_descendants(self):
        from mobile.favourites import catalog
        from mobile.workspace import Session
        app = self.app
        folder = self.source.root / 'Folder Ω'
        folder.mkdir()
        note = folder / 'Private name.md'
        note.write_text('# Keep bytes')
        source = dict(type='local', path=str(note))
        store = catalog(app)
        store.remember(source, note.name, dict(kind='notes', root=str(folder)), favourite=True)
        app.recent_documents.remember_file(Session('', 'file-reference', 'fixture', 'markdown', title=note.name), source)
        self.run_async(app.browse_files())
        self.select(folder.name)
        app.file_name.value = 'Renamed Ω'
        self.run_async(app.rename_file())
        expected = str(self.source.root / 'Renamed Ω' / note.name)
        self.assertEqual(store.entries()[0]['source']['path'], expected)
        self.assertEqual(store.entries()[0]['opener']['root'], str(self.source.root / 'Renamed Ω'))
        recent = app.recent_documents.items[0]
        self.assertEqual(recent['source']['path'], expected)
        self.assertEqual(recent['resource'], app.recent_documents.reference_id(recent['source']))
        self.assertEqual(Path(expected).read_text(), '# Keep bytes')

    def test_rename_updates_recent_on_ui_thread_even_if_favourites_fail(self):
        from mobile.workspace import Session
        app = self.app
        source = dict(type='local', path=str(self.source.root / 'first.txt'))
        app.recent_documents.remember_file(Session('', 'file-reference', 'fixture', 'text', title='first.txt'), source)
        ui_thread, observed = get_ident(), []
        relocate = app.recent_documents.relocate
        def on_ui(*args, **kwargs):
            observed.append(get_ident())
            return relocate(*args, **kwargs)
        app.file_name.value = 'renamed.txt'
        with patch('services.documents.catalog.DocumentCatalog.relocate', side_effect=OSError('Unreadable favourites')), \
                patch.object(app.recent_documents, 'relocate', side_effect=on_ui):
            self.run_async(app.rename_file())
        self.assertEqual(observed, [ui_thread])
        self.assertEqual(app.recent_documents.items[0]['source']['path'], str(self.source.root / 'renamed.txt'))
        self.assertIn('saved references could not be updated', app.file_status.value)

    def test_delete_keeps_the_confirmed_target_if_selection_changes_in_dialog(self):
        async def confirm(dialog):
            self.select('second.txt')
            return True
        with patch.object(self.app.main_window, 'dialog', side_effect=confirm):
            self.run_async(self.app.delete_file())
        self.assertFalse((self.source.root / 'first.txt').exists())
        self.assertEqual((self.source.root / 'second.txt').read_text(), 'Second')

    def test_refused_confirmation_has_no_side_effects(self):
        with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value=False)):
            self.run_async(self.app.delete_file())
        self.assertTrue((self.source.root / 'first.txt').exists())
        self.assertFalse(self.app.cloud_busy)
        self.assertFalse(hasattr(self.app, '_file_operations'))

    def test_move_does_not_overwrite_an_existing_destination(self):
        (self.destination.root / 'existing.txt').write_text('Keep destination')
        self.app.file_target.value = 'existing.txt'
        self.run_async(self.app.move_file())
        self.assertEqual((self.source.root / 'first.txt').read_text(), 'First')
        self.assertEqual((self.destination.root / 'existing.txt').read_text(), 'Keep destination')
        self.assertIn('Operation failed:', self.app.file_status.value)
        self.assertTrue(self.app.file_actions_button.enabled)

    def test_direct_private_move_requires_confirmation_and_keeps_captured_source(self):
        self.app.file_provider.private = True
        self.app.file_target.value = 'confirmed.txt'
        with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value=False)):
            self.run_async(self.app.move_file())
        self.assertTrue((self.source.root / 'first.txt').exists())
        self.assertFalse((self.destination.root / 'confirmed.txt').exists())
        async def confirm(dialog):
            self.select('second.txt')
            return True
        with patch.object(self.app.main_window, 'dialog', side_effect=confirm):
            self.run_async(self.app.move_file())
        self.assertEqual((self.destination.root / 'confirmed.txt').read_text(), 'First')
        self.assertEqual((self.source.root / 'second.txt').read_text(), 'Second')

    def test_new_folder_keeps_unrelated_open_edits(self):
        from features.text_editor.resources import LocalTextCopies
        self.run_async(self.app.open_crypt(copies=LocalTextCopies(self.app.file_provider), key='first.txt'))
        owner = self.app.private_sessions.active
        owner.crypt_text.value = 'Keep open draft'
        self.app.file_name.value = 'Another folder'
        self.run_async(self.app.new_file_folder())
        self.assertTrue((self.source.root / 'Another folder').is_dir())
        self.assertIs(self.app.private_sessions.controllers[owner.session.id], owner)
        self.assertEqual(owner.crypt_text.value, 'Keep open draft')

    def test_worker_uses_captured_source_and_name_and_leaves_new_screen_status_alone(self):
        started, release = Event(), Event()
        original = file_operations.rename_resource
        ui_thread = get_ident()
        def rename(*args, **kwargs):
            self.assertNotEqual(get_ident(), ui_thread)
            started.set()
            if not release.wait(4):
                raise RuntimeError('Worker fixture was not released')
            return original(*args, **kwargs)
        async def exercise():
            self.app.file_name.value = 'captured.txt'
            task = asyncio.create_task(self.app.rename_file())
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                self.app.file_provider = self.destination
                self.app.file_path = 'another-folder'
                self.app.file_name.value = 'wrong.txt'
                self.app.file_status.value = 'New screen status'
                release.set()
                await task
            finally:
                release.set()
                await task
        with patch('mobile.file_operations.rename_resource', side_effect=rename), \
                patch.object(self.app, 'browse_files', AsyncMock()) as browse:
            self.run_async(exercise())
        self.assertEqual((self.source.root / 'captured.txt').read_text(), 'First')
        self.assertFalse((self.destination.root / 'wrong.txt').exists())
        self.assertEqual(self.app.file_status.value, 'New screen status')
        browse.assert_not_awaited()
        self.assertFalse(self.app.cloud_busy)

    def test_destination_resolution_runs_in_worker_with_captured_mapping_and_target(self):
        started, release = Event(), Event()
        original = FileDestination.resolve
        ui_thread = get_ident()
        def resolve(destination):
            self.assertNotEqual(get_ident(), ui_thread)
            started.set()
            if not release.wait(4):
                raise RuntimeError('Worker fixture was not released')
            return original(destination)
        async def exercise():
            self.app.file_target.value = 'captured.txt'
            task = asyncio.create_task(self.app.move_file())
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                self.app.file_roots['Destination'] = self.source
                self.app.file_target.value = 'wrong.txt'
                release.set()
                await task
            finally:
                release.set()
                await task
        # The post-operation browse resolves providers on the UI thread by design.
        with patch.object(FileDestination, 'resolve', resolve), \
                patch.object(self.app, 'browse_files', AsyncMock()), \
                patch.object(self.app, 'refresh_crypt', AsyncMock()):
            self.run_async(exercise())
        self.assertEqual((self.destination.root / 'captured.txt').read_text(), 'First')
        self.assertFalse((self.source.root / 'wrong.txt').exists())

    def test_busy_transfer_and_dirty_reader_guards_do_not_start_worker(self):
        work = unittest.mock.Mock()
        self.app.cloud_busy = self.app.transfer_busy = True
        self.assertFalse(self.run_async(self.app.file_work(work)))
        self.app.cloud_busy = self.app.transfer_busy = False
        with patch.object(self.app, 'clear_private_reader', return_value=False):
            self.assertFalse(self.run_async(self.app.file_work(work)))
        work.assert_not_called()
        self.assertIsNone(self.app.file_operations().cancel_event)

    def check_cancel(self, cancel_task):
        started, release = Event(), Event()
        observed = []
        def work(cancelled):
            observed.append(cancelled)
            started.set()
            if not release.wait(4):
                raise RuntimeError('Worker fixture was not released')
            check_cancelled(cancelled)
        async def exercise():
            task = asyncio.create_task(self.app.file_work(work))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                self.assertIs(self.app._crypt_cancel, self.app.file_operations().cancel_event)
                if cancel_task:
                    task.cancel()
                    await asyncio.sleep(0)
                else:
                    self.app.cancel_cloud()
                self.assertTrue(observed[0]())
                self.assertTrue(self.app.cloud_busy)
                self.assertFalse(self.app.file_actions_button.enabled)
                self.assertFalse(await self.app.file_work(lambda cancelled: self.fail('Parallel operation')))
                release.set()
                if cancel_task:
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                else:
                    self.assertFalse(await task)
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)
        self.run_async(exercise())
        self.assertFalse(self.app.cloud_busy)
        self.assertIsNone(self.app._crypt_cancel)
        self.assertIsNone(self.app.file_operations().task)
        self.assertTrue(self.app.file_actions_button.enabled)
        self.assertTrue((self.source.root / 'first.txt').exists())

    def test_existing_cancel_control_signals_the_owned_worker(self):
        self.check_cancel(False)

    def test_task_cancellation_keeps_busy_guard_until_worker_retires(self):
        self.check_cancel(True)

    def test_partial_failure_keeps_specific_warning_and_restores_controls(self):
        def fail(cancelled):
            raise MutationIncomplete('Source partly removed.', MutationResult(source_state='partial'))
        self.assertFalse(self.run_async(self.app.file_work(fail)))
        self.assertEqual(self.app.file_status.value, 'Source partly removed.\nRefresh before retrying.')
        self.assertEqual(self.app.file_action_status.text, self.app.file_status.value)
        self.assertFalse(self.app.cloud_busy)
        self.assertTrue(self.app.file_actions_button.enabled)

    def test_capture_failure_is_reported_and_can_be_retried(self):
        self.app.file_destination.items = ['Missing location']
        self.app.file_destination.value = 'Missing location'
        self.run_async(self.app.move_file())
        self.assertIn('Missing location', self.app.file_status.value)
        self.assertTrue(self.app.file_actions_button.enabled)
        self.assertIsNone(self.app.file_operations().cancel_event)
        self.app.file_destination.items = ['Destination']
        self.app.file_destination.value = 'Destination'
        self.app.file_target.value = 'retried.txt'
        self.run_async(self.app.move_file())
        self.assertTrue((self.destination.root / 'retried.txt').exists())

    def test_late_error_does_not_replace_status_after_navigation_or_host_retirement(self):
        for invalidation in ('navigation', 'host'):
            with self.subTest(invalidation=invalidation):
                started, release = Event(), Event()
                def work(cancelled):
                    started.set()
                    if not release.wait(4):
                        raise RuntimeError('Worker fixture was not released')
                    raise OSError('Obsolete operation error')
                async def exercise():
                    task = asyncio.create_task(self.app.file_work(work))
                    try:
                        self.assertTrue(await asyncio.to_thread(started.wait, 3))
                        if invalidation == 'navigation':
                            self.app.navigation_generation += 1
                        else:
                            self.app.active_host = False
                        self.app.file_status.value = 'Current status'
                        self.app.file_action_status.text = 'Current actions'
                        release.set()
                        self.assertFalse(await task)
                    finally:
                        release.set()
                        await task
                        self.app.active_host = True
                self.run_async(exercise())
                self.assertEqual(self.app.file_status.value, 'Current status')
                self.assertEqual(self.app.file_action_status.text, 'Current actions')
                self.assertFalse(self.app.cloud_busy)

    def test_captured_encrypted_destination_rejects_replaced_credentials_before_resolution(self):
        from types import SimpleNamespace
        client = SimpleNamespace(generation=1)
        destination = FileDestination(self.root, client, 'Secret', client.generation)
        client.generation = 2
        with patch('mobile.file_operations.encrypted_storage') as resolve:
            with self.assertRaisesRegex(ValueError, 'Connection changed'):
                destination.resolve()
        resolve.assert_not_called()

    def test_confirmed_delete_rejects_a_replacement_at_the_same_path(self):
        path = 'first.txt'
        revision = self.source.entry(path)['revision']
        request = FileOperationRequest('delete', self.source, path, expected_revision=revision)
        original = self.source.root / path
        original.rename(original.with_name('renamed.txt'))
        original.write_text('replacement')

        with self.assertRaisesRegex(ValueError, 'selected item changed'):
            request.execute(lambda: False)
        self.assertEqual(original.read_text(), 'replacement')
        self.assertTrue(original.with_name('renamed.txt').exists())

    def test_invalid_names_and_protected_root_never_mutate_storage(self):
        for request in (FileOperationRequest('new', self.source, '', '../bad'),
                        FileOperationRequest('rename', self.source, 'first.txt', '../bad'),
                        FileOperationRequest('delete', self.source, '')):
            with self.subTest(kind=request.kind), self.assertRaises(ValueError):
                request.execute(lambda: False)
        self.assertTrue((self.source.root / 'first.txt').exists())
        self.assertTrue(self.source.root.exists())

    def test_begin_failure_does_not_latch_the_coordinator_busy(self):
        begin = unittest.mock.Mock(side_effect=[RuntimeError('Could not bind controls'), object()])
        host = FileOperationsHost(allowed=lambda mutation: True, begin=begin,
            current=lambda view: True, report=unittest.mock.Mock(), finish=unittest.mock.Mock())
        coordinator = FileOperations(host)
        with self.assertRaisesRegex(RuntimeError, 'Could not bind controls'):
            self.run_async(coordinator.run(lambda: lambda cancelled: None))
        self.assertIsNone(coordinator.cancel_event)
        self.assertIsNone(coordinator.task)
        self.assertTrue(self.run_async(coordinator.run(lambda: lambda cancelled: None)))
        self.assertEqual(host.finish.call_count, 1)

    def test_retired_operation_cannot_release_another_cancellation_owner(self):
        started, release = Event(), Event()
        replacement = Event()
        def work(cancelled):
            started.set()
            if not release.wait(4):
                raise RuntimeError('Worker fixture was not released')
        async def exercise():
            task = asyncio.create_task(self.app.file_work(work))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 3))
                self.app._crypt_cancel = replacement
                self.app.file_status.value = 'New operation status'
                release.set()
                self.assertFalse(await task)
                self.assertTrue(self.app.cloud_busy)
                self.assertIs(self.app._crypt_cancel, replacement)
                self.assertEqual(self.app.file_status.value, 'New operation status')
            finally:
                release.set()
                await task
                self.app._crypt_cancel = None
                self.app.set_cloud_busy(False)
        self.run_async(exercise())
