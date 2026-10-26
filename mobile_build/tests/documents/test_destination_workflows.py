"""Real provider bytes for Save As naming, folder creation and browsed moves."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
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
        self.app.loop.close()
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
        self.picker.save_as_name.value = 'invalid.exe'
        self.run_async(self.picker.confirm_editor_file())
        self.assertIn('supported', self.picker.save_as_status.value)
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
                while not started.is_set():
                    await asyncio.sleep(.01)
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
                while not started.is_set():
                    await asyncio.sleep(.01)
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
        self.picker.save_as_storage.value = 'Destination'
        self.run_async(self.picker._storage_refresh)
        return source, destination

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
        self.picker.save_as_storage.value = 'Local files'
        self.run_async(self.picker._storage_refresh)
        self.run_async(self.picker.browser_editor_location(('Local files', 'Source')))
        self.picker.save_as_name.value = 'Nested'
        self.run_async(self.picker.confirm_editor_file())
        self.assertTrue((source / 'child.txt').is_file())
        self.assertFalse((source / 'Nested').exists())
        self.assertIn('Move failed:', self.picker.save_as_status.value)
