"""Daily-note discovery, rooted file actions and abandoned opening behavior."""
from commonUtils.testing.stages import TestStage
import asyncio
from datetime import date
from itertools import count
from threading import Event
import unittest
from unittest.mock import AsyncMock, patch
import mobile_build.tests.documents.test_obsidian as fixtures
from mobile.obsidian import open_vault
from features.notes_library import library_files

TEST_STAGE = TestStage.REGRESSION


class NotesLibraryPanelTests(unittest.TestCase):
    def test_outgoing_tab_is_ready_while_backlinks_are_loading(self):
        from features.notes_library.notes_links import connections
        started, release = Event(), Event()
        def slow(*args, **kwargs):
            started.set()
            release.wait(5)
            return connections(*args, **kwargs)
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            await owner.open_note('Vault/Home.md')
            try:
                with patch('features.notes_library.notes_links.connections', side_effect=slow):
                    task = self.app.loop.create_task(owner.show_links())
                    self.assertTrue(await asyncio.to_thread(started.wait, 2), 'Backlink worker did not start')
                    self.assertEqual(owner.links_tab, 'outgoing')
                    self.assertIs(owner.links_scroll.content, owner.link_rows)
                    self.assertTrue(owner.link_rows.children[0].text.startswith('Outgoing links ('))
                    owner.select_links_tab('incoming')
                    self.assertIs(owner.links_scroll.content, owner.backlink_rows)
                    self.assertEqual(owner.backlink_rows.children[0].text, 'Finding backlinks…')
                    release.set()
                    await asyncio.wait_for(task, 3)
                    self.assertTrue(owner.backlink_rows.children[0].text.startswith('Backlinks ('))
            finally:
                release.set()
                owner.dispose()
        self.run_async(exercise())

    def test_filename_search_default_and_tabs_retain_independent_rows(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            self.assertEqual(owner.search_mode.value, 'Search in File Names')
            files, files_scroll = owner.rows, owner.rows_scroll
            original = tuple(files.children)
            with patch.object(owner.library, 'read_text', side_effect=AssertionError('Filename search read content')):
                owner.search.value = 'Plan'
                await owner.search_task
            search, search_scroll = owner.rows, owner.rows_scroll
            self.assertIsNot(search, files)
            self.assertIsNot(search_scroll, files_scroll)
            results = tuple(search.children)
            self.assertTrue(results)
            self.assertEqual(tuple(files.children), original)
            owner.select_panel_tab('Files')
            self.assertIs(owner.rows, files)
            self.assertEqual(tuple(owner.rows.children), original)
            owner.select_panel_tab('Search')
            self.assertIs(owner.rows, search)
            self.assertEqual(tuple(owner.rows.children), results)
            owner.dispose()
            self.assertFalse(files.children)
            self.assertFalse(search.children)
        self.run_async(exercise())

    def test_cooperative_search_render_does_not_expose_partial_row_replacement(self):
        (self.vault / 'First.md').write_text('First')
        (self.vault / 'Second.md').write_text('Second')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            files = tuple(owner.rows.children)
            owner.search.value = 'Plan'
            await owner.search_task
            before = tuple(owner.rows.children)
            owner.search_rows = [row for row in owner.folders[owner.root]
                                 if row['name'] in ('First.md', 'Second.md')]
            observed = [before]
            for _ in owner.tree_updates():
                observed.append(tuple(owner.rows.children))
            after = tuple(owner.rows.children)
            self.assertNotEqual(before, after)
            self.assertTrue(all(rows == before or rows == after for rows in observed))
            self.assertEqual(tuple(owner._row_panels['Files']['rows'].children), files)
            owner.dispose()
        self.run_async(exercise())

    def test_panel_container_surfaces_do_not_request_native_text_color(self):
        from dataclasses import replace
        import toga
        presentation = self.app.presentation
        containers = []
        def paint(widget, **options):
            if isinstance(widget, toga.Box):
                self.assertIsNone(options.get('foreground'))
                containers.append(widget)
            return presentation.surface(widget, **options)
        self.app._presentation = replace(presentation, surface=paint)
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'documents')
            await owner.open_note('Vault/Home.md')
            await owner.open_note('Vault/Projects/Plan.MD')
            owner.update_tree_selection()
            self.assertGreater(len(containers), 1)
            owner.dispose()
        self.run_async(exercise())

    def test_command_group_is_centered_in_the_allocated_panel_width(self):
        from travertino.layout import Viewport
        import toga
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            commands = [child for child in owner.panel_actions.children if isinstance(child, toga.Button)]
            for width in (264, 320, 600):
                owner.tree.style.layout(Viewport(width=width, height=700))
                left = commands[0].layout.absolute_content_left
                right = commands[-1].layout.absolute_content_right
                center = owner.tree.layout.absolute_content_left + owner.tree.layout.content_width / 2
                self.assertAlmostEqual((left + right) / 2, center, delta=1)
            owner.dispose()
        self.run_async(exercise())

    def test_centered_commands_collapse_without_changing_document(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Projects/Plan.MD')
            owner.sidebar.show_sidebar()
            self.assertEqual(owner.path, 'Vault/Projects/Plan.MD')
            self.assertEqual(owner.panel_tab, 'Files')
            await owner.toggle_folder('Vault/Projects')
            collapse = next(button for button in owner.panel_actions.children
                            if getattr(button, 'accessible_name', '') == 'Collapse all folders')
            collapse.on_press()
            self.assertEqual(owner.expanded, {owner.root})
            self.assertEqual(owner.path, 'Vault/Projects/Plan.MD')
            self.assertFalse(hasattr(owner, 'panel_menu'))
            self.assertFalse(hasattr(owner, 'panel_footer'))
            self.assertEqual(owner.files_content.children, [owner.panel_actions, owner.rows_scroll])
            self.assertEqual(owner.panel_actions.style.justify_content, 'center')
            self.assertEqual(sum(hasattr(child, 'on_press') for child in owner.panel_actions.children), 3)
            owner.dispose()
            collapse.on_press()
            self.assertEqual(owner.expanded, set())
        self.run_async(exercise())

    def test_menu_result_from_removed_library_visit_cannot_reopen_a_form(self):
        import toga
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.sidebar.show_sidebar()
            entered, answer = asyncio.Event(), self.app.loop.create_future()
            async def dialog(choice):
                entered.set()
                return await answer
            with patch.object(self.app.main_window, 'dialog', new=dialog):
                pending = asyncio.create_task(owner.file_actions('Vault/Home.md'))
                await entered.wait()
                replacement = toga.Label('Another Files screen')
                self.app.routes.show(replacement, destination='files', root=True)
                answer.set_result('move')
                await pending
            self.assertIsNone(owner.file_action_view)
            self.assertIs(self.app.routes.body().children[0], replacement)
        self.run_async(exercise())

    def test_late_delete_confirmation_after_navigation_or_new_menu_cannot_delete(self):
        import toga
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            for change in ('leave-library', 'new-form', 'different-document'):
                owner.present()
                entered, answer = asyncio.Event(), self.app.loop.create_future()
                async def dialog(choice):
                    entered.set()
                    return await answer
                with self.subTest(change=change), patch.object(self.app.main_window, 'dialog', new=dialog):
                    pending = asyncio.create_task(owner.delete_entry('Vault/Projects/Plan.MD'))
                    await entered.wait()
                    if change == 'leave-library':
                        self.app.routes.show(toga.Label('Another Files screen'), destination='files', root=True)
                    elif change == 'new-form':
                        owner.manage_entry(folder=True)
                    else:
                        await owner.open_note('Vault/Home.md')
                    answer.set_result(True)
                    await pending
                    self.assertTrue((self.vault / 'Projects/Plan.MD').exists())
                    self.assertFalse(owner.file_command_busy)
        self.run_async(exercise())

    def test_returning_to_library_retires_form_callbacks_in_same_destination(self):
        import toga
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.copy_entry_form('Vault/Home.md')
            form = owner.file_action_view
            next(child for child in form.children if isinstance(child, toga.TextInput)).value = 'Retired copy.md'
            owner.present()
            self.assertIsNone(owner.file_action_view)
            next(child for child in form.children if isinstance(child, toga.Button) and child.text == 'Cancel').on_press()
            await next(child for child in form.children if isinstance(child, toga.Button) and child.text == 'Copy').on_press()
            self.assertFalse((self.vault / 'Retired copy.md').exists())
            self.assertIsNone(owner.file_action_view)
        self.run_async(exercise())

    def test_file_form_back_respects_route_guard(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.manage_entry(folder=True)
            form = owner.file_action_view
            with patch.object(self.app.routes, 'guard', return_value=False):
                self.assertTrue(self.app.routes.back())
            self.assertIs(owner.file_action_view, form)
            owner.return_from_file_action()
        self.run_async(exercise())

    def test_file_action_callbacks_cannot_change_files_or_destination_after_switching_tabs(self):
        import toga
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.copy_entry_form('Vault/Home.md')
            form = owner.file_action_view
            next(child for child in form.children if isinstance(child, toga.TextInput)).value = 'Hidden copy.md'
            self.app.routes.return_to('home')
            next(child for child in form.children if isinstance(child, toga.Button) and child.text == 'Cancel').on_press()
            await next(child for child in form.children if isinstance(child, toga.Button) and child.text == 'Copy').on_press()
            self.assertEqual(self.app.native_host.state.destination, 'home')
            self.assertFalse((self.vault / 'Hidden copy.md').exists())
        self.run_async(exercise())

    def test_successful_copy_returns_to_files_and_wide_cancel_keeps_files_pinned(self):
        from dataclasses import replace
        import toga
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            owner.sidebar.show_sidebar()
            owner.copy_entry_form('Vault/Home.md')
            form = owner.file_action_view
            next(child for child in form.children if isinstance(child, toga.TextInput)).value = 'Copy.md'
            await next(child for child in form.children if isinstance(child, toga.Button) and child.text == 'Copy').on_press()
            self.assertEqual(owner.sidebar.side, 'files')
            self.assertEqual(owner.path, 'Vault/Home.md')
            self.assertTrue((self.vault / 'Copy.md').exists())
            # Reflow prefers the actual article allocation over the host's
            # fallback width. Simulate the wide allocation as well as its host.
            with patch.object(owner, 'host', replace(owner.host, content_width=lambda destination: 1100)), \
                    patch('features.notes_library.mobile.notes_library.allocated_width', return_value=1100):
                owner.reflow(1100)
                self.assertTrue(owner.sidebar.expanded)
                owner.manage_entry(folder=True)
                self.assertTrue(self.app.routes.system_back())
                self.assertTrue(owner.sidebar.expanded)
                self.assertIsNone(owner.sidebar.side)
                self.assertIn(owner.tree, owner.sidebar.view.children)
                self.assertEqual(owner.path, 'Vault/Home.md')
        self.run_async(exercise())

    def test_superseded_file_menu_cannot_replace_or_cancel_newer_form(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            for stale_result in ('move', 'cancel'):
                owner.sidebar.show_sidebar()
                answers = []
                async def dialog(choice):
                    answer = self.app.loop.create_future()
                    answers.append(answer)
                    return await answer
                with patch.object(self.app.main_window, 'dialog', new=dialog):
                    first = asyncio.create_task(owner.file_actions('Vault/Home.md'))
                    await asyncio.sleep(0)
                    second = asyncio.create_task(owner.file_actions('Vault/Projects/Plan.MD'))
                    await asyncio.sleep(0)
                    answers[1].set_result('rename')
                    await second
                    form = owner.file_action_view
                    answers[0].set_result(stale_result)
                    await first
                self.assertIs(owner.file_action_view, form)
                self.assertEqual(owner.selected_path, 'Vault/Projects/Plan.MD')
                self.assertEqual(form.content.children[2].value, 'Plan.MD')
                owner.return_from_file_action()
        self.run_async(exercise())

    def test_old_file_form_cancel_and_submit_cannot_affect_replacement(self):
        import toga
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            for action in ('move', 'copy'):
                owner.selected_path = 'Vault/Home.md'
                if action == 'move':
                    owner.manage_entry(move=True)
                else:
                    owner.copy_entry_form('Vault/Home.md')
                old_view = owner.file_action_view
                form = old_view.content if isinstance(old_view, toga.ScrollContainer) else old_view
                next(child for child in form.children if isinstance(child, toga.TextInput)).value = 'Stale.md'
                submit = next(child for child in form.children if isinstance(child, toga.Button)
                              and child.text in ('Rename', 'Copy'))
                cancel = next(child for child in form.children if isinstance(child, toga.Button)
                              and child.text == 'Cancel')
                owner.manage_entry(folder=True)
                current = owner.file_action_view
                cancel.on_press()
                await submit.on_press()
                self.assertIs(owner.file_action_view, current)
                self.assertTrue((self.vault / 'Home.md').exists())
                self.assertFalse((self.vault / 'Stale.md').exists())
                owner.return_from_file_action()
        self.run_async(exercise())

    def test_file_action_menu_cancel_keeps_the_original_drawer(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            owner.sidebar.show_sidebar()
            history = list(owner.history)
            drawer = owner.sidebar.overlay
            async def dismiss(dialog):
                self.assertIs(owner.sidebar.overlay, drawer)
                self.assertEqual(owner.sidebar.retiring, [])
                return 'cancel'
            with patch.object(self.app.main_window, 'dialog', new=dismiss):
                await owner.file_actions('Vault/Projects/Plan.MD')
            self.assertEqual(owner.sidebar.side, 'files')
            self.assertIs(owner.sidebar.overlay, drawer)
            self.assertEqual(owner.path, 'Vault/Home.md')
            self.assertEqual(owner.history, history)
        self.run_async(exercise())

    def test_file_action_form_cancel_and_android_back_restore_files_without_retracing_document(self):
        import toga
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            for loaded in (False, True):
                if loaded:
                    await owner.open_note('Vault/Home.md')
                for action in ('move', 'copy'):
                    for dismiss in ('cancel', 'system-back', 'toolbar-back'):
                        with self.subTest(loaded=loaded, action=action, dismiss=dismiss):
                            owner.sidebar.show_sidebar()
                            history = list(owner.history)
                            async def choose(dialog):
                                return action
                            with patch.object(self.app.main_window, 'dialog', new=choose):
                                await owner.file_actions('Vault/Projects/Plan.MD')
                            self.assertIsNone(owner.sidebar.side)
                            view = owner.file_action_view
                            if dismiss == 'cancel':
                                form = view.content if isinstance(view, toga.ScrollContainer) else view
                                next(child for child in form.children if isinstance(child, toga.Button)
                                     and child.text == 'Cancel').on_press()
                            elif dismiss == 'system-back':
                                self.assertTrue(self.app.routes.system_back())
                            else:
                                self.assertTrue(self.app.routes.back())
                            self.assertIsNone(owner.file_action_view)
                            self.assertEqual(owner.sidebar.side, 'files')
                            self.assertEqual(owner.history, history)
                            self.assertEqual(owner.path, 'Vault/Home.md' if loaded else None)
        self.run_async(exercise())

    def test_file_form_back_keeps_document_origin_and_waits_for_running_mutation(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            owner.sidebar.show_detail()
            owner.selected_path = owner.path
            owner.manage_entry(move=True)
            form = owner.file_action_view
            owner.file_command_busy = True
            self.assertTrue(self.app.routes.system_back())
            self.assertIs(owner.file_action_view, form)
            owner.file_command_busy = False
            self.assertTrue(self.app.routes.system_back())
            self.assertIsNone(owner.file_action_view)
            self.assertIsNone(owner.sidebar.side)
            self.assertEqual(owner.path, 'Vault/Home.md')
        self.run_async(exercise())

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
            pane_children = tuple(owner.tree.children)
            self.assertEqual(owner.panel_body.children, [owner.files_content])
            self.assertIsNone(owner.calendar_scroll.parent)
            self.assertEqual(owner.panel_tabs['Files'].style.font_weight, 'bold')
            self.assertEqual({button.style.font_size for button in owner.panel_tabs.values()},
                             {13})
            self.assertEqual(owner.panel_tabs['Files']._impl._surface_roles[:2], ('transparent', 'accent'))
            self.assertEqual(owner.panel_tabs['Calendar']._impl._surface_roles[:2], ('transparent', 'muted'))
            owner.search.value = 'Plan'
            await owner.search_task
            self.assertEqual(owner.panel_tab, 'Search')
            self.assertEqual(tuple(owner.tree.children), pane_children)
            self.assertIs(owner.search.parent, owner.search_content)
            self.assertIsNone(owner.search_mode.parent)
            self.assertIs(owner.rows_scroll.parent, owner.search_content)
            self.assertIsNone(owner.files_content.parent)
            owner.select_panel_tab('Calendar')
            self.assertEqual(tuple(owner.tree.children), pane_children)
            self.assertEqual(owner.panel_body.children, [owner.calendar_scroll])
            self.assertIsNone(owner.files_content.parent)
            self.assertEqual(owner.panel_tabs['Calendar'].style.font_weight, 'bold')
            self.assertEqual(owner.panel_tabs['Calendar']._impl._surface_roles[:2], ('transparent', 'accent'))
            self.assertEqual(owner.panel_tabs['Files']._impl._surface_roles[:2], ('transparent', 'muted'))
            await owner.calendar_task
            owner.select_panel_tab('Files')
            self.assertEqual(tuple(owner.tree.children), pane_children)
            self.assertEqual(owner.panel_body.children, [owner.files_content])
            self.assertIsNone(owner.calendar_scroll.parent)
            self.assertEqual(owner.search.value, 'Plan')
            self.assertIs(owner.rows_scroll.parent, owner.files_content)
            self.assertEqual({child.vault_path for row in owner.rows.children for child in row.children
                              if hasattr(child, 'vault_path')},
                             {'Vault/Projects', 'Vault/attachment.txt', 'Vault/Home.md'})
            self.assertIs(owner.panel_actions.parent, owner.files_content)
            owner.select_panel_tab('invalid')
            self.assertEqual(owner.panel_body.children, [owner.files_content])
        self.run_async(exercise())

    def test_calendar_pauses_search_and_search_tab_resumes_the_current_query(self):
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
                self.assertEqual(run.await_count, 1)
                self.assertIsNone(owner.search_task)
                owner.select_panel_tab('Search')
                await asyncio.sleep(0)
                self.assertEqual(run.await_count, 2)
                self.assertEqual(run.await_args.args[0], 'Plan')
                release.set()
                await owner.search_task
                await owner.calendar_task
        self.run_async(exercise())

    def test_folder_icon_and_wider_disclosure_toggle_without_opening_landing_note(self):
        (self.vault / 'Projects' / 'Projects.md').write_text('# Projects')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            row = next(row for row in owner.rows.children
                       if any(getattr(child, 'vault_path', None) == 'Vault/Projects'
                              for child in row.children))
            icon, disclosure, filename = row.children[1:4]
            self.assertEqual((disclosure.style.width, disclosure.style.height), (44, 48))
            self.assertEqual((icon.style.width, icon.style.height), (32, 48))
            with patch.object(owner, 'toggle_folder', new=AsyncMock()) as toggle, \
                    patch.object(owner, 'open_note', new=AsyncMock()) as opened:
                await icon.on_press()
                toggle.assert_awaited_once_with('Vault/Projects')
                opened.assert_not_awaited()
                toggle.reset_mock()
                await disclosure.on_press()
                toggle.assert_awaited_once_with('Vault/Projects')
                opened.assert_not_awaited()
                await filename.on_press()
                opened.assert_awaited_once_with('Vault/Projects/Projects.md')
            owner.dispose()
        self.run_async(exercise())

    def test_row_menus_reserve_a_full_target_separate_from_filename_and_disclosure(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            self.assertIs(owner.sidebar.opening_surface, owner.welcome)
            rows = list(owner.rows.children)
            for row in rows:
                button = next((child for child in row.children if hasattr(child, 'vault_path')), None)
                if button is None:
                    continue
                menu = row.children[-1]
                self.assertIsNot(menu, button)
                self.assertEqual((menu.style.width, menu.style.height), (48, 48))
                with patch.object(owner, 'file_actions', new=AsyncMock()) as actions:
                    await menu.on_press()
                    actions.assert_awaited_once_with(button.vault_path)
            self.assertTrue(rows)
        self.run_async(exercise())

    def test_filename_holds_keep_actions_separate_from_icon_drags(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import Mock
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            button = next(button for row in owner.rows.children for button in row.children
                          if getattr(button, 'vault_path', None) == 'Vault/Projects')
            with patch.object(owner.file_drag, 'bind') as bind:
                owner.bind_file_hold(button, button.vault_path, directory=True)
                bind.assert_called_once_with(button, button.vault_path, source=False, target=True)
            with patch.object(owner, 'file_actions', new=AsyncMock()) as actions:
                button.notes_file_actions()
                await asyncio.sleep(0)
                actions.assert_awaited_once_with(button.vault_path)
            native = Mock()
            impl = type('AndroidButton', (), {'__module__': 'toga_android.widgets.button'})()
            impl.native = native
            android_button = SimpleNamespace(_impl=impl)
            with patch.dict(sys.modules, {
                    'android.view': SimpleNamespace(View=SimpleNamespace(OnLongClickListener=object)),
                    'java': SimpleNamespace(dynamic_proxy=lambda interface: object)}), \
                    patch.object(owner.file_drag, 'bind') as bind, \
                    patch.object(owner, 'file_actions', new=AsyncMock()) as actions:
                owner.bind_file_hold(android_button, button.vault_path, directory=True)
                bind.assert_called_once_with(android_button, button.vault_path, source=False, target=True)
                self.assertTrue(native.setOnLongClickListener.call_args.args[0].onLongClick(native))
                await asyncio.sleep(0)
                actions.assert_awaited_once_with(button.vault_path)
                owner.release_file_hold(android_button)
            icon = button._notes_drag_icon
            with patch.object(owner.file_drag, 'unbind') as unbind:
                owner.release_file_hold(button)
                self.assertEqual([call.args[0] for call in unbind.call_args_list], [button, icon])
            owner.dispose()
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
            with patch('features.notes_library.library_files.search_resources', side_effect=scan):
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
            with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_android.widgets.box'), \
                    patch('features.notes_library.mobile.notes_library.monotonic', side_effect=count()):
                owner.render_tree()
                pending = owner.tree_task
                # Resume after the renderer reaches its first cooperative yield.
                # A wall-clock delay can let this small fixture finish first.
                await asyncio.sleep(0)
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
            with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_android.widgets.box'), \
                    patch('features.notes_library.mobile.notes_library.monotonic', side_effect=count()):
                owner.render_tree()
                first = owner.tree_task
                # Resume after the renderer reaches its first cooperative yield.
                # A wall-clock delay can let this small fixture finish first.
                await asyncio.sleep(0)
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
                if progress is None:
                    # The saved filename index can have no matches for the new query.
                    return SearchResult([], 0, True, [])
                result = SearchResult([dict(path='Vault/Projects/Plan.MD', name='Plan.MD', directory=False)], 1, False, [])
                progress(result)
                entered.set()
                if not release.wait(3):
                    raise RuntimeError('Test did not release search')
                return SearchResult(result.rows, 1, True, [])
            with patch('features.notes_library.library_files.search_resources', side_effect=scan):
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

    def test_modal_drawers_have_no_close_button_or_storage_footer(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.sidebar.show_sidebar()
            self.assertTrue(owner.sidebar.overlay.dim)
            self.assertFalse(owner.sidebar.overlay.passthrough_controls)
            self.assertFalse(hasattr(owner, 'panel_metadata'))
            self.assertFalse(hasattr(owner, 'panel_identity'))
            self.assertEqual(owner.links.children[0].text, 'Links')
            self.assertEqual(list(owner.panel_tabs), ['Files', 'Search', 'Calendar', 'Playlist'])
            self.assertTrue(owner.sidebar.overlay.edge_panel)
            owner.sidebar.reflow(296)  # A 320-unit view minus the host inset.
            self.assertEqual(owner.sidebar.policy.sidebar_width, 264)
            owner.sidebar.show_links()
            self.assertTrue(owner.sidebar.overlay.dim)
            owner.sidebar.show_detail()
            self.assertIsNone(owner.sidebar.overlay)
        self.run_async(exercise())

    def test_playlist_names_add_repair_drag_and_remove_through_library_pane(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            panel = owner.playlist_panel
            owner.select_panel_tab('Playlist')
            await panel.loading
            self.assertIn('Create a playlist', panel.notice.text)
            panel.name()
            field, commands = panel.commands.children
            field.value = 'Morning'
            await commands.children[0].on_press()
            self.assertEqual(panel.header.text, 'Morning')
            self.assertIn('Add Markdown', panel.notice.text)

            panel.begin_pick()
            self.assertEqual(owner.panel_tab, 'Files')
            self.assertIs(panel.pick_prompt.parent, owner.files_content)
            owner.select_panel_tab('Search')
            self.assertIs(panel.pick_prompt.parent, owner.search_content)
            await owner.open_selected_note('Vault/Home.md')
            self.assertIsNone(owner.path)
            self.assertEqual(owner.panel_tab, 'Playlist')
            await panel.reload()
            panel.begin_pick()
            await owner.open_selected_note('Vault/Projects/Plan.MD')
            await panel.reload()
            first, second = panel.playlist.entries

            self.assertTrue(panel.drag.start(second.id))
            self.assertTrue(panel.drag.drop(first.id))
            await asyncio.sleep(0)
            for _ in range(100):
                if panel.playlist.entries[0] == second:
                    break
                await asyncio.sleep(.01)
            self.assertEqual(panel.playlist.entries[0], second)
            panel.buttons[second.id].on_press()
            self.assertEqual(panel.selected, second.id)
            with patch.object(panel.speech, 'play') as play:
                panel.play_button.on_press()
                play.assert_called_once_with(panel.playlist.id, anchor=panel.play_button)
                play.reset_mock()
                panel.selected_play_button.on_press()
                play.assert_called_once_with(panel.playlist.id, second.id, anchor=panel.play_button)
            await panel.move_down()
            await panel.reload()
            self.assertEqual(panel.playlist.entries[1], second)

            panel.repair()
            await owner.open_selected_note('Vault/Home.md')
            await panel.reload()
            self.assertEqual(panel.playlist.entries[1].id, second.id)
            self.assertEqual(panel.playlist.entries[1].path, 'Vault/Home.md')
            await panel.remove()
            await panel.reload()
            self.assertEqual(panel.playlist.entries, (first,))
            self.assertTrue((self.vault / 'Projects/Plan.MD').exists())
            speech = panel.speech
            panel.suspend_display()
            self.assertEqual(panel.header.text, '')
            self.assertFalse(panel.rows.children)
            self.assertIs(panel.speech, speech)
            self.assertIsNone(panel.reload())
            panel.resume_display()
            await panel.loading
            self.assertEqual([row.text for row in panel.rows.children], ['Morning'])
            owner.dispose()
            self.assertFalse(panel.rows.children)
            self.assertEqual(panel.header.text, '')
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

    def test_default_copy_form_keeps_folder_and_extension_and_numbers_conflicts(self):
        import toga
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            for number in (1, 2):
                owner.copy_entry_form('Vault/Projects/Plan.MD')
                form = owner.file_action_view
                self.assertEqual(next(child for child in form.children if isinstance(child, toga.TextInput)).value,
                                 'Projects/Plan - Copy.MD')
                await next(child for child in form.children if isinstance(child, toga.Button) and child.text == 'Copy').on_press()
                name = 'Plan - Copy' + (' (2)' if number == 2 else '') + '.MD'
                self.assertEqual((self.vault / 'Projects' / name).read_bytes(),
                                 (self.vault / 'Projects/Plan.MD').read_bytes())
            self.assertEqual(library_files.copy(owner.library, 'Vault/Projects'), 'Vault/Projects - Copy')
            self.assertTrue((self.vault / 'Projects - Copy/Plan.MD').exists())
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

    def test_folder_rename_reopens_landing_note_and_direct_rename_keeps_folder(self):
        (self.vault / 'Projects/Projects.md').write_text('# Landing')

        async def rename(owner, path, target):
            owner.selected_path = path
            self.assertTrue(owner.manage_entry(move=True))
            form = self.app.body.children[0].content
            form.children[2].value = target
            await form.children[4].on_press()

        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Projects/Projects.md')
            await rename(owner, 'Vault/Projects', 'Archive')
            self.assertEqual(owner.path, 'Vault/Archive/Archive.md')
            self.assertEqual(owner.history[owner.history_index], owner.path)
            self.assertEqual((self.vault / 'Archive/Archive.md').read_text(), '# Landing')
            self.assertTrue((self.vault / 'Archive/Plan.MD').is_file())
            self.assertFalse((self.vault / 'Archive/Projects.md').exists())
            await rename(owner, owner.path, 'Landing.md')
            self.assertEqual(owner.path, 'Vault/Archive/Landing.md')
            self.assertIsNone(owner.library.folder_page('Vault/Archive'))
            self.assertTrue((self.vault / 'Archive/Landing.md').is_file())

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
            entered, retired = asyncio.Event(), asyncio.Event()
            async def stalled():
                entered.set()
                try:
                    await asyncio.Future()
                finally:
                    retired.set()
            with patch.object(owner, 'remember_position', side_effect=stalled):
                task = asyncio.create_task(owner.open_note('Vault/Home.md'))
                try:
                    await asyncio.wait_for(entered.wait(), timeout=5)
                    # Observe the hung callback's cancellation independently of
                    # subsequent file I/O and rendering on a loaded host.
                    await asyncio.wait_for(retired.wait(), timeout=5)
                    self.assertTrue(await asyncio.wait_for(task, timeout=30))
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
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

    def test_read_only_calendar_can_open_and_file_actions_only_offer_playlists(self):
        (self.vault / '2026-10-15.md').write_text('Existing')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.select_panel_tab('Calendar')
            await owner.calendar_task
            with patch.object(owner.library, 'supports', return_value=False), \
                    patch.object(self.app.main_window, 'dialog', new=AsyncMock()) as dialog:
                self.assertFalse(await owner.open_daily_note('2026-10-16'))
                dialog.assert_not_awaited()
                await owner.file_actions('Vault/Home.md')
                dialog.assert_awaited_once()
                self.assertEqual([choice[1] for choice in dialog.call_args.args[0].choices],
                                 ['playlist', 'cancel'])
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

    def test_document_and_filename_scopes_own_inputs_results_and_pagination(self):
        (self.vault / 'Body.md').write_text('Unique phrase in the body')
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            names_input = owner.search
            names_input.value = 'Plan'
            await owner.search_task
            names_rows, names_scroll = owner.rows, owner.rows_scroll
            names_result = list(owner.search_rows)
            owner.shown = 100
            owner.search_scope_buttons['Search within Documents'].on_press()
            self.assertIsNot(owner.search, names_input)
            self.assertEqual(owner.search.value, '')
            self.assertIsNot(owner.rows, names_rows)
            self.assertIsNot(owner.rows_scroll, names_scroll)
            documents_input = owner.search
            documents_input.value = 'Unique phrase'
            await owner.search_task
            self.assertEqual([row['path'] for row in owner.search_rows], ['Vault/Body.md'])
            documents_rows = owner.rows
            owner.shown = 150
            with patch.object(owner, 'run_search', side_effect=AssertionError('Completed scope was rescanned')):
                owner.search_scope_buttons['Search in File Names'].on_press()
                self.assertIs(owner.search, names_input)
                self.assertEqual(owner.search.value, 'Plan')
                self.assertIs(owner.rows, names_rows)
                self.assertIs(owner.rows_scroll, names_scroll)
                self.assertEqual(owner.search_rows, names_result)
                self.assertEqual(owner.shown, 100)
                owner.search_scope_buttons['Search within Documents'].on_press()
                self.assertIs(owner.search, documents_input)
                self.assertEqual(owner.search.value, 'Unique phrase')
                self.assertIs(owner.rows, documents_rows)
                self.assertEqual(owner.shown, 150)
            owner.dispose()
            self.assertEqual(names_input.value, '')
            self.assertEqual(documents_input.value, '')
            self.assertFalse(names_rows.children)
            self.assertFalse(documents_rows.children)
        self.run_async(exercise())

    def test_search_scope_switch_cancels_late_document_results(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.search_mode.value = 'Search within Documents'
            started, release = Event(), Event()
            original = owner.library.read_text
            def slow(*args, **kwargs):
                started.set()
                release.wait(5)
                return original(*args, **kwargs)
            try:
                with patch.object(owner.library, 'read_text', side_effect=slow):
                    owner.search.value = 'late body result'
                    for _ in range(200):
                        if started.is_set():
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(started.is_set())
                    owner.search_mode.value = 'Search in File Names'
                    owner.search.value = 'Plan'
                    await owner.search_task
                    expected = list(owner.search_rows)
                    release.set()
                    await asyncio.sleep(.1)
                    self.assertEqual(owner.search_rows, expected)
                    self.assertEqual(owner.search.value, 'Plan')
            finally:
                release.set()
                owner.dispose()
        self.run_async(exercise())

    def test_mutation_invalidates_inactive_scope_without_changing_its_query(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.search.value = 'Plan'
            await owner.search_task
            owner.search_mode.value = 'Search within Documents'
            owner.search.value = 'Plan'
            await owner.search_task
            library_files.copy(owner.library, 'Vault/Projects/Plan.MD', 'Vault/Plan copy.MD')
            owner.refresh_library_indexes()
            await owner.search_task
            owner.search_mode.value = 'Search in File Names'
            self.assertEqual(owner.search.value, 'Plan')
            await owner.search_task
            self.assertEqual({row['path'] for row in owner.search_rows},
                {'Vault/Projects/Plan.MD', 'Vault/Plan copy.MD'})
        self.run_async(exercise())
