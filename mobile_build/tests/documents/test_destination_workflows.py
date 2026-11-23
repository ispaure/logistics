"""Real provider bytes for Save As naming, folder creation and browsed moves."""

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
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from commonUtils.runtime.resources.local import LocalFiles
from mobile.app import LogisticsMobile
from mobile.destination_names import save_filename
from mobile.file_operations import FileOperationRequest


class DestinationNameTests(unittest.TestCase):
    def test_basename_preserves_source_suffix_and_explicit_supported_intent(self):
        for value, source, expected in (
                ('copy', 'original.txt', 'copy.txt'), ('copy', 'original.md', 'copy.md'),
                ('copy', 'untitled', 'copy.txt'), ('copy.MD', 'original.txt', 'copy.MD'),
                ('.notes', 'original.md', '.notes.md'), ('résumé copy', 'original.MD', 'résumé copy.MD'),
                ('many.dots.txt', 'original.md', 'many.dots.txt')):
            with self.subTest(value=value, source=source):
                self.assertEqual(save_filename(value, source), expected)

    def test_invalid_names_never_turn_into_paths_or_different_explicit_types(self):
        for name in ('', ' ', '.', '..', '../escape', 'child/name', r'child\name', '/absolute',
                     'bad.exe', 'trailing.', 'bad\x00name'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                save_filename(name, 'source.txt')


class DestinationWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.temp.name).resolve()
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.run_async = self.app.loop.run_until_complete
        self.app.show_cloud(present=False)
        self.run_async(self.app.editor_picker().show_text_destination('source.md', b'# Unsaved'))
        self.picker = self.app.editor_picker()
        self.root = self.picker.editor_provider(self.picker.save_as_storage.value).root

    def tearDown(self):
        self.app.main_window.close()
        close_loop(self.app.loop)
        LogisticsMobile.storage_root = None
        self.temp.cleanup()

    def test_create_nested_folders_then_save_bare_name_and_reopen_exact_bytes(self):
        picker = self.picker
        for name in ('First', 'Nested'):
            picker.show_new_folder()
            picker.new_folder_name.value = name
            self.run_async(picker.create_picker_folder())
        self.assertEqual(picker.picker_folder.value, 'First/Nested')
        self.assertEqual(picker.save_as_name.value, 'source.md')
        picker.save_as_name.value = 'résumé'
        self.assertEqual(picker.effective_name.text, 'Save as: résumé.md')
        self.run_async(picker.confirm_editor_file())
        self.assertEqual((self.root / 'First/Nested/résumé.md').read_bytes(), b'# Unsaved')
        self.assertEqual(self.app.private_sessions.active.crypt_reader.name, 'résumé.md')

    def test_selection_move_publishes_successful_items_and_keeps_conflicts(self):
        destination = self.root / 'Destination'
        destination.mkdir()
        for name in ('first.txt', 'conflict.txt'):
            (self.root / name).write_text(name)
        (destination / 'conflict.txt').write_text('Keep destination')
        self.run_async(self.app.show_files(location=('Local files', '')))
        browser = self.app.file_browser
        from mobile.routes import contains
        parent = self.app.file_select_bar.parent
        self.assertTrue(contains(self.app.files_view, self.app.file_select_bar))
        self.assertEqual(self.app.file_select_bar.style.display, 'none')
        self.assertEqual(self.app.file_select_bar.style.visibility, 'hidden')
        self.assertTrue(all(button.style.visibility == 'hidden' for button in self.app.file_select_bar.children))
        self.assertEqual(self.app.file_select_bar.style.height, 0)
        self.app.begin_file_selection()
        self.assertIs(self.app.file_select_bar.parent, parent)
        self.assertEqual(self.app.file_select_bar.style.display, 'pack')
        self.assertEqual(self.app.file_select_bar.style.visibility, 'visible')
        self.assertEqual(self.app.file_move_button.style.visibility, 'visible')
        self.assertEqual(self.app.file_delete_button.style.visibility, 'visible')
        self.assertEqual(self.app.file_select_bar.style.height, 48)
        browser.show_tiles()
        entry = next(entry for entry in browser.tree.entries.values() if not entry.container)
        card = browser.entry_rows[entry.identity]
        circle = card._tile_selection
        self.assertEqual(circle.style.visibility, 'visible')
        self.assertEqual(circle.accessible_name, 'Select ' + entry.label)
        self.run_async(browser._select_pressed(entry, circle))
        self.assertEqual(circle.accessible_name, 'Deselect ' + entry.label)
        self.run_async(browser._select_pressed(entry, circle))
        browser.show_list()
        for entry in list(browser.tree.entries.values()):
            if not entry.container:
                self.run_async(browser.activate_entry(entry))
        self.assertEqual(len(self.app.file_checked), 2)
        self.assertIsNone(self.app.provider_sessions().active)
        self.assertEqual(self.app.file_selection_count.text, '2 selected')
        self.run_async(self.app.move_checked_files())
        self.assertIs(self.app.file_select_bar.parent, parent)
        self.assertEqual(self.app.file_select_bar.style.display, 'none')
        self.assertEqual(self.app.file_select_bar.style.visibility, 'hidden')
        self.assertTrue(all(button.style.visibility == 'hidden' for button in self.app.file_select_bar.children))
        self.assertEqual(self.app.file_select_bar.style.height, 0)
        self.run_async(self.picker.browser_editor_location((self.picker.save_as_storage.value, 'Destination')))
        self.run_async(self.picker.confirm_editor_file())
        self.assertEqual((destination / 'first.txt').read_text(), 'first.txt')
        self.assertFalse((self.root / 'first.txt').exists())
        self.assertEqual((self.root / 'conflict.txt').read_text(), 'conflict.txt')
        self.assertEqual((destination / 'conflict.txt').read_text(), 'Keep destination')
        self.assertIn('conflict.txt', self.picker.save_as_status.value)
        (destination / 'conflict.txt').unlink()
        self.run_async(self.picker.confirm_editor_file())
        self.assertEqual((destination / 'conflict.txt').read_text(), 'conflict.txt')
        self.assertFalse((self.root / 'conflict.txt').exists())
        self.assertEqual(self.app.file_status.value, 'Move finished.')

    def test_ios_move_search_keeps_browser_mounted_through_keyboard_resize(self):
        destination = self.root / 'Search destination'
        destination.mkdir()
        (self.root / 'original.txt').write_bytes(b'Original bytes')
        (self.root / 'Unrelated').mkdir()
        self.run_async(self.app.show_files(location=('Local files', '')))
        self.app.browser_file_selected(self.app.file_provider.entry('original.txt'))
        self.run_async(dict(self.app.file_item_commands())['Move…']())
        picker = self.picker
        browser = picker.editor_browser
        original_layout = list(picker.panel.children)
        browser.open_search()
        backend = type(self.app._impl)
        search_field = SimpleNamespace(isFirstResponder=True)
        with (patch.object(backend, '__module__', 'toga_iOS.app'),
              patch.object(self.app.native_host, 'adapter', SimpleNamespace(keyboard_inset=300)),
              patch.object(browser.search._impl, 'native', search_field, create=True)):
            picker.fit_keyboard(True)
            picker.fit_keyboard(True)
            self.assertIs(browser.widget.parent, picker.panel)
            self.assertIs(picker.picker_header.parent, picker.panel)
            self.assertTrue(browser.search_open)
            self.assertIsNone(picker.picker_form.parent)
            browser.search.value = 'Search destination'
            browser.render()
            result, = browser.entries
            self.assertEqual(result.label, 'Search destination')
            self.run_async(browser.activate_entry(result))
            self.assertFalse(browser.search_open)
            search_field.isFirstResponder = False
            picker.fit_keyboard(True)
            self.assertIs(browser.widget.parent, picker.panel)
        picker.fit_keyboard(False)
        self.assertEqual(list(picker.panel.children), original_layout)
        self.assertEqual(picker.picker_folder.value, destination.name)
        self.run_async(picker.confirm_editor_file())
        self.assertEqual((destination / 'original.txt').read_bytes(), b'Original bytes')
        self.assertFalse((self.root / 'original.txt').exists())

    def test_duplicate_uses_chosen_folder_and_name_without_overwriting(self):
        destination = self.root / 'Destination'
        destination.mkdir()
        (self.root / 'original.txt').write_bytes(b'Original bytes')
        (destination / 'existing.txt').write_bytes(b'Keep destination')
        self.run_async(self.app.show_files(location=('Local files', '')))
        self.app.browser_file_selected(self.app.file_provider.entry('original.txt'))
        actions = dict(self.app.file_item_commands())
        self.assertTrue({'Move…', 'Duplicate…'} <= actions.keys())
        self.assertTrue({'Pin this folder', 'New folder…', 'Cut', 'Copy regular file'}.isdisjoint(actions))
        self.run_async(actions['Duplicate…']())
        self.assertNotEqual(self.picker.save_as_name.value, 'original.txt')
        self.run_async(self.picker.browser_editor_location((self.picker.save_as_storage.value, 'Destination')))
        self.picker.save_as_name.value = 'existing.txt'
        self.run_async(self.picker.confirm_editor_file())
        self.assertEqual((destination / 'existing.txt').read_bytes(), b'Keep destination')
        self.picker.save_as_name.value = 'renamed.txt'
        self.run_async(self.picker.confirm_editor_file())
        self.assertEqual((destination / 'renamed.txt').read_bytes(), b'Original bytes')
        self.assertEqual((self.root / 'original.txt').read_bytes(), b'Original bytes')

    def test_failed_folder_creation_keeps_folder_filename_and_draft(self):
        (self.root / 'Exists').mkdir()
        for name in ('Exists', '../escape', ''):
            self.picker.new_folder_name.value = name
            self.run_async(self.picker.create_picker_folder())
            self.assertIn('Folder creation failed:', self.picker.save_as_status.value)
            self.assertEqual(self.picker.picker_folder.value, '')
            self.assertEqual(self.picker.save_as_data, b'# Unsaved')
            self.assertEqual(self.picker.save_as_name.value, 'source.md')
        self.assertFalse((self.root.parent / 'escape').exists())

    def test_failed_write_retains_draft_for_correction_and_retry(self):
        self.picker.save_as_name.value = 'invalid/name'
        self.run_async(self.picker.confirm_editor_file())
        self.assertIn('failed', self.picker.save_as_status.value.lower())
        self.assertEqual(self.picker.save_as_data, b'# Unsaved')
        self.picker.save_as_name.value = 'fixed'
        self.run_async(self.picker.confirm_editor_file())
        self.assertEqual((self.root / 'fixed.md').read_bytes(), b'# Unsaved')

    def test_storage_switch_refreshes_and_parent_state_matches_visible_root(self):
        other = Path(self.temp.name) / 'other'
        other.mkdir()
        (other / 'Only here').mkdir()
        self.picker.editor_storage_roots['Other'] = LocalFiles(other)
        self.picker.save_as_storage.items = [*self.picker.editor_storage_roots]
        self.picker.save_as_storage.value = 'Other'
        pending = self.picker._storage_refresh
        self.run_async(pending)
        self.assertEqual(self.picker.editor_picker_location, ('Other', ''))
        self.assertFalse(self.picker.picker_parent.enabled)
        self.assertEqual([r['name'] for r in self.picker.editor_picker_rows.values()], ['Only here'])
        self.picker.save_as_name.value = 'placed'
        self.run_async(self.picker.confirm_editor_file())
        self.assertTrue((other / 'placed.md').exists())
        self.assertFalse((self.root / 'placed.md').exists())

    def test_late_folder_completion_does_not_navigate_or_discard_draft(self):
        started, release = Event(), Event()
        original = LocalFiles.mkdir
        def delayed(provider, path):
            started.set()
            if not release.wait(5):
                raise RuntimeError('Fixture timed out')
            original(provider, path)
        async def exercise():
            self.picker.new_folder_name.value = 'Late'
            with patch.object(LocalFiles, 'mkdir', delayed):
                task = asyncio.create_task(self.picker.create_picker_folder())
                self.assertTrue(await asyncio.to_thread(started.wait, 5), 'Folder worker did not start')
                self.app.navigation_generation += 1
                release.set()
                await task
            self.assertEqual(self.picker.picker_folder.value, '')
            self.assertEqual(self.picker.save_as_data, b'# Unsaved')
        self.run_async(exercise())

    def test_pending_folder_cancel_returns_to_new_document_form(self):
        import toga
        from commonUtils.runtime.resources.mutations import create_resource_folder
        self.picker.clear()
        self.app.show_home()
        form = toga.Box()
        self.app.show_view(form, route='new-document', title='New document')
        origin = (self.app.native_host.state.destination,
                  len(self.app.routes.screens[self.app.native_host.state.destination]),
                  len(self.app.adaptive.detail_routes))
        self.run_async(self.picker.show_document_creation('Draft.md', origin))
        self.run_async(self.picker.choose_creation_location())
        self.run_async(self.picker.browser_editor_location(('Local', '')))
        started, release = Event(), Event()
        def delayed(*args, **kwargs):
            started.set()
            if not release.wait(5):
                raise RuntimeError('Fixture timed out')
            return create_resource_folder(*args, **kwargs)
        async def exercise():
            self.picker.new_folder_name.value = 'Cancelled'
            with patch('commonUtils.runtime.resources.mutations.create_resource_folder', delayed):
                task = asyncio.create_task(self.picker.create_picker_folder())
                self.assertTrue(await asyncio.to_thread(started.wait, 5), 'Folder worker did not start')
                self.picker.cancel_text_destination()
                release.set()
                await task
                await asyncio.sleep(.05)
            from mobile.routes import contains
            self.assertTrue(contains(self.app.body, form))
            self.assertIsNone(self.picker.creation)
            self.assertFalse((self.root / 'Cancelled').exists())
        self.run_async(exercise())

    def prepare_move(self, *, folder=False):
        self.picker.clear()
        self.run_async(self.app.show_files(location=('Local files', '')))
        provider = self.app.file_provider
        source = provider.root / ('Source' if folder else 'source.txt')
        if folder:
            source.mkdir()
            (source / 'child.txt').write_text('Keep bytes')
        else:
            source.write_text('Keep bytes')
        destination = Path(self.temp.name) / 'destination'
        destination.mkdir()
        self.app.file_roots['Destination'] = LocalFiles(destination)
        request = FileOperationRequest('move', provider, source.name)
        self.run_async(self.picker.show_destination(source.name, request))
        self.assertEqual({row.value for row in self.picker.save_as_storage.items},
                         {'Local', 'Received Files', 'Shared Files', 'Destination'})
        self.picker.save_as_storage.value = 'Destination'
        self.run_async(self.picker._storage_refresh)
        return source, destination

    def test_workspace_move_menu_accepts_scheduled_picker_for_root_and_nested_files(self):
        from features.rclone.localcrypt.mobile.resources import CryptFiles
        from mobile_build.tests.transfers.test_localcrypt_access import Client
        from mobile.action_menu import BrowserActions

        async def exercise():
            provider = CryptFiles(Path(self.temp.name) / 'ciphertext', Client(), 'Secret')
            (provider.root / 'nested').mkdir()
            for path in ('root.md', 'nested/note.md'):
                (provider.root / path).write_bytes(b'opaque fixture')
                await self.app.show_files()
                self.app.file_provider = provider
                self.app.file_path = folder = path.rpartition('/')[0]
                rows = provider.list(folder)
                self.app.file_rows = {row['name']: row for row in rows}
                self.app.set_file_items(list(self.app.file_rows))
                self.app.file_selection.value = path.rpartition('/')[2]
                browser = self.app.file_browser
                browser.set_entries(provider, folder, rows)
                entry = next(entry for entry in browser.tree.entries.values()
                             if entry.payload and entry.payload.get('path') == path)
                await browser.select(entry)
                menu = BrowserActions(browser, self.app.file_item_commands())
                menu.invoke(dict(menu.actions)['Move…'])
                await asyncio.gather(*tuple(browser.work.tasks))
                self.assertEqual(self.picker.operation.mode, 'destination')
                self.assertEqual(self.picker.operation.destination_action.path, path)
                self.assertEqual(self.picker.save_as_name.value, path.rpartition('/')[2])
                self.assertEqual(self.picker.editor_picker_location, ('Source location', folder))
                self.assertIs(self.picker._listed_provider, provider)
                if folder:
                    with (patch.object(self.app, 'cloud_client', provider.client),
                          patch.object(provider.client, 'resolve_remote', return_value='Secret alias', create=True) as resolve):
                        provider.client.generation += 1
                        self.assertTrue(await self.picker.rebind_move_source(self.picker.operation))
                        resolve.assert_called_once_with('Secret', provider.identity, cipher=True)
                        rebound = self.picker.destination_action.provider
                        self.assertEqual(rebound.root, provider.root)
                        self.assertEqual(rebound.entry(path)['path'], path)
                        rebound.close()
                self.picker.cancel_text_destination()

        self.run_async(exercise())

    def test_browsed_move_uses_created_folder_and_preserves_default_name(self):
        source, destination = self.prepare_move()
        self.picker.new_folder_name.value = 'Organized'
        self.run_async(self.picker.create_picker_folder())
        self.run_async(self.picker.confirm_editor_file())
        self.assertEqual((destination / 'Organized/source.txt').read_text(), 'Keep bytes')
        self.assertFalse(source.exists())

    def test_whole_folder_move_preserves_children(self):
        source, destination = self.prepare_move(folder=True)
        self.run_async(self.picker.confirm_editor_file())
        self.assertEqual((destination / 'Source/child.txt').read_text(), 'Keep bytes')
        self.assertFalse(source.exists())

    def test_iphone_received_video_moves_to_shared_movies_without_reading_bytes(self):
        from commonUtils.runtime.platform import OS
        from mobile.local_sources import SharedFiles
        from services.documents.locations import MobileLocalFiles
        self.picker.clear()
        self.run_async(self.app.show_files(location=('Local files', '')))
        shared = Path(self.temp.name) / 'Shared'
        received = shared / 'Received Files'
        received.mkdir(parents=True)
        (shared / 'Movies').mkdir()
        source = received / 'Movie.mkv'
        # Sparse fixture: moving 40 GiB must not read or duplicate its content.
        with source.open('wb') as stream:
            stream.write(b'video fixture')
            stream.truncate(40 * 1024 ** 3)
        before = source.stat()
        provider = MobileLocalFiles(received)
        self.app.file_roots['Received Files'] = provider
        self.app.file_roots['Shared files'] = SharedFiles(shared)
        self.run_async(self.picker.show_destination(source.name,
            FileOperationRequest('move', provider, source.name)))
        self.run_async(self.picker.browser_editor_location(('Shared Files', 'Movies')))
        local_move_path = MobileLocalFiles.local_move_path
        local_open = LocalFiles.open
        def iphone_move_path(provider, path):
            # Exercise iOS provider policy while leaving the host's actual
            # exclusive-rename syscall in place (Linux has no renamex_np).
            with patch('commonUtils.runtime.platform.get_os', return_value=OS.IOS):
                return local_move_path(provider, path)
        def reject_video_read(provider, path):
            if Path(path).name == source.name:
                raise AssertionError('Must not read video')
            return local_open(provider, path)
        with patch.object(MobileLocalFiles, 'local_move_path', iphone_move_path), \
                patch.object(LocalFiles, 'open', reject_video_read), \
                patch.object(LocalFiles, 'create_file', side_effect=AssertionError('Must not copy video')):
            self.run_async(self.picker.confirm_editor_file())
        target = shared / 'Movies/Movie.mkv'
        self.assertFalse(source.exists(), self.picker.save_as_status.value)
        self.assertEqual((target.stat().st_ino, target.stat().st_size), (before.st_ino, before.st_size))
        self.assertIsNone(self.picker._work)
        self.assertFalse(self.app.cloud_busy)
        self.assertIsNone(self.picker.destination_action)
        self.assertIn('Move finished.', self.app.file_status.value)

    def test_conflict_and_cancel_preserve_both_locations(self):
        source, destination = self.prepare_move()
        (destination / 'source.txt').write_text('Existing destination')
        self.run_async(self.picker.confirm_editor_file())
        self.assertEqual(source.read_text(), 'Keep bytes')

        self.assertEqual((destination / 'source.txt').read_text(), 'Existing destination')
        self.assertIn('Move failed:', self.picker.save_as_status.value)
        task = self.picker.cancel_text_destination()
        self.run_async(task)
        self.assertEqual(source.read_text(), 'Keep bytes')

    def test_move_progress_blocks_navigation_and_interruption_retires_before_unlocking(self):
        from unittest.mock import Mock
        from commonUtils.runtime.operations import check_cancelled
        source, destination = self.prepare_move()
        started, release = Event(), Event()
        awake = Mock()
        from mobile.document_mutations import DocumentMutation
        def delayed(plan, cancelled):
            plan.progress(phase='Copying', done=5_000_000, total=10_000_000, files=0, total_files=1)
            started.set()
            if not release.wait(5):
                raise RuntimeError('Move fixture timed out')
            check_cancelled(cancelled)
        async def exercise():
            with patch('mobile.keep_awake.AwakeLease', return_value=awake), \
                    patch.object(DocumentMutation, 'execute', delayed):
                task = asyncio.create_task(self.picker.confirm_editor_file())
                try:
                    self.assertTrue(await asyncio.to_thread(started.wait, 5))
                    await asyncio.sleep(.3)
                    self.assertIn('Copying · 50%', self.picker.save_as_status.value)
                    self.assertEqual(self.picker.move_progress.value, 50)
                    self.assertIs(self.picker.panel.children[0], self.picker.move_notice)
                    self.assertIs(self.picker.save_as_status.parent, self.picker.move_notice)
                    self.assertFalse(self.app.select_destination('settings'))
                    self.assertFalse(self.picker.save_as_name.enabled)
                    self.picker.cancel(interrupted=True)
                    self.assertTrue(self.picker.moving())
                    awake.close.assert_not_called()
                finally:
                    release.set()
                    await task
                self.assertFalse(self.picker.moving())
                self.assertFalse(self.app.cloud_busy)
                awake.close.assert_called_once_with()
                self.assertIn('leaving the app or locking', self.picker.save_as_status.value)
                self.assertIsNone(self.picker.move_progress.parent)
                self.assertTrue(self.picker.save_as_name.enabled)
        self.run_async(exercise())
        self.assertTrue(source.exists())
        self.assertEqual(list(destination.iterdir()), [])

    def test_read_only_destination_disables_save_and_folder_creation(self):
        from commonUtils.runtime.resources.provider import ResourceCapabilities
        class ReadOnly(LocalFiles):
            capabilities = ResourceCapabilities()
        other = Path(self.temp.name) / 'readonly'
        other.mkdir()
        self.picker.editor_storage_roots['Read only'] = ReadOnly(other)
        self.picker.save_as_storage.items = list(self.picker.editor_storage_roots)
        self.picker.save_as_storage.value = 'Read only'
        self.run_async(self.picker._storage_refresh)
        self.assertFalse(self.picker.picker_primary.enabled)
        self.assertFalse(self.picker.picker_new_folder.enabled)
        self.assertEqual(self.picker.save_as_data, b'# Unsaved')

    def test_decrypted_move_requires_explicit_confirmation(self):
        source, destination = self.prepare_move()
        self.picker.destination_action.provider.private = True  # Synthetic privacy metadata.
        with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value=False)) as confirm:
            self.run_async(self.picker.confirm_editor_file())
            confirm.assert_awaited_once()
        self.assertEqual(source.read_text(), 'Keep bytes')
        self.assertEqual(list(destination.iterdir()), [])

    def test_folder_cannot_move_into_its_descendant(self):
        source, _ = self.prepare_move(folder=True)
        self.picker.save_as_storage.value = 'Local'
        self.run_async(self.picker._storage_refresh)
        self.run_async(self.picker.browser_editor_location(('Local', 'Source')))
        self.picker.save_as_name.value = 'Nested'
        self.run_async(self.picker.confirm_editor_file())
        self.assertTrue((source / 'child.txt').is_file())
        self.assertFalse((source / 'Nested').exists())
        self.assertIn('Move failed:', self.picker.save_as_status.value)
