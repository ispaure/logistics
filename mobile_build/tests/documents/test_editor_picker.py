"""Owned picker state, cancellation and stale worker publication boundaries."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import toga

from commonUtils.runtime.resources.local import LocalFiles
from mobile.app import LogisticsMobile


class SyntheticPrivateFiles(LocalFiles):
    private = True


class EditorPickerTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name).resolve()
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_cloud(present=False)
        self.app.loop.run_until_complete(self.app.show_editor_open())

    def tearDown(self):
        self.app.active_host = True
        self.app.main_window.close()
        close_loop(self.app.loop)
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    async def wait_for_worker(self, started):
        for _ in range(200):
            if started.is_set():
                return
            await asyncio.sleep(.01)
        self.fail('Picker worker did not start')

    def test_owner_keeps_picker_state_off_the_app_and_preserves_provider_identity(self):
        app = self.app
        picker = app.editor_picker()
        self.assertNotIn('editor_browser', vars(app))
        self.assertNotIn('save_as_data', vars(app))
        self.assertIs(app.editor_browser, picker.editor_browser)
        provider = LocalFiles(Path(self.directory.name))
        app.editor_storage_roots = {'Associated provider': provider}
        self.assertIs(picker.editor_provider('Associated provider'), provider)
        app.save_as_data = b'unsaved'
        self.assertEqual(picker.save_as_data, b'unsaved')
        app.cancel_text_destination()
        self.assertIsNone(picker.save_as_data)
        self.assertIsNone(picker.save_as_source_document)

    def test_notebook_save_picker_exposes_and_navigates_ordinary_storage_roots(self):
        from features.notebooks.notebook import Notebook
        from services.documents.locations import collection_path
        picker = self.app.editor_picker()
        owner = SimpleNamespace(session=None, privacy_gate=None, document=None,
            editor=SimpleNamespace(notebook=Notebook.new('Destination check')))
        self.app.loop.run_until_complete(picker.show_notebook_destination(owner))
        self.assertTrue({'Local files', 'Shared files', 'Received Files'} <=
                        {row.value for row in picker.save_as_storage.items})
        received = picker.editor_provider('Received Files')
        self.assertTrue(self.app.loop.run_until_complete(
            picker.browser_editor_location(('Received Files', ''))))
        self.assertIs(picker._listed_provider, received)
        self.assertTrue(picker.picker_primary.enabled)
        self.app.loop.run_until_complete(picker.browser_editor_location(
            ('Shared files', collection_path(self.app.private_root).name)))
        self.assertEqual(picker.save_as_storage.value, 'Local files')
        self.assertEqual(picker.picker_folder.value, '')
        self.assertTrue(picker.picker_primary.enabled)
        self.assertEqual(picker.save_as_name.value, 'Destination check.rmdoc')

    def test_new_text_destination_drops_previous_operation_owners(self):
        from mobile.editor_picker import PickerOperation
        picker = self.app.editor_picker()
        previous = PickerOperation(data=b'private', source_document=object(),
            privacy_gate=object(), binary_owner=object(), destination_action=object())
        picker.operation = previous
        self.app.loop.run_until_complete(picker.show_text_destination('new.txt', b'new'))
        self.assertIsNot(picker.operation, previous)
        self.assertEqual(picker.operation.data, b'new')
        self.assertIsNone(picker.operation.binary_owner)
        self.assertIsNone(picker.operation.source_document)
        self.assertIsNone(picker.operation.privacy_gate)
        self.assertIsNone(picker.operation.destination_action)

    def test_worker_captures_draft_and_rejects_replaced_presentation(self):
        from dataclasses import replace
        picker = self.app.editor_picker()
        picker.save_as_data = b'original'
        work = picker._begin_work()
        try:
            picker.save_as_data = b'later'
            self.assertEqual(work.presentation.data, b'original')
            picker.operation = replace(picker.operation)
            self.assertFalse(picker._accepts(work))
        finally:
            picker._finish_work(work)

    def test_retired_notebook_serialization_cannot_replace_new_picker(self):
        picker = self.app.editor_picker()
        started, release = Event(), Event()
        def serialize():
            started.set()
            release.wait(5)
            return b'notebook'
        panel = SimpleNamespace(session=None, privacy_gate=None,
            editor=SimpleNamespace(notebook=SimpleNamespace(name='Old', to_bytes=serialize)))
        async def exercise():
            for replacement in ('picker', 'navigation'):
                started.clear()
                release.clear()
                task = asyncio.create_task(picker.show_notebook_destination(panel))
                try:
                    await self.wait_for_worker(started)
                    if replacement == 'picker':
                        await picker.show_editor_open()
                    else:
                        self.app.navigation_generation += 1
                    selected = picker.operation
                finally:
                    release.set()
                await task
                self.assertIs(picker.operation, selected)
                self.assertEqual(picker.operation.mode, 'open')
                self.assertIsNone(picker.operation.binary_owner)
        self.app.loop.run_until_complete(exercise())

    def test_keyboard_naming_layout_retains_focus_tree_draft_and_browsing_state(self):
        picker = self.app.editor_picker()
        panel, form, name = picker.panel, picker.picker_form, picker.save_as_name
        original = list(panel.children)
        parent = name.parent
        provider = picker._listed_provider
        picker.save_as_data = b'Keep this draft'
        name.value = 'Retained.txt'
        picker.fit_keyboard(True)
        self.assertEqual(list(panel.children), [form, picker.picker_actions])
        self.assertIs(name.parent, parent)
        self.assertIs(form.content, picker.save_as_view)
        self.assertEqual(form.style.height, 'none')
        self.assertEqual(form.style.flex, 1)
        picker.fit_keyboard(True)
        original_size = self.app.main_window.size
        self.app.main_window.size = type(original_size)(900, 180)
        picker.fit_keyboard(True)
        self.assertEqual(panel.style.direction, 'row')
        self.assertEqual(picker.picker_actions.style.direction, 'column')
        self.assertEqual(picker.picker_actions.style.width, 112)
        self.assertIs(name.parent, parent)
        self.app.main_window.size = original_size
        picker.fit_keyboard(False)
        self.assertEqual(panel.style.direction, 'column')
        self.assertEqual(picker.picker_actions.style.direction, 'row')
        self.assertEqual(picker.picker_actions.style.width, 'none')
        self.assertEqual(list(panel.children), original)
        self.assertIs(name.parent, parent)
        self.assertEqual(name.value, 'Retained.txt')
        self.assertEqual(picker.save_as_data, b'Keep this draft')
        self.assertIs(picker._listed_provider, provider)
        self.assertGreater(form.style.height, 0)

    def test_apple_location_dropdown_keeps_its_first_responder_attached(self):
        picker = self.app.editor_picker()
        native = SimpleNamespace(isFirstResponder=True)
        name = SimpleNamespace(isFirstResponder=False)
        backend = type('IOSApp', (), {'__module__': 'toga_iOS.app', 'loop': self.app.loop})()
        adapter = SimpleNamespace(keyboard_inset=236)
        with patch.object(self.app, '_impl', backend), patch.object(self.app.native_host, 'adapter', adapter), \
                patch.object(picker.save_as_storage._impl, 'native', native, create=True), \
                patch.object(picker.save_as_name._impl, 'native', name, create=True):
            picker.fit_keyboard(True)
            self.assertIs(picker.save_as_storage.parent, picker.panel)
            picker.fit_keyboard(True)
            self.assertIs(picker.save_as_storage.parent, picker.panel)
            native.isFirstResponder = False
            picker.fit_keyboard(True)
            self.assertIs(picker.save_as_storage.parent, picker.panel)
            picker.fit_keyboard(False)
            picker.fit_keyboard(True)  # Rotation may briefly report chrome with no first responder.
            self.assertIs(picker.save_as_storage.parent, picker.panel)
            name.isFirstResponder = True
            picker.fit_keyboard(True)
            self.assertIsNone(picker.save_as_storage.parent)
            picker.fit_keyboard(False)
            self.assertIs(picker.save_as_storage.parent, picker.panel)

    def test_apple_keyboard_uses_visible_height_without_moving_the_focused_input(self):
        picker = self.app.editor_picker()
        name, parent = picker.save_as_name, picker.save_as_name.parent
        name.value = 'Retained.md'
        original_size = self.app.main_window.size
        self.app.main_window.size = type(original_size)(874, 402)
        backend = type('IOSApp', (), {'__module__': 'toga_iOS.app', 'loop': self.app.loop})()
        adapter = SimpleNamespace(keyboard_inset=236)
        try:
            with patch.object(self.app, '_impl', backend), patch.object(self.app.native_host, 'adapter', adapter):
                picker.fit_keyboard(True)
                self.assertEqual(picker.panel.style.direction, 'row')
                self.assertIs(name.parent, parent)
                self.assertEqual(name.value, 'Retained.md')
                adapter.keyboard_inset = 0
                picker.fit_keyboard(False)
                self.assertEqual(picker.panel.style.direction, 'column')
                self.assertIs(name.parent, parent)
                self.assertEqual(name.value, 'Retained.md')
        finally:
            self.app.main_window.size = original_size

    def test_apple_keyboard_reveal_coalesces_and_cancels_with_picker(self):
        picker = self.app.editor_picker()
        backend = type('IOSApp', (), {'__module__': 'toga_iOS.app', 'loop': self.app.loop})()
        adapter = SimpleNamespace(keyboard_inset=236)
        with patch.object(self.app, '_impl', backend), patch.object(self.app.native_host, 'adapter', adapter), \
                patch('mobile.keyboard.reveal_picker_input') as reveal:
            picker.fit_keyboard(True)
            first = picker._keyboard_reveal
            picker.fit_keyboard(True)
            self.assertTrue(first.cancelled())
            self.app.loop.run_until_complete(asyncio.sleep(0))
            reveal.assert_called_once_with(picker)
            reveal.reset_mock()
            picker.fit_keyboard(True)
            picker.fit_keyboard(False)
            self.app.loop.run_until_complete(asyncio.sleep(0))
            reveal.assert_not_called()
            picker.fit_keyboard(True)
            picker.clear()
            self.app.loop.run_until_complete(asyncio.sleep(0))
            reveal.assert_not_called()

    def test_apple_keyboard_reveal_uses_current_first_responder_after_layout(self):
        from mobile.keyboard import reveal_picker_input
        events = []
        scroll = Mock()
        name, folder = Mock(), Mock()
        name.isFirstResponder = False
        folder.isFirstResponder = True
        folder.isDescendantOfView.return_value = True
        rect = SimpleNamespace(size=SimpleNamespace(height=48))
        folder.convertRect.side_effect = lambda *a, **k: events.append('convert') or rect
        scroll.contentInset = SimpleNamespace(bottom=0)
        window = Mock()
        window.layoutIfNeeded.side_effect = lambda: events.append('layout')
        view = Mock()
        view.refresh.side_effect = lambda: events.append('content')
        scroll.scrollRectToVisible.side_effect = lambda *a, **k: events.append('reveal')
        picker = SimpleNamespace(panel=object(), name_panel=None,
            picker_form=SimpleNamespace(content=view, _impl=SimpleNamespace(native=scroll)),
            save_as_name=SimpleNamespace(_impl=SimpleNamespace(native=name)),
            new_folder_name=SimpleNamespace(_impl=SimpleNamespace(native=folder)),
            save_as_view=view, app=SimpleNamespace(
                native_host=SimpleNamespace(adapter=SimpleNamespace(keyboard_frame=None, keyboard_visible=False)),
                main_window=SimpleNamespace(_impl=SimpleNamespace(native=window))))
        reveal_picker_input(picker)
        self.assertEqual(events, ['layout', 'content', 'convert', 'reveal'])
        folder.convertRect.assert_called_once_with(folder.bounds, toView=scroll)
        scroll.scrollRectToVisible.assert_called_once_with(rect, animated=False)
        name.convertRect.assert_not_called()
        events.clear()
        folder.isDescendantOfView.return_value = False
        reveal_picker_input(picker)
        self.assertEqual(events, [])

    def test_apple_keyboard_reveal_accounts_for_actual_occluded_scroll_bounds(self):
        from mobile.keyboard import reveal_picker_input, reset_picker_keyboard_insets
        def rect(x, y, width, height):
            return SimpleNamespace(origin=SimpleNamespace(x=x, y=y),
                                   size=SimpleNamespace(width=width, height=height))
        # Hosted Duo failure: the 48pt field ends at229, keyboard starts204,
        # but the still272pt scroll viewport tells UIKit it is already visible.
        scroll = Mock()
        scroll.contentInset = SimpleNamespace(top=0, left=0, bottom=7, right=0)
        scroll.adjustedContentInset = scroll.contentInset
        scroll.contentSize = SimpleNamespace(width=570, height=230)
        scroll.bounds = rect(0, 0, 570, 272)
        scroll.convertRect.return_value = rect(96, 153, 570, 272)
        focused = Mock(isFirstResponder=True)
        focused.isDescendantOfView.return_value = True
        scroll.contentOffset = SimpleNamespace(x=0, y=0)
        def field_rect(*args, toView):
            return (rect(96, 181 - scroll.contentOffset.y, 570, 48)
                    if toView is window else rect(0, 28, 570, 48))
        focused.convertRect.side_effect = field_rect
        keyboard = rect(0, 204, 678, 228)
        window = Mock()
        window.bounds = rect(0, 0, 678, 432)
        window.convertRect.return_value = keyboard
        adapter = SimpleNamespace(keyboard_frame=object(), keyboard_visible=True)
        form = SimpleNamespace(content=Mock(), _impl=SimpleNamespace(native=scroll))
        picker = SimpleNamespace(name_panel=None, picker_form=form,
            save_as_name=SimpleNamespace(_impl=SimpleNamespace(native=focused)),
            new_folder_name=SimpleNamespace(_impl=SimpleNamespace(native=Mock(isFirstResponder=False))),
            app=SimpleNamespace(native_host=SimpleNamespace(adapter=adapter),
                main_window=SimpleNamespace(_impl=SimpleNamespace(native=window))))
        # Test both native semantics: already accounting for the keyboard
        # inset, or treating the field as visible in the full viewport.
        for native_reveals in (False, True):
            scroll.contentOffset.y = 0
            scroll.setContentOffset.reset_mock()
            def reveal(area, animated):
                self.assertEqual(area.size.height, 48)
                if native_reveals:
                    scroll.contentOffset.y = 25
            scroll.scrollRectToVisible.side_effect = reveal
            for _ in range(2):
                reveal_picker_input(picker)
                self.assertEqual(scroll.contentInset.bottom, 228)
                self.assertEqual(form._keyboard_bottom_inset, 7)
                self.assertEqual(scroll.contentOffset.y, 25)
                self.assertEqual(181 + 48 - scroll.contentOffset.y, 204)
            self.assertEqual(scroll.setContentOffset.call_count, 0 if native_reveals else 1)
        # A settled safe-area layout already above the keyboard needs no
        # additional reservation; neither repeated reveal nor rotation adds up.
        scroll.convertRect.return_value = rect(96, 120, 570, 84)
        scroll.bounds = rect(0, 0, 570, 84)
        reveal_picker_input(picker)
        self.assertEqual(scroll.contentInset.bottom, 7)
        scroll.convertRect.return_value = rect(96, 153, 570, 272)
        scroll.bounds = rect(0, 0, 570, 272)
        reveal_picker_input(picker)
        reset_picker_keyboard_insets(picker)
        self.assertEqual(scroll.contentInset.bottom, 7)
        self.assertFalse(hasattr(form, '_keyboard_bottom_inset'))
        reset_picker_keyboard_insets(picker)
        self.assertEqual(scroll.contentInset.bottom, 7)
        # Floating keyboards do not reserve the whole form's bottom edge.
        keyboard.origin.y = 150
        keyboard.size.height = 80
        reveal_picker_input(picker)
        self.assertEqual(scroll.contentInset.bottom, 7)

    def test_late_listing_and_error_do_not_publish_after_invalidation(self):
        app, picker = self.app, self.app.editor_picker()
        for failure in (False, True):
            for invalidation in ('cancel', 'clear', 'credentials', 'host', 'navigation'):
                with self.subTest(failure=failure, invalidation=invalidation):
                    started, release = Event(), Event()
                    original = LocalFiles.list
                    def delayed(provider, *args, **kwargs):
                        started.set()
                        if not release.wait(5):
                            raise RuntimeError('Picker fixture not released')
                        if failure:
                            raise OSError('Late list failure')
                        return original(provider, *args, **dict(kwargs, cancelled=lambda: False))
                    async def exercise():
                        await app.show_editor_open()
                        before = app.save_as_status.value
                        client = app.cloud_client
                        with patch.object(type(picker.editor_provider(picker.save_as_storage.value)), 'list', new=delayed), patch.object(
                                picker.editor_browser, 'set_entries') as publish:
                            task = asyncio.create_task(app.refresh_editor_browser())
                            try:
                                await self.wait_for_worker(started)
                                # Loading is published synchronously at admission;
                                # invalidation must prevent every later update.
                                before = app.save_as_status.value
                                if invalidation == 'cancel':
                                    app.cancel_cloud()
                                    self.assertTrue(picker._work.cancel.is_set())
                                elif invalidation == 'clear':
                                    picker.clear()
                                    before = app.save_as_status.value
                                elif invalidation == 'credentials':
                                    app.cloud_client = object()
                                elif invalidation == 'host':
                                    app.active_host = False
                                else:
                                    app.navigation_generation += 1
                                release.set()
                                self.assertFalse(await task)
                                publish.assert_not_called()
                                self.assertEqual(app.save_as_status.value, before)
                                self.assertFalse(app.cloud_busy)
                            finally:
                                release.set()
                                await task
                                app.active_host = True
                                app.cloud_client = client
                    app.loop.run_until_complete(exercise())

    def test_cancelled_open_does_not_open_a_late_resolved_document(self):
        app = self.app
        root = app.private_root / 'LocalFiles'
        (root / 'note.md').write_text('Keep the previous editor')
        app.save_as_name.value = 'note.md'
        from commonUtils.runtime.resources.selection import ResourceSelection
        started, release = Event(), Event()
        original = ResourceSelection.resolve
        def delayed(model, *args, **kwargs):
            started.set()
            if not release.wait(5):
                raise RuntimeError('Picker fixture not released')
            return original(model, *args, **dict(kwargs, cancelled=lambda: False))
        async def exercise():
            with patch.object(ResourceSelection, 'resolve', new=delayed), patch.object(
                    app, 'open_crypt', new_callable=AsyncMock) as opened:
                task = asyncio.create_task(app.confirm_editor_file())
                try:
                    await self.wait_for_worker(started)
                    app.cancel_cloud()
                    release.set()
                    await task
                    opened.assert_not_awaited()
                    self.assertFalse(app.cloud_busy)
                finally:
                    release.set()
                    await task
        app.loop.run_until_complete(exercise())

    def test_cancelled_save_keeps_draft_without_publishing_or_reopening(self):
        app = self.app
        app.loop.run_until_complete(app.show_text_destination('retained.md', b'Retained draft'))
        from commonUtils.runtime.resources.mutations import save_resource_and_reopen
        started, release = Event(), Event()
        def delayed(*args, **kwargs):
            started.set()
            if not release.wait(5):
                raise RuntimeError('Save fixture not released')
            return save_resource_and_reopen(*args, **kwargs)
        async def exercise():
            with patch('services.documents.storage.save_resource_and_reopen', side_effect=delayed), patch.object(
                    app, 'open_crypt', new_callable=AsyncMock) as opened:
                task = asyncio.create_task(app.save_text_destination())
                try:
                    await self.wait_for_worker(started)
                    app.cancel_text_destination()
                    release.set()
                    await task
                    opened.assert_not_awaited()
                    self.assertEqual(app.save_as_data, b'Retained draft')
                    self.assertFalse((app.private_root / 'LocalFiles' / 'retained.md').exists())
                    self.assertFalse(app.cloud_busy)
                finally:
                    release.set()
                    await task
        app.loop.run_until_complete(exercise())

    def test_save_as_replacement_confirmation_and_revision_guard(self):
        app = self.app
        original = app.private_root / 'LocalFiles' / 'existing.md'
        for decision in ('cancel', 'replace', 'changed', 'navigation'):
            with self.subTest(decision=decision):
                original.write_bytes(b'original')
                app.loop.run_until_complete(app.show_text_destination('existing.md', b'draft'))
                async def confirm(dialog):
                    if decision == 'changed':
                        original.write_bytes(b'changed while confirming')
                    if decision == 'navigation':
                        app.navigation_generation += 1
                    return decision != 'cancel'
                with patch.object(app.main_window, 'dialog', side_effect=confirm), patch.object(
                        app, 'open_crypt', new_callable=AsyncMock, return_value=True) as opened:
                    app.loop.run_until_complete(app.save_text_destination())
                expected = b'draft' if decision == 'replace' else b'changed while confirming' if decision == 'changed' else b'original'
                self.assertEqual(original.read_bytes(), expected, app.save_as_status.value)
                if decision == 'replace':
                    opened.assert_awaited_once()
                else:
                    opened.assert_not_awaited()
                    self.assertEqual(app.save_as_data, b'draft')

    def test_file_selection_only_changes_name_and_folder_navigation_preserves_it(self):
        app, picker = self.app, self.app.editor_picker()
        root = app.private_root / 'LocalFiles'
        (root / 'Notes').mkdir()
        (root / 'existing.md').write_bytes(b'original')
        app.loop.run_until_complete(app.show_text_destination('draft.md', b'draft'))
        row = next(row for row in picker.editor_picker_rows.values() if row['name'] == 'existing.md')
        picker.browser_editor_selected(row)
        self.assertEqual(picker.save_as_name.value, 'existing.md')
        self.assertEqual((root / 'existing.md').read_bytes(), b'original')
        app.loop.run_until_complete(picker.browser_editor_folder(dict(path='Notes')))
        self.assertEqual(picker.save_as_name.value, 'existing.md')
        self.assertEqual(picker.picker_folder.value, 'Notes')
        self.assertIn('Notes', picker.picker_destination.text)

    def test_picker_system_back_ascends_before_leaving_and_search_is_local(self):
        app, picker = self.app, self.app.editor_picker()
        root = app.private_root / 'LocalFiles'
        (root / 'Notes').mkdir()
        app.loop.run_until_complete(app.show_text_destination('draft.md', b'draft'))
        app.loop.run_until_complete(picker.browser_editor_folder(dict(path='Notes')))
        picker.editor_browser.open_search()
        self.assertTrue(app.routes.system_back())
        self.assertFalse(picker.editor_browser.search_open)
        self.assertEqual(picker.picker_folder.value, 'Notes')
        self.assertTrue(app.routes.system_back())
        if app.routes.back_task is not None:
            app.loop.run_until_complete(app.routes.back_task)
        self.assertEqual(picker.picker_folder.value, '')
        self.assertEqual(picker.save_as_data, b'draft')

    def test_search_file_uses_its_containing_folder_without_saving(self):
        app, picker = self.app, self.app.editor_picker()
        root = app.private_root / 'LocalFiles'
        (root / 'Notes').mkdir()
        (root / 'Notes/existing.md').write_bytes(b'original')
        app.loop.run_until_complete(app.show_text_destination('draft.md', b'draft'))
        row = picker.editor_provider('Local files').entry('Notes/existing.md')
        picker.browser_editor_selected(row)
        app.loop.run_until_complete(picker.browser_editor_file(row))
        self.assertEqual(picker.picker_folder.value, 'Notes')
        self.assertEqual(picker.save_as_name.value, 'existing.md')
        self.assertEqual((root / 'Notes/existing.md').read_bytes(), b'original')

    def test_new_folder_preserves_filename_and_rejects_invalid_names(self):
        app, picker = self.app, self.app.editor_picker()
        app.loop.run_until_complete(app.show_text_destination('draft.md', b'draft'))
        picker.toggle_editor_new_folder()
        for invalid in ('../escape', 'nested/folder', ''):
            picker.new_folder_name.value = invalid
            app.loop.run_until_complete(picker.create_editor_folder())
            self.assertEqual(picker.picker_folder.value, '')
            self.assertTrue(picker.save_as_status.value)
        picker.new_folder_name.value = 'Notes'
        app.loop.run_until_complete(picker.create_editor_folder())
        self.assertTrue((app.private_root / 'LocalFiles/Notes').is_dir())
        self.assertEqual(picker.picker_folder.value, 'Notes')
        self.assertEqual(picker.save_as_name.value, 'draft.md')
        self.assertNotIn(picker.new_folder_form, picker.panel.children)

    def test_filename_cannot_silently_change_the_destination_folder(self):
        app, picker = self.app, self.app.editor_picker()
        app.loop.run_until_complete(app.show_text_destination('nested/draft.md', b'draft'))
        with patch.object(app.main_window, 'dialog', new_callable=AsyncMock) as dialog:
            app.loop.run_until_complete(picker.confirm_editor_file())
        dialog.assert_not_awaited()
        self.assertIn('Invalid child name', picker.save_as_status.value)
        self.assertEqual(picker.save_as_data, b'draft')

    def test_locked_source_cannot_publish_save_as(self):
        from services.session_auth import ResumePassword
        gate = ResumePassword('fixture-password')
        self.app.loop.run_until_complete(self.app.show_text_destination('locked.md', b'Private draft', privacy_gate=gate))
        self.app.screen_privacy.conceal()
        with patch.object(self.app.main_window, 'dialog', new_callable=AsyncMock) as dialog:
            self.app.loop.run_until_complete(self.app.save_text_destination())
        dialog.assert_not_awaited()
        self.assertFalse((self.app.private_root / 'LocalFiles' / 'locked.md').exists())
        self.assertEqual(self.app.save_as_data, b'Private draft')

    async def open_provider_save_as(self, *, private=True, gate=None):
        from services.documents.provider_documents import ProviderDocuments
        root = Path(self.directory.name) / ('private-source' if private else 'ordinary-source')
        root.mkdir()
        source = root / 'source.txt'
        source.write_bytes(b'original')
        provider = (SyntheticPrivateFiles if private else LocalFiles)(root)
        self.assertTrue(await self.app.open_crypt(
            copies=ProviderDocuments(provider), key=source.name, privacy_gate=gate, edit=True))
        owner = self.app.provider_sessions().active
        owner.crypt_text.value = 'edited draft'
        picker = self.app.editor_picker()
        await picker.show_crypt_save_as(owner=owner)
        self.assertIs(picker.origin.owner, owner)
        self.assertTrue(self.app.workspace.accepts(picker.origin.token))
        return picker, source

    async def choose_ordinary_save_destination(self, picker):
        self.assertTrue(await picker.browser_editor_location(('Local files', '')))
        self.assertIn('Plaintext', picker.picker_destination.text)
        return picker.editor_provider('Local files').root

    def test_private_provider_text_save_as_decline_preserves_draft(self):
        from services.session_auth import ResumePassword

        async def exercise():
            gate = ResumePassword('synthetic gate')
            picker, source = await self.open_provider_save_as(gate=gate)
            self.assertFalse(gate.locked)
            destination = await self.choose_ordinary_save_destination(picker)
            with (patch.object(toga, 'ConfirmDialog', wraps=toga.ConfirmDialog) as confirm,
                  patch.object(self.app.main_window, 'dialog', new_callable=AsyncMock, return_value=False) as dialog):
                await picker.save_text_destination()
            dialog.assert_awaited_once()
            confirm.assert_called_once_with('Save to unencrypted storage?',
                                            'The destination will contain a decrypted copy. Continue?')
            self.assertFalse((destination / source.name).exists())
            self.assertEqual(picker.operation.data, b'edited draft')
            self.assertEqual(source.read_bytes(), b'original')

        self.app.loop.run_until_complete(exercise())

    def test_private_provider_text_save_as_accepts_without_resume_gate(self):
        async def exercise():
            picker, source = await self.open_provider_save_as()
            self.assertIsNone(picker.operation.privacy_gate)
            destination = await self.choose_ordinary_save_destination(picker)
            with patch.object(self.app.main_window, 'dialog', new_callable=AsyncMock, return_value=True) as dialog:
                await picker.save_text_destination()
            dialog.assert_awaited_once()
            self.assertEqual((destination / source.name).read_bytes(), b'edited draft')
            self.assertEqual(source.read_bytes(), b'original')
            self.assertIsNone(picker.operation.data)

        self.app.loop.run_until_complete(exercise())

    def test_same_policy_provider_text_saves_without_plaintext_confirmation(self):
        from services.session_auth import ResumePassword

        async def exercise():
            for private in (True, False):
                with self.subTest(private=private):
                    gate = ResumePassword('synthetic gate')
                    picker, source = await self.open_provider_save_as(private=private, gate=gate)
                    destination = source.parent if private else await self.choose_ordinary_save_destination(picker)
                    if private:
                        self.assertEqual(picker.save_as_storage.value, 'Source location')
                    picker.save_as_name.value = 'copy.txt'
                    with patch.object(self.app.main_window, 'dialog', new_callable=AsyncMock) as dialog:
                        await picker.save_text_destination()
                    dialog.assert_not_awaited()
                    self.assertEqual((destination / 'copy.txt').read_bytes(), b'edited draft')
                    self.assertEqual(source.read_bytes(), b'original')

        self.app.loop.run_until_complete(exercise())

    def test_plaintext_confirmation_rejects_changed_destination_or_source(self):
        from services.session_auth import ResumePassword

        async def exercise():
            gate = ResumePassword('synthetic gate')
            picker, source = await self.open_provider_save_as(gate=gate)
            destination = await self.choose_ordinary_save_destination(picker)
            origin = picker.origin.token
            for change in ('folder', 'name', 'gate', 'origin'):
                with self.subTest(change=change):
                    async def confirm(dialog):
                        if change == 'folder':
                            picker.picker_folder.value = 'changed'
                        elif change == 'name':
                            picker.save_as_name.value = 'changed.txt'
                        elif change == 'gate':
                            gate.lock()
                            self.assertTrue(gate.authorize(gate.revision))
                        else:
                            self.app.workspace.invalidate(origin[0])
                        return True

                    with patch.object(self.app.main_window, 'dialog', side_effect=confirm) as dialog:
                        await picker.save_text_destination()
                    dialog.assert_awaited_once()
                    self.assertFalse((destination / source.name).exists())
                    self.assertFalse((destination / 'changed.txt').exists())
                    self.assertEqual(picker.operation.data, b'edited draft')
                    picker.picker_folder.value = ''
                    picker.save_as_name.value = source.name

        self.app.loop.run_until_complete(exercise())

    def test_private_notebook_save_as_confirms_before_publication(self):
        from features.notebooks.notebook import Notebook
        from services.documents.storage import DocumentResource

        async def exercise():
            root = Path(self.directory.name) / 'private-notebook'
            root.mkdir()
            notebook = Notebook.new('Synthetic notebook')
            name = notebook.name + '.rmdoc'
            (root / name).write_bytes(notebook.to_bytes())
            picker = self.app.editor_picker()
            session = self.app.workspace.open('provider-session', 'notebook-source', 'notebook', transient=True)
            with DocumentResource(SyntheticPrivateFiles(root), name, max_bytes=128 * 1024 * 1024) as resource:
                owner = SimpleNamespace(session=session, privacy_gate=None,
                    document=SimpleNamespace(resource=resource), editor=SimpleNamespace(notebook=notebook))
                await picker.show_notebook_destination(owner)
                target = (await self.choose_ordinary_save_destination(picker)) / name
                draft = picker.operation.data
                with (patch.object(toga, 'ConfirmDialog', wraps=toga.ConfirmDialog) as confirm,
                      patch.object(self.app.main_window, 'dialog', new_callable=AsyncMock, return_value=False) as dialog):
                    await picker.save_text_destination()
                dialog.assert_awaited_once()
                confirm.assert_called_once_with('Save to unencrypted storage?',
                                                'The destination will contain a decrypted copy. Continue?')
                self.assertFalse(target.exists())
                self.assertEqual(picker.operation.data, draft)
                with (patch.object(self.app.main_window, 'dialog', new_callable=AsyncMock, return_value=True) as dialog,
                      patch('features.notebooks.mobile.documents.retarget_notebook',
                            new_callable=AsyncMock, return_value=True) as retarget):
                    await picker.save_text_destination()
                dialog.assert_awaited_once()
                retarget.assert_awaited_once()
                self.assertEqual(target.read_bytes(), draft)
                self.assertIsNone(picker.operation.data)

        self.app.loop.run_until_complete(exercise())

    def test_save_as_cancel_restores_managed_origin_even_with_old_provider_active(self):
        from features.text_editor.resources import LocalTextCopies
        app = self.app
        saved = Path(self.directory.name) / 'earlier.txt'
        saved.write_text('Earlier saved file')
        app.loop.run_until_complete(app.open_crypt(copies=LocalTextCopies(LocalFiles(saved.parent)), key=saved.name, edit=True))
        previous = app.provider_sessions().active
        app.new_document(name='New draft.txt', content='Unfinished current draft')
        origin, owner = app.current, app.editor_view
        for close in ('cancel', 'back'):
            app.loop.run_until_complete(app.show_document_save_as())
            self.assertIs(app.editor_picker().origin.owner, owner)
            if close == 'cancel':
                app.cancel_text_destination()
            else:
                app.routes.back()
            self.assertIs(app.current, origin)
            self.assertIs(app.editor_view, owner)
            self.assertEqual(app.current.text, 'Unfinished current draft')
            self.assertIs(app.provider_sessions().active, previous)
            self.assertIsNone(app.editor_picker().origin)

    def test_closed_origin_never_reopens_an_unrelated_document(self):
        app = self.app
        app.new_document(name='Closed origin.txt', content='retained')
        key = app.editor_view.session.id
        app.loop.run_until_complete(app.show_document_save_as())
        self.assertTrue(app.close_session(key))
        with patch.object(app, 'show_documents_hub') as hub, patch.object(app, 'resume_crypt') as resume:
            app.cancel_text_destination(dismissed=True)
        hub.assert_called_once()
        resume.assert_not_called()
        self.assertNotIn(key, app.workspace.sessions)
