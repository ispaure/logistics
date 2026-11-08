"""User-created documents publish into browsable local or encrypted folders."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.SMOKE
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from mobile.app import LogisticsMobile
from mobile.local_sources import device_files
from mobile_build.tests.support.localcrypt import CreationClient


class DocumentCreationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        LogisticsMobile.storage_root = self.root
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_home()

    def tearDown(self):
        self.app.main_window.close()
        self.app.loop.run_until_complete(self.app.loop.shutdown_default_executor())
        close_loop(self.app.loop)
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_naming_form_replaces_type_alert_and_cancel_keeps_origin(self):
        origin = self.app.body
        files = {p for p in self.root.rglob('*') if p.is_file()}
        with patch.object(self.app.main_window, 'dialog', new=AsyncMock()) as dialog:
            self.app.loop.run_until_complete(self.app.choose_document_type())
        dialog.assert_not_awaited()
        self.app.editor_picker().cancel_text_destination()
        self.assertIs(self.app.body, origin)
        self.assertEqual({p for p in self.root.rglob('*') if p.is_file()}, files)

    def test_native_refresh_does_not_drop_creation_but_navigation_does(self):
        app = self.app
        pending = app.choose_document_type()
        app.navigation_generation += 1
        app.loop.run_until_complete(pending)
        self.assertTrue(app.editor_picker().visible())
        app.editor_picker().cancel_text_destination()
        pending = app.choose_document_type()
        app.show_documents_hub()
        app.loop.run_until_complete(pending)
        self.assertFalse(app.editor_picker().visible())

    def test_new_request_waits_for_initial_connections_and_keeps_navigation_guard(self):
        app = self.app
        async def exercise(navigate):
            ready = asyncio.Event()
            app.set_cloud_busy(True)
            async def restore():
                await ready.wait()
                app.set_cloud_busy(False)
            app.cloud_startup_task = app.loop.create_task(restore())
            pending = app.choose_document_type()
            await asyncio.sleep(0)
            self.assertIsNone(app.editor_picker().panel)
            if navigate:
                app.show_documents_hub()
            ready.set()
            await pending
            self.assertEqual(app.editor_picker().visible(), not navigate)
            if not navigate:
                app.editor_picker().cancel_text_destination()
        app.loop.run_until_complete(exercise(False))
        app.loop.run_until_complete(exercise(True))

    def choose(self, name, kind='Plain text (.txt)', *, local=True):
        with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=dict((label, ext) for label, ext in __import__('mobile.document_choices', fromlist=['CHOICES']).CHOICES)[kind])):
            self.app.loop.run_until_complete(self.app.choose_document_type())
        picker = self.app.editor_picker()
        form = picker.panel
        picker.save_as_name.value, picker.creation_type.value = name, kind
        self.app.loop.run_until_complete(picker.choose_creation_location())
        if local:
            row = next(row for row in picker.editor_picker_rows.values() if row['name'] == 'Local')
            self.app.loop.run_until_complete(picker.browser_editor_folder(row))
        return form, picker

    def test_editing_name_keeps_chosen_folder_without_publishing(self):
        from features.notebooks.notebook import Notebook
        app = self.app
        origin = app.body
        compact = patch.object(app.adaptive, 'content_width', return_value=390)
        compact.start()
        self.addCleanup(compact.stop)
        _, picker = self.choose('Trip.txt')
        panel, location = picker.panel, picker.editor_picker_location
        self.assertTrue(picker.visible())
        app.routes.back()
        self.assertIs(picker.panel, picker.name_panel)
        self.assertIn(picker.creation_formats.tabs, picker.name_content.children)
        self.assertFalse((self.root / 'LocalFiles/Trip.txt').exists())
        picker.creation_type.value = 'Markdown (.md)'
        self.assertEqual(picker.save_as_name.value, 'Trip.md')
        picker.creation_type.value = 'Remarkable Document (.rmdoc)'
        self.assertEqual(picker.save_as_name.value, 'Trip.rmdoc')
        picker.save_as_name.value = 'Final title'
        app.loop.run_until_complete(picker.choose_creation_location())
        self.assertIs(picker.panel, panel)
        self.assertEqual(picker.editor_picker_location, location)
        app.loop.run_until_complete(picker.confirm_editor_file())
        path = self.root / 'LocalFiles/Final title.rmdoc'
        self.assertEqual(Notebook.read(path.read_bytes()).name, 'Final title')
        self.assertFalse((self.root / 'LocalFiles/Trip.rmdoc').exists())
        self.assertNotIn('text-destination', [row[0] for row in app.routes.screens['home']])
        self.assertIsNot(app.body, origin)

    def test_wide_layout_keeps_edits_folder_and_route_across_width_changes(self):
        from mobile.fold_layout import Division
        app = self.app
        origin = app.body
        with patch.object(app.adaptive, 'content_width', return_value=810) as width:
            _, picker = self.choose('Wide')
            layout = picker.creation_layout
            route = app.body
            self.assertTrue(layout.paired)
            self.assertEqual(list(layout.children), [picker.name_panel, layout.gutter, picker.location_panel])
            with patch('mobile.creation_layout.division', return_value=Division(350, 0, 24, 800)):
                layout.reflow()
                self.assertEqual(picker.name_panel.style.width, 350)
                self.assertEqual(layout.gutter.style.width, 24)
            picker.save_as_name.value = '../invalid'
            self.assertFalse(picker.picker_primary.enabled)
            picker.save_as_name.value = 'Wide draft'
            picker.creation_type.value = 'Markdown (.md)'
            self.assertTrue(picker.picker_primary.enabled)
            self.assertIn('Wide draft.md', picker.picker_destination.text)
            width.return_value = 390
            layout.reflow()
            self.assertFalse(layout.paired)
            self.assertIs(picker.edit_name.parent, picker.creation_location.heading)
            self.assertEqual(picker.editor_picker_location, ('Local', ''))
            self.assertIs(app.body, route)
            width.return_value = 810
            layout.reflow()
            self.assertIsNone(picker.edit_name.parent)
            app.routes.back()
            self.assertIs(app.body, origin)
            self.assertFalse((self.root / 'LocalFiles/Wide draft.md').exists())

    def test_folder_entry_keeps_destination_fixed_until_created_or_cancelled(self):
        app = self.app
        with patch.object(app.adaptive, 'content_width', return_value=810) as width:
            _, picker = self.choose('Draft')
            layout = picker.creation_layout
            picker.show_new_folder()
            picker.new_folder_name.value = 'Nested'
            picker.fit_keyboard(True)
            width.return_value = 390
            layout.reflow()
            width.return_value = 810
            layout.reflow()
            self.assertFalse(picker.picker_primary.enabled)
            self.assertFalse(app.loop.run_until_complete(picker.browser_editor_location(('Received Files', ''))))
            app.loop.run_until_complete(picker.confirm_editor_file())
            self.assertFalse((self.root / 'LocalFiles/Draft.txt').exists())
            app.loop.run_until_complete(picker.create_picker_folder())
            self.assertEqual(picker.editor_picker_location, ('Local', 'Nested'))
            picker.fit_keyboard(False)
            self.assertEqual(list(picker.location_panel.children)[:4], list(picker._browse_controls))
            picker.show_new_folder()
            picker.new_folder_name.value = '../invalid'
            app.loop.run_until_complete(picker.create_picker_folder())
            self.assertIn('Folder creation failed:', picker.save_as_status.value)
            picker.hide_new_folder()
            self.assertEqual(picker.save_as_status.value, '')
            self.assertTrue(picker.picker_primary.enabled)
            app.loop.run_until_complete(picker.confirm_editor_file())
            self.assertTrue((self.root / 'LocalFiles/Nested/Draft.txt').is_file())

    def test_folder_parent_links_keep_document_pending_while_creating_siblings(self):
        _, picker = self.choose('Draft')
        browser = picker.editor_browser
        for name in ('Projects', 'Notes'):
            picker.show_new_folder()
            picker.new_folder_name.value = name
            self.app.loop.run_until_complete(picker.create_picker_folder())
        self.assertEqual(picker.editor_picker_location, ('Local', 'Projects/Notes'))
        links = [child for child in picker.creation_location.crumbs.children
                 if hasattr(child, '_creation_parent_link')]
        picker.show_new_folder()
        self.assertFalse(links[0].enabled)
        self.app.loop.run_until_complete(links[0].on_press())
        self.assertEqual(picker.editor_picker_location, ('Local', 'Projects/Notes'))
        picker.hide_new_folder()
        self.app.loop.run_until_complete(links[1].on_press())
        self.assertEqual(picker.editor_picker_location, ('Local', 'Projects'))
        picker.show_new_folder()
        picker.new_folder_name.value = 'Research'
        self.app.loop.run_until_complete(picker.create_picker_folder())
        self.assertIs(picker.editor_browser, browser)
        self.assertTrue((self.root / 'LocalFiles/Projects/Notes').is_dir())
        self.assertTrue((self.root / 'LocalFiles/Projects/Research').is_dir())
        self.assertFalse(list((self.root / 'LocalFiles').rglob('Draft.txt')))
        self.app.loop.run_until_complete(picker.confirm_editor_file())
        self.assertTrue((self.root / 'LocalFiles/Projects/Research/Draft.txt').is_file())
        picker.clear()
        self.assertFalse(picker.creation_location.crumbs.children)

    def test_next_reads_current_name_and_storage_echo_keeps_nested_location(self):
        app = self.app
        folder = self.root / 'LocalFiles' / 'Project notes'
        folder.mkdir(parents=True)
        with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value='txt')):
            app.loop.run_until_complete(app.choose_document_type())
        picker = app.editor_picker()
        # Return can precede the native field's queued change notification.
        picker.save_as_name.on_change = None
        picker.save_as_name.value = 'Field notes'
        self.assertTrue(picker.next_button.enabled)  # Type-first flow has a valid default name.
        app.loop.run_until_complete(picker.choose_creation_location())
        self.assertIs(picker.panel, picker.location_panel)
        app.loop.run_until_complete(picker.browser_editor_location(('Local', folder.name)))
        picker.change_editor_storage()
        self.assertEqual(picker.picker_folder.value, folder.name)
        self.assertIn('Field notes.txt', picker.picker_destination.text)
        self.assertIn(folder.name, ' '.join(picker.picker_destination.text.split()))
        self.assertFalse(list(folder.iterdir()))

    def test_received_files_notebook_creation_on_android_without_exclusive_rename(self):
        import errno
        from commonUtils.runtime.platform import OS
        from features.notebooks.notebook import Notebook
        from mobile.incoming_files import inbox_path
        _, picker = self.choose('Received sketch', 'Remarkable Document (.rmdoc)', local=False)
        row = next(row for row in picker.editor_picker_rows.values() if row['name'] == 'Received Files')
        self.app.loop.run_until_complete(picker.browser_editor_folder(row))
        with patch('commonUtils.runtime.resources.local.rename_exclusive',
                   side_effect=OSError(errno.EINVAL, 'SD card rejects rename flags')), \
                patch('commonUtils.runtime.platform.get_os', return_value=OS.ANDROID):
            self.app.loop.run_until_complete(picker.confirm_editor_file())
        received = inbox_path(self.root)
        path = received / 'Received sketch.rmdoc'
        self.assertTrue(path.is_file(), picker.save_as_status.value)
        self.assertEqual(Notebook.read(path.read_bytes()).name, 'Received sketch')
        self.assertIsNotNone(self.app.notebook_panel)
        self.assertEqual(sorted(p.name for p in received.iterdir()), ['Received sketch.rmdoc'])

    def test_sd_received_notebook_creation_and_workspace_reopen(self):
        import json
        from features.notebooks.mobile.documents import panels
        external = TemporaryDirectory()
        self.addCleanup(external.cleanup)
        volume = Path(external.name).resolve()
        base = volume / 'Logistics'
        base.mkdir()
        token = 'a' * 32
        (base / '.logistics-storage').write_text(token)
        (self.root / 'collection-storage.json').write_text(json.dumps(dict(volume=str(volume), token=token)))
        _, picker = self.choose('SD notebook', 'Remarkable Document (.rmdoc)', local=False)
        row = next(row for row in picker.editor_picker_rows.values() if row['name'] == 'Received Files')
        self.app.loop.run_until_complete(picker.browser_editor_folder(row))
        self.app.loop.run_until_complete(picker.confirm_editor_file())
        panel = self.app.notebook_panel
        self.assertTrue(panels(self.app), picker.save_as_status.value)
        self.assertEqual(panel.document.resource.provider.root, base / 'Received Files')
        session = panel.session
        self.assertTrue(self.app.close_session(session.id))
        self.app.loop.run_until_complete(self.app.open_download(path=base / 'Received Files/SD notebook.rmdoc'))
        self.assertIn(self.app.notebook_panel.session.id, panels(self.app))
        self.assertEqual(self.app.notebook_panel.session.resource, session.resource)

    def test_cold_start_client_and_credentials_changes_do_not_leave_loading_form(self):
        import asyncio
        from types import SimpleNamespace
        app = self.app
        original = asyncio.to_thread
        calls = []
        async def restoring(*args, **kwargs):
            calls.append(args[0])
            if len(calls) == 1:
                app.cloud_client = SimpleNamespace(generation=0, cancel=lambda: None)
            elif len(calls) == 2:
                app.cloud_client.generation = 1
            return await original(*args, **kwargs)
        with patch('mobile.editor_picker.asyncio.to_thread', side_effect=restoring), \
                patch.object(app.main_window, 'dialog', new=AsyncMock(return_value='txt')):
            app.loop.run_until_complete(app.choose_document_type())
            picker = app.editor_picker()
            picker.save_as_name.value = 'Cold start'
            app.loop.run_until_complete(picker.choose_creation_location())
        picker = app.editor_picker()
        self.assertEqual(picker.editor_picker_location, ('Shared Files', ''))
        self.assertIn('Local', [row['name'] for row in picker.editor_picker_rows.values()])
        self.assertFalse(app.cloud_busy)
        self.assertNotEqual(picker.save_as_status.value, 'Loading folder…')

    def test_creation_keyboard_compaction_keeps_name_type_and_destination(self):
        narrow = patch.object(self.app.adaptive, 'content_width', return_value=390)
        narrow.start()
        self.addCleanup(narrow.stop)
        _, picker = self.choose('Keep my name', 'Remarkable Document (.rmdoc)')
        name, kind = picker.save_as_name, picker.creation_type
        location = picker.editor_picker_location
        picker.show_creation_name()
        picker.fit_keyboard(True)
        self.assertIn(picker.creation_formats.tabs, picker.name_content.children)
        self.assertNotIn(picker.creation_formats.cards, picker.name_view.children)
        self.assertTrue(picker.creation_formats.tabbed)
        self.assertEqual([' '.join(button.text.split()) for button in picker.creation_formats.tab_buttons.values()],
                         ['Text', 'Markdown', 'reMarkable Notebook'])
        self.assertIn(name, picker.name_view.children)
        self.assertNotIn(picker.save_as_storage, picker.name_panel.children)
        self.assertIs(picker.name_form.content, picker.name_view)
        self.assertEqual(name.value, 'Keep my name.rmdoc')
        self.assertEqual(name._impl.get_value(), 'Keep my name')
        picker.fit_keyboard(False)
        self.assertIn(picker.creation_formats.tabs, picker.name_content.children)
        self.assertEqual(picker.editor_picker_location, location)
        self.assertEqual(kind.value, 'Remarkable Document (.rmdoc)')

    def test_change_format_dismisses_keyboard_without_replacing_name_or_location(self):
        with patch.object(self.app.adaptive, 'content_width', return_value=810):
            _, picker = self.choose('Research', 'Markdown (.md)')
        picker.show_creation_name()
        field, location = picker.save_as_name, picker.editor_picker_location
        picker.fit_keyboard(True)
        with patch('mobile.keyboard.dismiss_picker_keyboard') as dismiss:
            picker.creation_formats.change.on_press()
        dismiss.assert_called_once_with(picker)
        self.assertIs(picker.save_as_name, field)
        self.assertIn(picker.creation_formats.cards, picker.name_view.children)
        picker.creation_formats.buttons['Remarkable Document (.rmdoc)'].on_press()
        self.assertEqual(picker.destination_filename(), 'Research.rmdoc')
        self.assertEqual(picker.editor_picker_location, location)
        self.assertIn('Research.rmdoc', picker.picker_destination.text)
        self.assertFalse(list((self.root / 'LocalFiles').iterdir()))

    def test_wide_entry_browses_immediately_and_create_does_not_require_next(self):
        app = self.app
        with patch.object(app.adaptive, 'content_width', return_value=810):
            app.loop.run_until_complete(app.choose_document_type())
            picker = app.editor_picker()
            self.assertIs(picker.panel, picker.name_panel)
            self.assertIs(picker.location_panel.parent, picker.creation_layout)
            self.assertEqual(picker.editor_picker_location, ('Shared Files', ''))
            self.assertIsNone(picker.next_button.parent)
            app.loop.run_until_complete(picker.browser_editor_location(('Local', '')))
            picker.save_as_name.value = 'No extra step'
            picker.creation_formats.buttons['Markdown (.md)'].on_press()
            app.loop.run_until_complete(picker.confirm_editor_file())
            self.assertTrue((self.root / 'LocalFiles/No extra step.md').is_file())

    def test_format_cards_use_available_space_and_disable_during_io(self):
        with patch.object(self.app.adaptive, 'content_width', return_value=810):
            _, picker = self.choose('Space')
        formats = picker.creation_formats
        formats.fit(True, 280, 700)
        self.assertTrue(formats.compact)
        self.assertIsNone(formats.cards.parent)
        formats.fit(True, 600, 400)
        self.assertFalse(formats.compact)
        formats.fit(True, 600, 280)
        self.assertTrue(formats.compact)
        work = picker._begin_work()
        self.assertFalse(formats.change.enabled)
        self.assertTrue(all(not button.enabled for button in formats.buttons.values()))
        picker._finish_work(work)
        self.assertTrue(formats.change.enabled)

    def test_ios_location_dropdown_preserves_format_cards(self):
        from types import SimpleNamespace
        with patch.object(self.app.adaptive, 'content_width', return_value=810):
            _, picker = self.choose('Dropdown')
        picker.creation_type.value = 'Markdown (.md)'
        storage = SimpleNamespace(isFirstResponder=True)
        name = SimpleNamespace(isFirstResponder=False)
        with patch.object(type(self.app._impl), '__module__', 'toga_iOS.app'), \
                patch.object(picker.save_as_storage._impl, 'native', storage, create=True), \
                patch.object(picker.save_as_name._impl, 'native', name, create=True), \
                patch.object(self.app.native_host, 'adapter', SimpleNamespace(keyboard_inset=350)):
            picker.fit_keyboard(True)
            self.assertFalse(picker.creation_formats.compact)
            self.assertIn(picker.creation_formats.cards, picker.name_view.children)
            self.assertIsNone(picker.creation_formats.row.parent)
            self.assertEqual(picker.destination_filename(), 'Dropdown.md')
            storage.isFirstResponder = False
            name.isFirstResponder = True
            picker.fit_keyboard(True)
            self.assertTrue(picker.creation_formats.compact)
            name.isFirstResponder = False
            picker.fit_keyboard(True)
            self.assertTrue(picker.creation_formats.compact)
            storage.isFirstResponder = True
            picker.fit_keyboard(True)
            self.assertFalse(picker.creation_formats.compact)
            self.assertEqual(picker.destination_filename(), 'Dropdown.md')

    def test_phone_tabs_switch_format_without_dismissing_keyboard_or_moving_name(self):
        narrow = patch.object(self.app.adaptive, 'content_width', return_value=390)
        narrow.start()
        self.addCleanup(narrow.stop)
        _, picker = self.choose('Phone draft')
        picker.show_creation_name()
        name, parent, location = picker.save_as_name, picker.save_as_name.parent, picker.editor_picker_location
        picker.fit_keyboard(True)
        with patch('mobile.keyboard.dismiss_picker_keyboard') as dismiss:
            picker.creation_formats.tab_buttons['Markdown (.md)'].on_press()
        dismiss.assert_not_called()
        self.assertTrue(picker._compact_keyboard)
        self.assertEqual(picker.destination_filename(), 'Phone draft.md')
        self.assertIs(name.parent, parent)
        self.assertEqual(picker.editor_picker_location, location)
        self.assertIn(picker.creation_formats.tabs, picker.name_content.children)
        self.assertIsNone(picker.creation_formats.row.parent)

    def test_phone_tabs_switch_back_to_wide_cards_and_keep_selection(self):
        with patch.object(self.app.adaptive, 'content_width', return_value=390) as width:
            _, picker = self.choose('Resize')
            picker.creation_formats.tab_buttons['Remarkable Document (.rmdoc)'].on_press()
            width.return_value = 810
            picker.creation_layout.reflow()
            self.assertFalse(picker.creation_formats.tabbed)
            self.assertIn(picker.creation_formats.cards, picker.name_view.children)
            self.assertIsNone(picker.creation_formats.tabs.parent)
            width.return_value = 390
            picker.creation_layout.reflow()
            self.assertTrue(picker.creation_formats.tabbed)
            self.assertEqual(picker.destination_filename(), 'Resize.rmdoc')

    def test_large_unpaired_form_keeps_cards(self):
        with patch.object(self.app.adaptive, 'content_width', return_value=810):
            _, picker = self.choose('Wide portrait')
        # A horizontal fold can keep a large form on one page.
        picker.creation_layout.paired = False
        picker.creation_formats.fit(False, 700, 810)
        self.assertFalse(picker.creation_formats.tabbed)
        self.assertIn(picker.creation_formats.cards, picker.name_view.children)
        self.assertIsNone(picker.creation_formats.tabs.parent)

    def test_short_phone_keyboard_hides_redundant_labels_and_restores_them(self):
        with patch.object(self.app.adaptive, 'content_width', return_value=390):
            _, picker = self.choose('Short')
        formats = picker.creation_formats
        formats.fit(True, 90, 390)
        self.assertIsNone(formats.name_label.parent)
        self.assertIsNone(picker.effective_name.parent)
        self.assertIn(picker.save_as_name, picker.name_view.children)
        picker.save_as_name.value = '../invalid'
        formats.fit(True, 90, 390)
        self.assertIn(picker.effective_name, picker.name_view.children)
        formats.fit(False, 600, 390)
        self.assertIn(formats.name_label, picker.name_view.children)
        self.assertEqual(picker.save_as_name.style.height, 48)

    def test_creation_starts_at_browse_all_files_and_can_return_from_collections(self):
        _, picker = self.choose('Anywhere', local=False)
        self.assertEqual(picker.editor_picker_location, ('Shared Files', ''))
        self.assertEqual(picker.editor_provider('Shared Files').root, device_files(self.root).root)
        self.assertFalse(picker.picker_primary.enabled)
        self.assertFalse(picker.picker_new_folder.enabled)
        self.assertEqual(picker.picker_primary.text, 'Create here')
        self.assertIn('Open a folder', picker.save_as_status.value)
        for name in ('Local', 'Received Files'):
            row = next(row for row in picker.editor_picker_rows.values() if row['name'] == name)
            self.app.loop.run_until_complete(picker.browser_editor_folder(row))
            self.assertEqual(picker.editor_picker_location, (name, ''))
            self.assertTrue(picker.picker_primary.enabled)
            self.assertTrue(picker.picker_parent.enabled)
            self.app.loop.run_until_complete(picker.parent_editor_folder())
            self.assertEqual(picker.editor_picker_location, ('Shared Files', ''))

    def test_ios_shared_root_and_collection_destinations_publish_documents(self):
        from services.documents.locations import use_shared_local, _shared_local_roots
        from mobile.incoming_files import inbox_path
        shared_directory = TemporaryDirectory()
        self.addCleanup(shared_directory.cleanup)
        shared = Path(shared_directory.name)
        use_shared_local(self.root, shared)
        self.addCleanup(_shared_local_roots.pop, self.root)
        (shared / 'Notes').mkdir()
        for label, folder, target in (
                ('Shared Files', 'Notes', shared / 'Notes/Public.md'),
                ('Local', '', shared / 'Local/Public.md'),
                ('Received Files', '', inbox_path(self.root) / 'Public.md')):
            with self.subTest(label=label):
                _, picker = self.choose('Public', 'Markdown (.md)', local=False)
                path = folder if label == 'Shared Files' else picker.editor_provider(label).root.name
                self.app.loop.run_until_complete(picker.browser_editor_location(('Shared Files', path)))
                self.assertEqual(picker.editor_picker_location, (label, folder))
                self.app.loop.run_until_complete(picker.confirm_editor_file())
                self.assertTrue(target.is_file(), picker.save_as_status.value)

    def test_notes_library_creation_uses_storage_picker_and_opens_marked_folder(self):
        import toga
        from features.notes_library.notes import LIBRARY_MARKER, vault_root
        from features.rclone.localcrypt.mobile.resources import CryptFiles
        from mobile.incoming_files import inbox_path
        from services.documents.locations import collection_path, use_shared_local, _shared_local_roots

        app = self.app
        shared_directory = TemporaryDirectory()
        self.addCleanup(shared_directory.cleanup)
        shared = Path(shared_directory.name)
        use_shared_local(self.root, shared)
        self.addCleanup(_shared_local_roots.pop, self.root)
        app.cloud_client = CreationClient()
        crypt = CryptFiles(self.root / 'LocalCryptFolders', app.cloud_client, 'Secret')
        self.addCleanup(crypt.close)

        async def exercise():
            for label, destination in (
                ('Local', collection_path(self.root)),
                ('Received Files', inbox_path(self.root)),
                ('Shared Files', shared),
                ('LocalCrypt: Secret', None),
            ):
                with self.subTest(label=label):
                    app.show_documents_hub()
                    button = next(item for item in app.document_notes_list.children
                                  if getattr(item, 'text', '') == 'New Notes Library…')
                    await button.on_press()
                    picker = app.editor_picker()
                    self.assertTrue(picker.visible())
                    await picker.browser_editor_location((label, ''))
                    picker.show_new_folder()
                    self.assertFalse(picker.picker_primary.enabled)
                    picker.new_folder_name.value = 'Projects'
                    await picker.create_picker_folder()
                    picker.save_as_name.value = 'Journal'
                    await picker.confirm_editor_file()
                    owner = app.vault_browser
                    self.assertIsNotNone(owner, picker.save_as_status.value)
                    self.assertEqual(owner.root, 'Projects/Journal')
                    self.assertFalse(picker.visible())
                    self.assertEqual(vault_root(owner.provider, owner.root,
                                                owner.provider.list(owner.root)), owner.root)
                    marker = owner.root + '/' + LIBRARY_MARKER
                    if destination is None:
                        self.assertTrue(owner.provider.private)
                        self.assertEqual(crypt._physical(marker).read_bytes(), b'cipher:')
                    else:
                        self.assertEqual((destination / marker).read_bytes(), b'')
                    owner.dispose()

        with (patch.object(app, 'existing_crypt_locations', return_value={'LocalCrypt: Secret': crypt}),
              patch('services.documents.mobile_views.document_webview',
                    side_effect=lambda resource=None, inline_video=False, **options: toga.WebView(**options))):
            app.loop.run_until_complete(exercise())

    def test_tablet_notes_picker_and_local_tab_use_individual_folders(self):
        import toga
        from features.notes_library.notes import LIBRARY_MARKER
        from services.documents.mobile_locations import _enabled
        from services.documents.migrations.mobile_layout import prepare_android

        app = self.app
        self.addCleanup(_enabled.discard, self.root)
        prepare_android(self.root)
        (self.root / 'Files/Projects/Archive').mkdir(parents=True)
        (self.root / 'Files/2026-Notes').mkdir()
        (self.root / 'Rclone Copies/Reference').mkdir()
        async def exercise():
            app.show_documents_hub()
            button = next(item for item in app.document_notes_list.children
                          if getattr(item, 'text', '') == 'New Notes Library…')
            await button.on_press()
            picker = app.editor_picker()
            self.assertEqual(picker.editor_picker_location, ('On My Tablet', ''))
            self.assertEqual(list(picker.editor_storage_roots), ['On My Tablet', 'Reference - Local Copy'])
            self.assertEqual({row['name'] for row in picker.editor_picker_rows.values()}, {'Projects', '2026-Notes'})
            picker.save_as_name.value = 'Rclone Copies'
            await picker.confirm_editor_file()
            self.assertIn('reserved', picker.save_as_status.value)
            picker.save_as_name.value = 'Journal'
            await picker.confirm_editor_file()
            self.assertTrue((self.root / 'Files/Journal' / LIBRARY_MARKER).is_file())
            self.assertEqual(app.vault_browser.root, 'Journal')
            app.vault_browser.dispose()
            app.show_locations()
            overview = app.body
            app.folder_local_buttons['Others'].on_press()
            await asyncio.sleep(0)
            self.assertIs(app.body, overview)
            self.assertEqual(app.folder_local_buttons['Others'].text, 'On My Tablet')
            tab = app.folder_tab_views['Local', 'Others']
            root = tab.nodes['All files',]
            self.assertEqual(root.button.text, 'On My Tablet')
            self.assertIsNotNone(root.guide)
            self.assertEqual(set(tab.nodes), {('All files',), ('All files', 'Projects'),
                                             ('All files', '2026-Notes'), ('All files', 'Journal')})
            self.assertIs(tab.nodes['All files', 'Projects'].row.parent, root.child_content)
            await root.button.on_press()
            self.assertEqual(app.file_loaded_location, ('Shared files', ''))
            self.assertEqual(app.files_view._folder_screen.title, 'On My Tablet')
            app.show_locations()
            await app.folder_buttons['Projects'].on_press()
            self.assertEqual(app.file_loaded_location, ('Shared files', 'Projects'))
            self.assertEqual(app.files_view._folder_screen.root_title, 'On My Tablet')
            self.assertEqual(app.file_provider.root, self.root / 'Files')
            from mobile.file_operations import FileOperationRequest
            (self.root / 'Files/Projects/Move.txt').write_text('move me')
            await picker.show_destination('Move.txt', FileOperationRequest('move', app.file_provider, 'Projects/Move.txt'))
            self.assertEqual(list(picker.editor_storage_roots), ['On My Tablet', 'Reference - Local Copy'])
            self.assertTrue(await picker.browser_editor_location(('Reference - Local Copy', '')))
            self.assertEqual(picker.editor_picker_location, ('Reference - Local Copy', 'Reference'))
            self.assertFalse(picker.picker_parent.enabled)
            picker.cancel_text_destination()
            app.show_locations()
            app.folder_local_buttons['Rclone'].on_press()
            self.assertNotIn('Rclone Copies', app.folder_buttons)
            self.assertIn('Reference', app.folder_buttons)

        with (patch('mobile.local_sources.device_label', return_value='Tablet'),
              patch('services.documents.mobile_views.document_webview',
                    side_effect=lambda resource=None, inline_video=False, **options: toga.WebView(**options))):
            app.loop.run_until_complete(exercise())

    def test_creation_forms_share_actual_synced_copy_destinations(self):
        import toga
        from features.notes_library.notes import LIBRARY_MARKER

        app = self.app
        app.cloud_client = client = CreationClient()
        app.cloud_crypt_remotes = {'Network only', 'Missing', 'Locked'}
        store = app.mirror_store()
        for target, remote, crypt, exists in (
                ('Office', 'Office', False, True),
                ('Deleted', 'Deleted', False, False),
                ('Missing', 'Missing', True, False),
                ('Locked', 'Locked', True, True),
                ('legacy-Old', 'legacy-Old', False, True)):
            prefix = 'Projects'.encode().hex() if crypt else ''
            connection = 'c' * 64 if remote == 'Locked' else client.connection
            job = dict(id=target, remote=remote, target=target, crypt=crypt, prefix=prefix, identity=connection,
                       cipher_identity=client.identity if crypt else '')
            store.jobs[target] = job
            if exists:
                store.target(job).mkdir(parents=True)

        locked = 'Locked - Encrypted Copy (Locked)'
        unlocked = 'Locked - Encrypted Copy'
        package = ('zip-key', {'remotes': {'Locked': 'c' * 64}})
        local = 'Office - Local Copy'
        office = store.target(store.jobs['Office'])
        (office / 'Existing' / 'Nested').mkdir(parents=True)
        (office / 'Readme.txt').write_text('Ordinary file')

        async def exercise():
            picker = app.editor_picker()
            for mode, name in (('save', 'Draft.md'), ('folder', 'Journal')):
                creation = ('home', len(app.routes.screens['home']), 0) if mode == 'save' else None
                await picker.show_editor_browser(mode, name, b'' if creation else None, creation=creation)
                if creation:
                    await picker.choose_creation_location()
                self.assertEqual({row.value for row in picker.save_as_storage.items},
                                 {'Local', 'Shared Files', 'Received Files', local, locked})
                if mode == 'save':
                    self.assertTrue(await picker.browser_editor_location((local, '')))
                    self.assertEqual(picker.editor_picker_location, (local, 'Office'))
                    self.assertFalse(picker.picker_parent.enabled)
                    await picker.confirm_editor_file()
                    self.assertEqual((store.target(store.jobs['Office']) / 'Draft.md').read_bytes(), b'')
                else:
                    picker.save_as_storage.value = local
                    picker.change_editor_storage()
                    await picker._storage_refresh
                    self.assertEqual(picker.editor_picker_location, (local, 'Office'))
                    self.assertEqual([entry.label for entry in picker.editor_browser.entries], ['Existing'])
                    row = next(iter(picker.editor_picker_rows.values()))
                    await picker.browser_editor_folder(row)
                    self.assertEqual([entry.label for entry in picker.editor_browser.entries], ['Nested'])
                    picker.change_editor_storage()  # Native selection can echo after navigation.
                    await asyncio.sleep(0)
                    self.assertEqual(picker.picker_folder.value, 'Office/Existing')
                    await picker.parent_editor_folder()
                    self.assertEqual(picker.editor_picker_location, (local, 'Office'))

                    await picker.browser_editor_location((locked, ''))
                    unlock.assert_called_once()
                    self.assertEqual(unlock.call_args.args, ('zip-key', 'Locked'))
                    self.assertEqual(unlock.call_args.kwargs['identity'], 'c' * 64)
                    app.clear_private_catalog(preserve_creation_picker=True)
                    self.assertEqual(picker.save_as_name.value, name)
                    client.connection = 'c' * 64
                    await unlock.call_args.kwargs['resume']()
                    self.assertEqual(picker.editor_picker_location, (unlocked, 'Projects'))
                    self.assertFalse(picker.picker_parent.enabled)
                    await picker.confirm_editor_file()
                    marker = store.target(store.jobs['Locked']) / name.encode().hex() / LIBRARY_MARKER.encode().hex()
                    self.assertEqual(marker.read_bytes(), b'cipher:')

        with (patch.object(app, 'home_unlock_candidates', return_value=[package]),
              patch.object(app, 'folder_path_visible', side_effect=lambda name, **kwargs: not str(name).startswith('legacy-')),
              patch.object(app, 'show_cloud'),
              patch.object(app, 'show_retained_unlock') as unlock,
              patch('services.documents.mobile_views.document_webview',
                    side_effect=lambda resource=None, inline_video=False, **options: toga.WebView(**options))):
            app.loop.run_until_complete(exercise())

    def test_failed_notes_marker_write_removes_only_new_empty_folder(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from features.notes_library.notes import create_library

        provider = LocalFiles(self.root)
        with patch.object(provider, 'create_file', side_effect=OSError('Storage unavailable')):
            with self.assertRaisesRegex(OSError, 'Storage unavailable'):
                create_library(provider, '', 'Journal')
        self.assertFalse((self.root / 'Journal').exists())

        (self.root / 'Journal').mkdir()
        with self.assertRaises(FileExistsError):
            create_library(provider, '', 'Journal')
        self.assertEqual(list((self.root / 'Journal').iterdir()), [])

    def test_notebook_name_preview_listing_validation_and_retry_use_notebook_format(self):
        from features.notebooks.notebook import Notebook
        local = self.root / 'LocalFiles'
        local.mkdir(exist_ok=True)
        (local / 'Existing.rmdoc').write_bytes(Notebook.new('Existing').to_bytes())
        (local / 'Text.txt').write_text('other format')
        _, picker = self.choose('Sketch', 'Remarkable Document (.rmdoc)')
        self.assertEqual(picker.effective_name.text, 'Save as: Sketch.rmdoc')
        self.assertIn('Existing.rmdoc', [row['name'] for row in picker.editor_picker_rows.values()])
        self.assertIn('Text.txt', [row['name'] for row in picker.editor_picker_rows.values()])
        picker.save_as_name.value = 'Invalid/name'
        self.app.loop.run_until_complete(picker.confirm_editor_file())
        self.assertIn('Creation failed:', picker.save_as_status.value)
        self.assertIsInstance(picker.save_as_status.label, __import__('toga').Label)
        self.assertTrue(picker.save_as_status.children)
        self.assertFalse((local / 'Invalid.txt').exists())
        picker.save_as_name.value = 'Renamed'
        self.assertEqual(picker.effective_name.text, 'Save as: Renamed.rmdoc')
        picker.new_folder_name.value = 'Test'
        self.app.loop.run_until_complete(picker.create_picker_folder())
        self.app.loop.run_until_complete(picker.confirm_editor_file())
        self.assertTrue((local / 'Test/Renamed.rmdoc').is_file(), picker.save_as_status.value)
        self.assertIsNotNone(self.app.notebook_panel)

    def test_local_document_is_in_all_files_and_saves_to_the_chosen_folder(self):
        app = self.app
        (self.root / 'LocalFiles/Notes').mkdir(parents=True)
        before = app.store.documents()
        _, picker = self.choose('First note', 'Markdown (.md)')
        self.assertNotIn('Cloud', picker.editor_storage_roots)
        self.assertEqual(set(picker.editor_storage_roots), {'Local', 'Shared Files', 'Received Files'})
        self.assertEqual(app.store.documents(), before)
        picker.picker_folder.value = 'Notes'
        app.loop.run_until_complete(picker.refresh_editor_browser())
        app.loop.run_until_complete(picker.confirm_editor_file())
        owner = app.private_sessions.active
        self.assertIsNotNone(owner)
        self.assertEqual(owner.crypt_reader.name, 'First note.md')
        self.assertEqual((self.root / 'LocalFiles/Notes/First note.md').read_bytes(), b'')
        owner.crypt_text.value = '# Saved in my folder'
        app.loop.run_until_complete(owner.save_crypt())
        self.assertEqual((self.root / 'LocalFiles/Notes/First note.md').read_text(), '# Saved in my folder')
        self.assertIn('First note.md', [row['name'] for row in device_files(self.root).list('LocalFiles/Notes')])
        self.assertEqual(app.store.documents(), before)
        self.assertNotIn('new-document', [row[0] for row in app.routes.screens['home']])
        self.assertNotIn('text-destination', [row[0] for row in app.routes.screens['home']])

    def test_cancel_and_duplicate_name_leave_existing_files_and_private_store_unchanged(self):
        app = self.app
        before = app.store.documents()
        original = self.root / 'LocalFiles/Keep.txt'
        original.parent.mkdir(exist_ok=True)
        original.write_bytes(b'keep')
        form, picker = self.choose('Keep')
        app.loop.run_until_complete(picker.confirm_editor_file())
        self.assertEqual(original.read_bytes(), b'keep')
        self.assertIn('already exists', picker.save_as_status.value)
        self.assertIsNone(app.provider_sessions().active)
        picker.cancel_text_destination()
        self.assertIsNot(app.body, form)
        self.assertEqual(app.store.documents(), before)

    def test_localcrypt_creation_and_editing_use_encrypted_provider_without_managed_plaintext(self):
        from features.rclone.localcrypt.mobile.resources import CryptFiles
        app = self.app
        app.cloud_client = client = CreationClient()
        provider = CryptFiles(self.root / 'LocalCryptFolders', client, 'Secret')
        before = app.store.documents()
        with patch.object(app, 'existing_crypt_locations', return_value={'Secret - Encrypted Copy': provider}):
            _, picker = self.choose('Private note', 'Markdown (.md)')
        picker.save_as_storage.value = 'Secret - Encrypted Copy'
        app.loop.run_until_complete(picker.refresh_editor_browser())
        app.loop.run_until_complete(picker.confirm_editor_file())
        owner = app.private_sessions.active
        self.assertIsNotNone(owner, picker.save_as_status.value)
        self.assertTrue(owner._crypt_reader_store.provider.private)
        self.assertEqual(provider._physical('Private note.md').read_bytes(), b'cipher:')
        owner.crypt_text.value = '# Secret draft'
        app.loop.run_until_complete(owner.save_crypt())
        raw = provider._physical('Private note.md').read_bytes()
        self.assertEqual(raw, b'cipher:' + b'# Secret draft'[::-1])
        self.assertNotIn(b'# Secret draft', raw)
        self.assertEqual(app.store.documents(), before)
        self.assertFalse((self.root / 'LocalFiles/Private note.md').exists())

    def test_remote_provider_cannot_be_used_for_creation(self):
        app = self.app
        _, picker = self.choose('Read only')
        provider = picker.editor_provider('Local')
        provider.remote_storage = True
        with patch.object(picker, 'editor_provider', return_value=provider):
            app.loop.run_until_complete(picker.confirm_editor_file())
        self.assertIn('read-only', picker.save_as_status.value)
        self.assertFalse((self.root / 'LocalFiles/Read only.txt').exists())

    def test_uncreated_localcrypt_roots_are_not_offered(self):
        app = self.app
        app.cloud_client = CreationClient()
        app.cloud_crypt_remotes = {'Secret'}
        _, picker = self.choose('First encrypted file')
        self.assertNotIn('Secret - Encrypted Copy', picker.editor_storage_roots)
        self.assertIn('Create a folder', picker.save_as_status.value)

    def test_session_capacity_rejects_creation_before_publishing(self):
        _, picker = self.choose('No capacity')
        with patch('mobile.workspace.MAX_SESSIONS', 0):
            self.app.loop.run_until_complete(picker.confirm_editor_file())
        self.assertIn('Close an open document', ' '.join(picker.save_as_status.value.split()))
        self.assertFalse((self.root / 'LocalFiles/No capacity.txt').exists())

    def test_notebook_creation_opens_in_shared_documents_and_recovers_ink(self):
        from features.notebooks.notebook import Notebook
        from features.notebooks.mobile.documents import open_notebook
        app = self.app
        _, picker = self.choose('Sketches', 'Remarkable Document (.rmdoc)')
        app.loop.run_until_complete(picker.confirm_editor_file())
        panel = getattr(app, 'notebook_panel', None)
        self.assertIsNotNone(panel, picker.save_as_status.value)
        self.assertEqual(panel.editor.notebook.name, 'Sketches')
        self.assertEqual(app.native_host.state.destination, 'home')
        source = self.root / 'LocalFiles/Sketches.rmdoc'
        self.assertEqual(Notebook.read(source.read_bytes()).name, 'Sketches')
        panel.editor.apply(dict(op='stroke', points=[[20,30,.4],[40,50,.8]], tool=12, width=2))
        key, session_id = panel.key, panel.session.id
        self.assertTrue(app.close_session(session_id))
        self.assertNotIn(session_id, app.workspace.sessions)
        self.assertTrue(app.loop.run_until_complete(open_notebook(app, path=source)))
        self.assertEqual(app.notebook_panel.key, key)
        self.assertEqual(len(app.notebook_panel.editor.notebook.page(0).strokes), 1)
        self.assertNotIn('new-document', [row[0] for row in app.routes.screens['home']])
        self.assertNotIn('text-destination', [row[0] for row in app.routes.screens['home']])

    def test_multiple_notebooks_keep_independent_editors_and_reopen_from_documents(self):
        from features.notebooks.mobile.documents import open_notebook
        app = self.app
        app.loop.run_until_complete(open_notebook(app, name='First'))
        first = app.notebook_panel
        app.loop.run_until_complete(open_notebook(app, name='Second'))
        second = app.notebook_panel
        self.assertIsNot(first, second)
        self.assertEqual(len(app._notebook_views), 2)
        self.assertTrue(app.loop.run_until_complete(open_notebook(app, key=first.key)))
        self.assertEqual(app.workspace.active, first.session.id)
        self.assertEqual(second.editor.notebook.name, 'Second')
