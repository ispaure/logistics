"""Daily-note discovery, rooted file actions and abandoned opening behavior."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import asyncio
from datetime import date
from threading import Event
import unittest
from unittest.mock import AsyncMock, patch
import mobile_build.tests.documents.test_obsidian as fixtures
from mobile.obsidian import open_vault
from features.notes_library import library_files


class NotesLibraryPanelTests(unittest.TestCase):
    def test_copy_and_delete_refresh_an_active_search(self):
        import toga
        from dataclasses import replace
        from unittest.mock import Mock
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.search_mode.value = 'Search in File Names'
            owner.search.value = 'Plan'
            await owner.search_task
            show = Mock()
            with patch.object(owner, 'host', replace(owner.host, show_view=show)):
                owner.copy_entry_form('Vault/Projects/Plan.MD')
                form = show.call_args.args[0]
                next(child for child in form.children if isinstance(child, toga.TextInput)).value = 'Projects/Plan copy.MD'
                await next(child for child in form.children if isinstance(child, toga.Button) and child.text == 'Copy').on_press()
            await owner.search_task
            self.assertEqual({row['path'] for row in owner.search_rows},
                             {'Vault/Projects/Plan.MD', 'Vault/Projects/Plan copy.MD'})
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)):
                await owner.delete_entry('Vault/Projects/Plan.MD')
            self.assertNotIn('Vault/Projects/Plan.MD', [row['path'] for row in owner.search_rows])
            await owner.search_task
            self.assertEqual([row['path'] for row in owner.search_rows], ['Vault/Projects/Plan copy.MD'])
        self.run_async(exercise())

    def test_deleting_other_note_preserves_current_duplicate_history_entry(self):
        (self.vault / 'Remove.md').write_text('# Remove')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            for path in ('Vault/Home.md', 'Vault/Remove.md', 'Vault/Home.md', 'Vault/Projects/Plan.MD'):
                await owner.open_note(path)
            await owner.navigate_history(-1)
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)):
                await owner.delete_entry('Vault/Remove.md')
            self.assertEqual(owner.history, ['Vault/Home.md', 'Vault/Home.md', 'Vault/Projects/Plan.MD'])
            self.assertEqual(owner.history_index, 1)
            await owner.navigate_history(1)
            self.assertEqual(owner.path, 'Vault/Projects/Plan.MD')
        self.run_async(exercise())

    def test_selected_unopened_folders_are_creation_parents_in_tree_and_search(self):
        import toga
        from dataclasses import replace
        from unittest.mock import Mock
        (self.vault / 'Projects/Deep').mkdir()
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            self.assertNotIn('Vault/Projects', owner.folders)
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='cancel')):
                await owner.file_actions('Vault/Projects')
            self.assertEqual(owner.selected_parent(), 'Vault/Projects')
            owner.search.value = 'Deep'
            await owner.search_task
            self.assertNotIn('Vault/Projects/Deep', owner.folders)
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='cancel')):
                await owner.file_actions('Vault/Projects/Deep')
            self.assertEqual(owner.selected_parent(), 'Vault/Projects/Deep')
            show = Mock()
            with patch.object(owner, 'host', replace(owner.host, show_view=show)):
                owner.manage_entry(folder=True)
                form = show.call_args.args[0].content
                next(child for child in form.children if isinstance(child, toga.TextInput)).value = 'Child'
                await next(child for child in form.children if isinstance(child, toga.Button) and child.text == 'Create folder').on_press()
            self.assertTrue((self.vault / 'Projects/Deep/Child').is_dir())
            self.assertFalse((self.vault / 'Projects/Child').exists())
        self.run_async(exercise())

    def test_tabs_mount_only_the_selected_content_and_preserve_search(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            self.assertEqual(owner.panel_body.children, [owner.files_content])
            self.assertIsNone(owner.calendar_scroll.parent)
            self.assertEqual(owner.panel_tabs['Files'].style.font_weight, 'bold')
            self.assertEqual(owner.panel_tabs['Files']._impl._surface_roles[:2], ('surface', 'text'))
            self.assertEqual(owner.panel_tabs['Calendar']._impl._surface_roles[:2], ('alternate', 'muted'))
            owner.search.value = 'Plan'
            await owner.search_task
            owner.select_panel_tab('Calendar')
            self.assertEqual(owner.panel_body.children, [owner.calendar_scroll])
            self.assertIsNone(owner.files_content.parent)
            self.assertEqual(owner.panel_tabs['Calendar'].style.font_weight, 'bold')
            self.assertEqual(owner.panel_tabs['Calendar']._impl._surface_roles[:2], ('surface', 'text'))
            self.assertEqual(owner.panel_tabs['Files']._impl._surface_roles[:2], ('alternate', 'muted'))
            await owner.calendar_task
            owner.select_panel_tab('Files')
            self.assertEqual(owner.panel_body.children, [owner.files_content])
            self.assertIsNone(owner.calendar_scroll.parent)
            self.assertEqual(owner.search.value, 'Plan')
            owner.select_panel_tab('invalid')
            self.assertEqual(owner.panel_body.children, [owner.files_content])
        self.run_async(exercise())

    def test_calendar_pauses_search_and_files_resume_the_current_query(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            entered, release = asyncio.Event(), asyncio.Event()
            async def scan(*args):
                entered.set()
                await release.wait()
            with patch.object(owner, 'run_search', side_effect=scan) as run:
                owner.search.value = 'Home'
                pending = owner.search_task
                await entered.wait()
                owner.select_panel_tab('Calendar')
                await asyncio.wait_for(asyncio.gather(pending, return_exceptions=True), .5)
                self.assertTrue(pending.cancelled())
                self.assertIsNone(owner.search_task)
                with patch.object(owner, 'tree_updates', side_effect=AssertionError('Hidden files must not render')):
                    owner.render_tree()
                    owner.search.value = 'Plan'
                    self.assertIsNone(owner.search_task)
                owner.select_panel_tab('Files')
                await asyncio.sleep(0)
                self.assertEqual(run.await_count, 2)
                self.assertEqual(run.await_args.args[0], 'Plan')
                release.set()
                await owner.search_task
                await owner.calendar_task
        self.run_async(exercise())

    def test_cancelled_row_cleanup_does_not_reuse_a_row_with_detached_file_actions(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            folders = owner.folders
            old_cache = dict(owner._row_cache)
            owner.folders = {owner.root: []}
            updates = owner.tree_updates()
            try:
                with patch.object(owner, 'release_file_hold', wraps=owner.release_file_hold) as release:
                    for _ in updates:
                        if release.called:
                            break
                    self.assertTrue(release.called)
                    button = release.call_args.args[0]
                    key, row = next((key, row) for key, row in old_cache.items() if button in row.children)
                    self.assertNotIn(key, owner._row_cache)
            finally:
                updates.close()
                owner.folders = folders
            owner.render_tree()
            self.assertIsNot(owner._row_cache[key], row)
            button = next(child for child in owner._row_cache[key].children if hasattr(child, 'vault_path'))
            with patch.object(owner, 'file_actions', new=AsyncMock()) as actions:
                button.notes_file_actions()
                await asyncio.sleep(0)
                actions.assert_awaited_once_with(button.vault_path)
        self.run_async(exercise())

    def test_search_without_early_matches_shows_progress_before_completion(self):
        from commonUtils.search.providers import SearchResult
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            entered, release = Event(), Event()
            def scan(*args, **kwargs):
                entered.set()
                if not release.wait(3):
                    raise RuntimeError('Test did not release search')
                return SearchResult([], 1000, True, [])
            with patch('features.notes_library.mobile.notes_library.search_resources', side_effect=scan):
                owner.search.value = 'missing'
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    self.assertIs(owner._rows_message.parent, owner.rows)
                    self.assertEqual(owner._rows_message.text, 'Searching…')
                finally:
                    release.set()
                    await owner.search_task
            self.assertEqual(owner._rows_message.text, 'No matching notes or folders.')
        self.run_async(exercise())

    def test_typing_cancels_unfinished_native_result_rendering(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_android.widgets.box'):
                owner.render_tree()
                pending = owner.tree_task
                await asyncio.sleep(.002)
                self.assertFalse(pending.done())
                owner.search.value = 'Home'
                await asyncio.gather(pending, return_exceptions=True)
                self.assertTrue(pending.cancelled())
                await owner.search_task
                await owner.tree_task
                self.assertEqual(len(owner.search_rows), 1)
        self.run_async(exercise())

    def test_hidden_or_retired_calendar_callbacks_cannot_restart_work(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.select_panel_tab('Calendar')
            await owner.calendar_task
            owner.select_panel_tab('Files')
            with patch.object(owner, 'render_calendar') as render:
                previous = owner.calendar_task
                owner.refresh_calendar()
                self.assertIs(owner.calendar_task, previous)
                render.assert_not_called()
            owner.dispose()
            with patch.object(owner, 'refresh_calendar') as refresh:
                owner.select_panel_tab('Calendar')
                refresh.assert_not_called()
                self.assertEqual(owner.panel_tab, 'Files')
        self.run_async(exercise())

    def test_native_tree_batches_yield_cancel_and_reuse_rows(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_android.widgets.box'):
                owner.render_tree()
                first = owner.tree_task
                await asyncio.sleep(.002)
                self.assertFalse(first.done())
                owner.render_tree()
                await asyncio.gather(first, return_exceptions=True)
                await owner.tree_task
                rows = list(owner.rows.children)
                owner.render_tree()
                await owner.tree_task
                self.assertEqual(owner.rows.children, rows)
                self.assertEqual(set(owner._row_cache.values()), set(rows))
                owner.render_tree()
                pending = owner.tree_task
                owner.dispose()
                await asyncio.gather(pending, return_exceptions=True)
                self.assertTrue(pending.cancelled())
        self.run_async(exercise())

    def test_equal_sized_new_search_publishes_partial_results_before_scan_finishes(self):
        from commonUtils.search.providers import SearchResult
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.search.value = 'Home'
            await owner.search_task
            self.assertEqual(len(owner.search_rows), 1)
            entered, release = Event(), Event()
            published = asyncio.Event()
            original_render = owner.render_tree
            def render():
                if owner.search_rows and owner.search_rows[0]['path'] == 'Vault/Projects/Plan.MD':
                    published.set()
                original_render()
            owner.render_tree = render
            def scan(*args, progress, **kwargs):
                result = SearchResult([dict(path='Vault/Projects/Plan.MD', name='Plan.MD', directory=False)], 1, False, [])
                progress(result)
                entered.set()
                if not release.wait(3):
                    raise RuntimeError('Test did not release search')
                return SearchResult(result.rows, 1, True, [])
            with patch('features.notes_library.mobile.notes_library.search_resources', side_effect=scan):
                owner.search.value = 'Plan'
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    await asyncio.wait_for(published.wait(), 1)
                finally:
                    release.set()
                    await owner.search_task
        self.run_async(exercise())

    setUp = fixtures.ObsidianTests.setUp
    tearDown = fixtures.ObsidianTests.tearDown
    run_async = fixtures.ObsidianTests.run_async

    def test_modal_drawers_have_no_close_button_and_discreet_storage_caption(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.sidebar.show_sidebar()
            self.assertTrue(owner.sidebar.overlay.dim)
            self.assertFalse(owner.sidebar.overlay.passthrough_controls)
            self.assertEqual(owner.tree.children[1].style.font_style, 'italic')
            self.assertEqual(owner.tree.children[1].style.font_size, 10)
            self.assertEqual(owner.links.children[0].text, 'Links')
            self.assertEqual(list(owner.panel_tabs), ['Files', 'Calendar'])
            owner.sidebar.reflow(296)  # A 320-unit view minus the host inset.
            self.assertEqual(owner.sidebar.policy.sidebar_width, 264)
            owner.sidebar.show_links()
            self.assertTrue(owner.sidebar.overlay.dim)
            owner.sidebar.show_detail()
            self.assertIsNone(owner.sidebar.overlay)
        self.run_async(exercise())

    def test_calendar_indexes_nested_names_without_reading_documents(self):
        (self.vault / 'Projects/2026-10-15.md').write_text('Daily note')
        (self.vault / '2026-02-30.md').write_text('Invalid date')
        (self.vault / '.obsidian/2026-10-14.md').write_text('Hidden')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            with patch.object(owner.library, 'read', side_effect=AssertionError('Calendar read a body')):
                owner.select_panel_tab('Calendar')
                await owner.calendar_task
            self.assertEqual(owner.calendar_entries, {'2026-10-15': ['Vault/Projects/2026-10-15.md']})
            owner.calendar_month = date(2026, 10, 1)
            owner.render_calendar()
            grid = owner.calendar_content.children[1]
            buttons = [button for row in grid.children for button in row.children if hasattr(button, 'daily_date')]
            self.assertEqual(len(buttons), 31)
            self.assertEqual(next(button.text for button in buttons if button.daily_date == '2026-10-15'), '15•')
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock()) as dialog:
                self.assertTrue(await owner.open_daily_note('2026-10-15'))
                dialog.assert_not_awaited()
            self.assertEqual(owner.path, 'Vault/Projects/2026-10-15.md')
        self.run_async(exercise())

    def test_missing_day_requires_confirmation_and_creates_only_in_root(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.select_panel_tab('Calendar')
            await owner.calendar_task
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=False)):
                self.assertFalse(await owner.open_daily_note('2026-10-16'))
            self.assertFalse((self.vault / '2026-10-16.md').exists())
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)):
                self.assertTrue(await owner.open_daily_note('2026-10-16'))
            self.assertEqual(owner.path, 'Vault/2026-10-16.md')
            self.assertTrue((self.vault / '2026-10-16.md').exists())
        self.run_async(exercise())

    def test_duplicate_daily_notes_require_explicit_selection(self):
        (self.vault / '2026-10-15.md').write_text('Root')
        (self.vault / 'Projects/2026-10-15.md').write_text('Nested')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.select_panel_tab('Calendar')
            await owner.calendar_task
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='Vault/Projects/2026-10-15.md')):
                self.assertTrue(await owner.open_daily_note('2026-10-15'))
            self.assertEqual(owner.path, 'Vault/Projects/2026-10-15.md')
        self.run_async(exercise())

    def test_copy_preserves_source_and_refuses_collision_escape_and_recursion(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            library_files.copy(owner.library, 'Vault/Projects', 'Vault/Backup')
            self.assertEqual((self.vault / 'Backup/Plan.MD').read_bytes(), (self.vault / 'Projects/Plan.MD').read_bytes())
            with self.assertRaises(FileExistsError):
                library_files.copy(owner.library, 'Vault/Home.md', 'Vault/Backup/Plan.MD')
            for target in ('Elsewhere.md', 'Vault/Projects/Nested'):
                with self.assertRaises(ValueError):
                    library_files.copy(owner.library, 'Vault/Projects', target)
            self.assertFalse(list(self.vault.rglob('.notes-copy-*')))
            self.assertTrue((self.vault / 'Home.md').exists())
        self.run_async(exercise())

    def test_edit_request_cannot_take_over_a_subsequent_selection(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            entered, release = asyncio.Event(), asyncio.Event()

            async def position():
                if not entered.is_set():
                    entered.set()
                    await release.wait()

            with patch.object(owner, 'remember_position', side_effect=position):
                edit = asyncio.create_task(owner.open_editor())
                await entered.wait()
                try:
                    self.assertTrue(await owner.open_note('Vault/Projects/Plan.MD'))
                finally:
                    release.set()
                self.assertFalse(await edit)
            self.assertEqual(owner.path, 'Vault/Projects/Plan.MD')
            self.assertIsNone(owner.embedded)
        self.run_async(exercise())

    def test_moving_open_note_resolves_draft_before_renaming_it(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            await owner.open_editor()
            owner.embedded.changed('# Edited before rename')
            owner.selected_path = owner.path
            owner.manage_entry(move=True)
            form = self.app.body.children[0].content
            name, submit = form.children[2], form.children[4]
            name.value = 'Moved.md'
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='cancel')):
                await submit.on_press()
            self.assertTrue((self.vault / 'Home.md').exists())
            self.assertTrue(owner.embedded.dirty)
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='save')):
                await submit.on_press()
            self.assertEqual((self.vault / 'Moved.md').read_text(), '# Edited before rename')
            self.assertEqual(owner.path, 'Vault/Moved.md')
            self.assertIsNone(owner.embedded)
        self.run_async(exercise())

    def test_deleting_another_note_keeps_the_current_draft(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            await owner.open_editor()
            editor = owner.embedded
            editor.changed('# Keep this draft')
            confirm = AsyncMock(return_value=True)
            with patch.object(self.app.main_window, 'dialog', new=confirm):
                await owner.delete_entry('Vault/Projects/Plan.MD')
            self.assertFalse((self.vault / 'Projects/Plan.MD').exists())
            self.assertIs(owner.embedded, editor)
            self.assertTrue(editor.dirty)
            confirm.assert_awaited_once()
        self.run_async(exercise())

    def test_delete_cancel_preserves_files_and_confirm_retires_open_page(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=False)):
                await owner.delete_entry('Vault/Home.md')
            self.assertTrue((self.vault / 'Home.md').exists())
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=True)):
                await owner.delete_entry('Vault/Home.md')
            self.assertFalse((self.vault / 'Home.md').exists())
            self.assertIsNone(owner.path)
            self.assertFalse(owner.up_button.enabled)
            self.assertNotIn('Vault/Home.md', owner.history)
        self.run_async(exercise())

    def test_cancelled_slow_open_keeps_current_page_and_rejects_late_result(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            entered, release = Event(), Event()
            original = owner.library.read
            def slow(path, **kw):
                entered.set()
                release.wait(3)
                return original(path, **kw)
            with patch.object(owner.library, 'read', side_effect=slow):
                task = asyncio.create_task(owner.open_note('Vault/Projects/Plan.MD'))
                try:
                    for _ in range(100):
                        if entered.is_set():
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(owner.page_loading.active)
                    self.assertTrue(self.app.routes.system_back())
                    self.assertIn(owner.web, owner.article.children)
                    self.assertFalse(owner.page_loading.active)
                finally:
                    release.set()
                self.assertFalse(await task)
            self.assertEqual(owner.path, 'Vault/Home.md')
            self.assertEqual(owner.history, ['Vault/Home.md'])
        self.run_async(exercise())

    def test_link_progress_distinguishes_finding_from_opening(self):
        async def exercise():
            from copy import deepcopy
            from dataclasses import replace
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            samples = []
            owner.host = replace(owner.host, open_timing=lambda sample: samples.append(deepcopy(sample)))
            found, read = Event(), Event()
            original_link, original_read = owner.library.link, owner.library.read
            def lookup(*args, **kwargs):
                found.wait(3)
                return original_link(*args, **kwargs)
            def load(*args, **kwargs):
                read.wait(3)
                return original_read(*args, **kwargs)
            with patch.object(owner.library, 'link', side_effect=lookup), patch.object(owner.library, 'read', side_effect=load):
                task = asyncio.create_task(owner.open_note('Projects/Plan.MD', resolve_link=True))
                try:
                    for _ in range(100):
                        if getattr(owner, 'page_loading', None) and owner.page_loading.active:
                            break
                        await asyncio.sleep(.01)
                    self.assertEqual(owner.page_loading.status.text, 'Finding file…')
                    found.set()
                    for _ in range(100):
                        if owner.page_loading.status.text == 'Reading Plan.MD…':
                            break
                        await asyncio.sleep(.01)
                    self.assertEqual(owner.page_loading.status.text, 'Reading Plan.MD…')
                    self.assertEqual(owner.page_loading.filename.text, 'Plan.MD')
                finally:
                    found.set()
                    read.set()
                self.assertTrue(await task)
                self.assertEqual(owner.page_loading.filename.text, '')
                self.assertEqual(owner.page_loading.status.text, '')
                sample = samples[-1]
                self.assertTrue(sample['link'])
                self.assertEqual(sample['cached_folders_at_start'], 0)
                self.assertTrue({'finding', 'found', 'prepared', 'published'} <= sample['stages_ms'].keys())
                self.assertNotIn('Plan.MD', str(samples))
                self.assertNotIn('Vault', str(samples))
        self.run_async(exercise())

    def test_stalled_position_callback_cannot_hold_up_local_open(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            async def stalled():
                await asyncio.sleep(10)
            with patch.object(owner, 'remember_position', side_effect=stalled):
                self.assertTrue(await asyncio.wait_for(owner.open_note('Vault/Home.md'), timeout=1))
        self.run_async(exercise())

    def test_refresh_and_second_tap_during_create_cannot_lose_success(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.select_panel_tab('Calendar')
            await owner.calendar_task
            entered, release = asyncio.Event(), asyncio.Event()
            async def confirm(dialog):
                entered.set()
                await release.wait()
                return True
            with patch.object(self.app.main_window, 'dialog', side_effect=confirm) as dialog:
                task = asyncio.create_task(owner.open_daily_note('2026-10-17'))
                await entered.wait()
                self.assertFalse(await owner.open_daily_note('2026-10-17'))
                self.assertEqual(dialog.call_count, 1)
                release.set()
                original = owner.library.create
                def create(*args, **kw):
                    # Simulate a refresh while a background write is pending.
                    owner.host.loop.call_soon_threadsafe(setattr, owner, 'calendar_entries', None)
                    return original(*args, **kw)
                with patch.object(owner.library, 'create', side_effect=create):
                    self.assertTrue(await task)
            if owner.calendar_task:
                await owner.calendar_task
            self.assertTrue((self.vault / '2026-10-17.md').exists())
            self.assertEqual(owner.path, 'Vault/2026-10-17.md')
        self.run_async(exercise())

    def test_read_only_calendar_can_open_but_cannot_offer_creation_or_actions(self):
        (self.vault / '2026-10-15.md').write_text('Existing')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.select_panel_tab('Calendar')
            await owner.calendar_task
            with patch.object(owner.library, 'supports', return_value=False), \
                    patch.object(self.app.main_window, 'dialog', new=AsyncMock()) as dialog:
                self.assertFalse(await owner.open_daily_note('2026-10-16'))
                await owner.file_actions('Vault/Home.md')
                dialog.assert_not_awaited()
                with self.assertRaises(PermissionError):
                    library_files.copy(owner.library, 'Vault/Home.md', 'Vault/Copy.md')
                with self.assertRaises(PermissionError):
                    library_files.remove(owner.library, 'Vault/Home.md')
            self.assertFalse((self.vault / '2026-10-16.md').exists())
        self.run_async(exercise())

    def test_open_updates_selection_without_rebuilding_native_tree(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            rows = list(owner.rows.children)
            with patch.object(owner, 'render_tree', side_effect=AssertionError('Rebuilt file list')):
                self.assertTrue(await owner.open_note('Vault/Home.md'))
            self.assertEqual(owner.rows.children, rows)
        self.run_async(exercise())
