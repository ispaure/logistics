"""Library authoring, safe return and remote command rejection."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from unittest.mock import AsyncMock, Mock, patch
import unittest
import mobile_build.tests.documents.test_obsidian as fixtures
from mobile.obsidian import open_vault


class MarkdownLibraryWorkflowTests(unittest.TestCase):
    setUp = fixtures.ObsidianTests.setUp
    tearDown = fixtures.ObsidianTests.tearDown
    run_async = fixtures.ObsidianTests.run_async

    def test_formatted_preview_failure_uses_popup_and_keeps_source_mode(self):
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            self.assertTrue(await library.open_note('Vault/Home.md'))
            source = (self.vault / 'Home.md').read_text()
            with patch('services.documents.authoring.markdown_editor.FormattedMarkdownInput.load',
                       side_effect=ValueError('Private HTML limit')), \
                    patch.object(self.app.main_window, 'dialog', new=AsyncMock()) as dialog:
                self.assertTrue(await library.open_editor())
                editor = library.embedded
                self.assertEqual(editor.view.children, [editor.source])
                self.assertEqual(editor.source.value, source)
                dialog.assert_awaited_once()
                self.assertFalse(await editor.choose_mode(True))
                self.assertEqual(dialog.await_count, 2)
                self.assertEqual(editor.view.children, [editor.source])
                self.assertEqual(editor.text, source)
                self.assertEqual(library.notice.text, '')
        self.run_async(exercise())

    def test_navigation_during_source_fallback_popup_retires_pending_editor(self):
        from features.notes_library.mobile.library_document import LibraryMarkdown
        disposed = []
        original = LibraryMarkdown.dispose
        def dispose(editor):
            disposed.append(editor)
            original(editor)
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            self.assertTrue(await library.open_note('Vault/Home.md'))
            async def popup(dialog):
                self.assertTrue(await library.open_note('Vault/Projects/Plan.MD'))
            with patch('services.documents.authoring.markdown_editor.FormattedMarkdownInput.load',
                       side_effect=ValueError('Private HTML limit')), \
                    patch.object(self.app.main_window, 'dialog', new=AsyncMock(side_effect=popup)), \
                    patch.object(LibraryMarkdown, 'dispose', new=dispose):
                self.assertFalse(await library.open_editor())
            self.assertEqual(library.path, 'Vault/Projects/Plan.MD')
            self.assertIsNone(library.embedded)
            self.assertEqual(len(disposed), 1)
            self.assertTrue(disposed[0].closed)
        self.run_async(exercise())

    def test_markdown_creation_keeps_supported_filename_extensions(self):
        import toga
        from dataclasses import replace
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            show = Mock()
            with patch.object(library, 'host', replace(library.host, show_view=show)), \
                    patch.object(library, 'choose_location', new=AsyncMock()) as choose:
                for name, expected in [('Alias.markdown', 'Alias.markdown'), ('Upper.MD', 'Upper.MD'),
                                       ('Plain', 'Plain.md')]:
                    library.name_document('md', name)
                    form = show.call_args.args[0]
                    await next(child for child in form.children if isinstance(child, toga.Button)
                               and child.text == 'Choose location').on_press()
                    self.assertEqual(choose.await_args.args, (expected, 'md', 'Vault'))
        self.run_async(exercise())

    def test_typing_during_save_keeps_new_native_input_and_cancels_navigation(self):
        import asyncio
        from threading import Event
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            editor.changed('# Captured draft\n')
            entered, release = Event(), Event()
            pending_native = None
            original = editor.resource.save
            def slow(data, **kwargs):
                entered.set()
                release.wait(5)
                return original(data, **kwargs)
            async def flush():
                nonlocal pending_native
                if pending_native is not None:
                    editor.changed(pending_native)
                    pending_native = None
            with patch.object(editor.resource, 'save', side_effect=slow), \
                    patch.object(editor.formatted, 'flush', new=AsyncMock(side_effect=flush)), \
                    patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='save')):
                navigation = asyncio.create_task(library.open_note('Vault/Projects/Plan.MD'))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                    pending_native = '# Typed while saving\n'
                finally:
                    release.set()
                self.assertFalse(await navigation)
                self.assertIs(library.embedded, editor)
                self.assertEqual(library.path, 'Vault/Home.md')
                self.assertEqual((self.vault / 'Home.md').read_text(), '# Captured draft\n')
                self.assertEqual(editor.text, '# Typed while saving\n')
                self.assertTrue(editor.dirty)
                self.assertTrue(await editor.save())
                self.assertEqual((self.vault / 'Home.md').read_text(), '# Typed while saving\n')
        self.run_async(exercise())

    def test_post_save_input_failure_keeps_published_baseline_for_retry(self):
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            editor.changed('# Published\n')
            with patch.object(editor.formatted, 'flush', new=AsyncMock(side_effect=[None, ValueError('Input not ready')])):
                self.assertFalse(await editor.save())
            self.assertEqual(editor.snapshot.text, '# Published\n')
            self.assertEqual((self.vault / 'Home.md').read_text(), '# Published\n')
            self.assertEqual(library.notice.text, 'Input not ready')
            editor.changed('# Retry draft\n')
            self.assertTrue(await editor.save())
            self.assertEqual((self.vault / 'Home.md').read_text(), '# Retry draft\n')
        self.run_async(exercise())

    def test_save_refreshes_content_search_and_open_links_without_reopening_closed_panel(self):
        import asyncio
        async def exercise():
            (self.vault / 'Home.md').write_text('# Home\nneedle\n[[Missing]]')
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            await editor.choose_mode(False)
            library.search_mode.value = 'Search within Documents'
            library.search.value = 'needle'
            await library.search_task
            self.assertEqual([row['path'] for row in library.search_rows], ['Vault/Home.md'])
            await library.show_links()
            self.assertIn('Unresolved links', [getattr(row, 'text', '') for row in library.link_rows.children])
            editor.source.value = '# Changed\n[[Projects/Plan.MD]]'
            editor.changed(editor.source.value)
            self.assertTrue(await editor.save())
            await asyncio.gather(library.search_task, library.links_refresh_task)
            self.assertEqual(library.search_rows, [])
            self.assertEqual(library.sidebar.side, 'links')
            labels = [getattr(row, 'text', '') for row in library.link_rows.children]
            self.assertIn('Outgoing links (1)', labels)
            self.assertNotIn('Unresolved links', labels)
            library.refresh_library_indexes()
            pending = library.links_refresh_task
            library.sidebar.show_detail()
            await asyncio.gather(pending, return_exceptions=True)
            self.assertIsNone(library.sidebar.side)
        self.run_async(exercise())

    def test_failed_source_switch_and_snapshot_keep_tools_closed_and_draft_intact(self):
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            original = editor.text
            with patch.object(editor, 'flush', new=AsyncMock(side_effect=ValueError('Input not ready'))), \
                    patch.object(editor, 'show_tool') as show:
                await editor.show_find()
                await editor.show_properties()
                await editor.edit_yaml()
                await editor.show_contents()
                show.assert_not_called()
            self.assertFalse(hasattr(editor, 'finder'))
            self.assertIsNone(editor.source)
            self.assertEqual(editor.text, original)
            self.assertEqual(library.notice.text, 'Input not ready')
            with patch.object(editor, 'flush', new=AsyncMock(side_effect=[None, ValueError('Input not ready')])):
                self.assertFalse(await editor.replace_draft(original, 'Replacement'))
            self.assertEqual(editor.text, original)
        self.run_async(exercise())

    def test_late_find_request_cannot_override_newer_formatted_mode(self):
        import asyncio
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            entered, release = asyncio.Event(), asyncio.Event()
            count = 0
            async def flush():
                nonlocal count
                count += 1
                if count == 1:
                    entered.set()
                    await release.wait()
            with patch.object(editor, 'flush', new=AsyncMock(side_effect=flush)):
                request = asyncio.create_task(editor.show_find())
                try:
                    await entered.wait()
                    self.assertTrue(await editor.choose_mode(True))
                finally:
                    release.set()
                    await request
            self.assertEqual(editor.view.children, [editor.formatted.view])
            self.assertFalse(hasattr(editor, 'finder'))
        self.run_async(exercise())

    def test_add_property_refuses_existing_name_and_edit_keeps_original_key(self):
        async def exercise():
            path = self.vault / 'Home.md'
            path.write_text('---\ntitle: Original\ncount: 2\n---\n# Home\n')
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            original = editor.text
            with patch.object(editor, 'show_tool') as show:
                editor.property_form(original)
                rows = show.call_args.args[1]
                rows.children[0].value = 'count'
                rows.children[2].value = 'Replace by mistake'
                await rows.children[4].on_press()
                self.assertIn('already exists', rows.children[3].text)
                self.assertEqual(editor.text, original)
                editor.property_form(original, 'title', 'Original')
                rows = show.call_args.args[1]
                self.assertTrue(rows.children[0].readonly)
                rows.children[0].value = 'count'  # Even a stale/programmatic rename cannot overwrite it.
                rows.children[2].value = 'Updated'
                await rows.children[4].on_press()
            self.assertIn('title: "Updated"', editor.text)
            self.assertIn('count: 2', editor.text)
        self.run_async(exercise())

    def test_source_find_replace_handles_unicode_literal_values_and_save(self):
        async def exercise():
            path = self.vault / 'Home.md'
            path.write_text('# Home\n\n🐢 Turtle and TURTLE. Cost $5.\n')
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            await editor.show_find()
            editor.finder.query.value = 'turtle'
            editor.finder.changed()
            editor.finder.next()
            first = editor.text.index('Turtle')
            self.assertEqual(editor.finder.span, (first, first + 6))
            editor.finder.next()
            self.assertEqual(editor.finder.span, (first + 11, first + 17))
            editor.finder.replacement.value = r'$1\literal'
            editor.finder.replace_all()
            self.assertEqual(editor.text.count(r'$1\literal'), 2)
            self.assertIn('🐢', editor.text)
            self.assertTrue(editor.dirty)
            self.assertTrue(await editor.save())
            self.assertEqual(path.read_text(), editor.text)
            editor.finder.toggle()
            self.assertNotIn(editor.finder.box, editor.view.children)
        self.run_async(exercise())

    def test_contents_in_preview_and_draft_reject_stale_navigation(self):
        import json
        from features.notes_library.mobile.library_tools import show_contents
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            with patch.object(library.web, 'evaluate_javascript', new=AsyncMock(return_value=json.dumps([
                    dict(title='Home', id='home', level=1)]))), \
                    patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='0')), \
                    patch.object(library, 'scroll_fragment') as scroll:
                await show_contents(library)
                scroll.assert_called_once_with('home')
            await library.open_editor()
            editor = library.embedded
            await editor.choose_mode(False)
            editor.source.value = '---\ntitle: Example\n---\n# Home\n\n## New draft heading\n'
            editor.changed(editor.source.value)
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='1')):
                await editor.show_contents()
            self.assertEqual(editor.source._library_selection,
                             (editor.text.index('## New'), editor.text.index('## New')))
            self.assertTrue(editor.dirty)
            async def leave(*args):
                await library.open_note('Vault/Projects/Plan.MD')
                return '0'
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='discard')):
                await library.open_note('Vault/Projects/Plan.MD')
            with patch.object(library.web, 'evaluate_javascript', new=AsyncMock(return_value=json.dumps([
                    dict(title='Plan', id='plan', level=1)]))), \
                    patch.object(self.app.main_window, 'dialog', new=AsyncMock(side_effect=leave)), \
                    patch.object(library, 'scroll_fragment') as scroll:
                await show_contents(library)
                scroll.assert_not_called()
        self.run_async(exercise())

    def test_properties_and_yaml_preserve_body_and_reject_stale_draft(self):
        from commonUtils.formats.markdown import replace_property
        async def exercise():
            path = self.vault / 'Home.md'
            body = '# Home\n\nUntouched **body**.\n'
            path.write_text('---\ntitle: Original # keep comment\ncount: 2\n---\n' + body)
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            with patch.object(editor, 'show_tool') as show:
                editor.property_form(editor.text, 'title', 'Original')
                rows = show.call_args.args[1]
                rows.children[2].value = 'Changed'
                await rows.children[4].on_press()
            self.assertIn('title: "Changed" # keep comment', editor.text)
            self.assertTrue(editor.text.endswith(body))
            with patch.object(editor, 'show_tool') as show:
                await editor.edit_yaml()
                rows = show.call_args.args[1]
                rows.children[0].value = 'title: YAML\ncount: 3\n'
                await rows.children[2].on_press()
            self.assertTrue(editor.text.endswith(body))
            self.assertIn('count: 3', editor.text)
            original = editor.text
            editor.changed(original + 'New draft')
            with self.assertRaisesRegex(ValueError, 'draft changed'):
                await editor.replace_draft(original, replace_property(original, 'count', 4))
            self.assertTrue(editor.text.endswith('New draft'))
        self.run_async(exercise())

    def test_retiring_editor_erases_find_and_property_tool_contents(self):
        async def exercise():
            secret = 'Sensitive property value ' * 8
            (self.vault / 'Home.md').write_text('---\nprivate: "' + secret + '"\n---\n# Home')
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            await editor.show_find()
            editor.finder.query.value = 'Sensitive search'
            editor.finder.replacement.value = 'Sensitive replacement'
            await editor.show_properties()
            property_row = editor.tool_views[-1].children[0]
            self.assertLessEqual(len(property_row.text), 36)
            self.assertEqual(property_row.accessible_name, 'private: ' + secret)
            await editor.edit_yaml()
            yaml_source = editor.tool_views[-1].children[0]
            yaml_source.value = 'private: secret'
            library.dispose()
            self.assertEqual(editor.finder.query.value, '')
            self.assertEqual(editor.finder.replacement.value, '')
            self.assertEqual(yaml_source.value, '')
            self.assertEqual(property_row.text, '')
            self.assertEqual(property_row.accessible_name, '')
            self.assertFalse(await editor.replace_draft('old', 'new'))
        self.run_async(exercise())

    def test_late_formatted_preparation_cannot_override_newer_source_choice(self):
        import asyncio
        from threading import Event
        from features.notes_library.mobile.library_document import prepare_editor
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            await editor.choose_mode(formatted=False)
            entered, release = Event(), Event()
            def slow_prepare(*args, **kwargs):
                entered.set()
                if not release.wait(3):
                    raise RuntimeError('Test did not release preparation')
                return prepare_editor(*args, **kwargs)
            with patch('features.notes_library.mobile.library_document.prepare_editor', side_effect=slow_prepare):
                pending = asyncio.create_task(editor.choose_mode(formatted=True))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    await editor.choose_mode(formatted=False)
                finally:
                    release.set()
                    await pending
            self.assertEqual(editor.view.children, [editor.source])
            self.assertTrue(editor.dirty is False)
        self.run_async(exercise())

    def test_cancel_editor_preparation_restores_published_reader(self):
        import asyncio
        from threading import Event
        from features.notes_library.mobile.library_document import prepare_editor
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            retained = list(library.article.children)
            entered, release = Event(), Event()
            def slow(*args, **kwargs):
                entered.set()
                if not release.wait(3):
                    raise RuntimeError('Preparation not released')
                return prepare_editor(*args, **kwargs)
            with patch('features.notes_library.mobile.library_document.prepare_editor', side_effect=slow):
                task = asyncio.create_task(library.open_editor())
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    self.assertEqual(library.page_loading.status.text, 'Preparing for editing…')
                    library.page_loading.cancel()
                    self.assertEqual(list(library.article.children), retained)
                finally:
                    release.set()
                self.assertFalse(await task)
            self.assertIsNone(library.embedded)
            self.assertFalse(library.editing)
        self.run_async(exercise())

    def test_edit_stays_in_library_and_saved_read_refreshes_the_note(self):
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            sessions = set(self.app.workspace.sessions)
            self.assertTrue(await library.open_editor())
            editor = library.embedded
            self.assertEqual(library.article.children, [editor.view])
            self.assertEqual(set(self.app.workspace.sessions), sessions)
            library.sidebar.show_sidebar()
            self.assertTrue(library.sidebar.sidebar_open)
            library.sidebar.show_detail()
            editor.changed('# Saved from library\n')
            self.assertTrue(await editor.save())
            self.assertTrue(await library.open_editor())  # Toggle to reading in place.
            self.assertIsNone(library.embedded)
            self.assertEqual((self.vault / 'Home.md').read_text(), '# Saved from library\n')
            from mobile.routes import contains
            self.assertTrue(contains(self.app.body, library.view))
        self.run_async(exercise())

    def test_library_edits_preserve_utf8_bom_and_original_line_endings(self):
        async def exercise():
            path = self.vault / 'Home.md'
            path.write_bytes(b'\xef\xbb\xbf# Home\r\nOld text\r\n')
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            editor.changed(editor.text.replace('Old text', 'New text'))
            self.assertTrue(await editor.save())
            self.assertEqual(path.read_bytes(), b'\xef\xbb\xbf# Home\r\nNew text\r\n')
        self.run_async(exercise())

    def test_disposing_library_clears_retained_native_source_text(self):
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            await editor.choose_mode(formatted=False)
            source = editor.source
            self.assertEqual(source.value, (self.vault / 'Home.md').read_text())
            self.assertFalse(editor.dirty)
            library.dispose()
            self.assertEqual(source.value, '')
            self.assertEqual(list(editor.view.children), [])
            self.assertIsNone(editor.snapshot)
        self.run_async(exercise())

    def test_cancel_and_failed_save_retain_the_library_draft(self):
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            editor.changed('# Unsaved\n')
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='cancel')):
                self.assertFalse(await library.open_note('Vault/Projects/Plan.MD'))
            self.assertIs(library.embedded, editor)
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='save')), \
                 patch.object(editor.resource, 'save', side_effect=OSError('Disk full')):
                self.assertFalse(await library.open_note('Vault/Projects/Plan.MD'))
            self.assertEqual(editor.text, '# Unsaved\n')
            self.assertIn('Disk full', library.notice.text)
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='discard')):
                self.assertTrue(await library.open_note('Vault/Projects/Plan.MD'))
            self.assertTrue(editor.closed)
        self.run_async(exercise())

    def test_remarkable_document_is_contained_and_uses_embedded_canvas(self):
        from features.notes_library.notes import NotesLibrary
        from features.notebooks.notebook import Notebook
        path = NotesLibrary(self.provider, 'Vault').create('Sketch', 'Vault/Projects', extension='rmdoc')
        self.assertEqual(Notebook.read((self.root / path).read_bytes()).name, 'Sketch')
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            sessions = set(self.app.workspace.sessions)
            self.assertTrue(await library.open_note(path))
            self.assertEqual(set(self.app.workspace.sessions), sessions)
            self.assertIs(library.article.children[0], library.embedded.view)
            self.assertTrue(library.embedded.panel.state()['notes_library'])
            library.sidebar.show_links()
            self.assertTrue(library.sidebar.sidebar_open)
        self.run_async(exercise())

    def test_slow_editor_open_cannot_replace_a_newer_document(self):
        import asyncio
        from dataclasses import replace
        from types import SimpleNamespace
        from features.notes_library.mobile.library_document import LibraryMarkdown
        async def exercise():
            for canvas in (False, True):
                library = await open_vault(self.app, self.provider, 'Vault', 'files')
                await library.open_note('Vault/Home.md')
                entered, release = asyncio.Event(), asyncio.Event()
                stale = SimpleNamespace(dispose=Mock())
                async def delayed(*args):
                    entered.set()
                    await release.wait()
                    return stale
                if canvas:
                    library.host = replace(library.host, document_editor=delayed)
                with patch.object(LibraryMarkdown, 'open', new=delayed):
                    task = asyncio.create_task(library.open_note('Vault/Sketch.rmdoc') if canvas else library.open_editor())
                    await entered.wait()
                    self.assertTrue(await library.open_note('Vault/Projects/Plan.MD'))
                    release.set()
                    self.assertFalse(await task)
                self.assertEqual(library.path, 'Vault/Projects/Plan.MD')
                self.assertIsNone(library.embedded)
                stale.dispose.assert_called_once()
        self.run_async(exercise())

    def test_corrupt_notebook_and_external_markdown_changes_keep_current_document(self):
        (self.vault / 'Broken.rmdoc').write_bytes(b'not a notebook')
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            self.assertFalse(await library.open_note('Vault/Broken.rmdoc'))
            self.assertEqual(library.path, 'Vault/Home.md')
            self.assertIsNone(library.embedded)
            await library.open_editor()
            draft = library.embedded
            draft.changed('# Draft\n')
            (self.vault / 'Home.md').write_text('# External edit\n')
            self.assertFalse(await draft.save())
            self.assertTrue(draft.dirty)
            self.assertEqual((self.vault / 'Home.md').read_text(), '# External edit\n')
        self.run_async(exercise())

    def test_exit_flushes_queued_native_input_even_when_python_was_clean(self):
        from mobile.session_workflows.transitions import transitions_for
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            self.assertFalse(editor.dirty)
            async def queued_input():
                editor.changed('# Queued native input\n')
            with patch.object(editor.formatted, 'flush', new=AsyncMock(side_effect=queued_input)), \
                    patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='cancel')):
                self.assertFalse(transitions_for(self.app).checkpoint_for_exit())
                await library._close_task
            self.assertIs(library.embedded, editor)
            self.assertEqual(editor.text, '# Queued native input\n')
            self.assertFalse(self.app.close_session(library.session.id))
            with self.assertRaisesRegex(OSError, 'Notes Library'):
                transitions_for(self.app).preserve_for_replacement()
            with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='discard')):
                key = library.session.id
                library.close()
                await library._close_task
            self.assertNotIn(key, self.app.workspace.sessions)
        self.run_async(exercise())

    def test_clean_embedded_close_flushes_without_prompt_or_rewrite(self):
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            await library.open_note('Vault/Home.md')
            await library.open_editor()
            editor = library.embedded
            with patch.object(editor.formatted, 'flush', new=AsyncMock()) as flush, \
                    patch.object(self.app.main_window, 'dialog', new=AsyncMock()) as dialog, \
                    patch.object(editor.resource, 'save', side_effect=AssertionError('Unnecessary rewrite')):
                key = library.session.id
                library.close()
                await library._close_task
            flush.assert_awaited_once()
            dialog.assert_not_awaited()
            self.assertNotIn(key, self.app.workspace.sessions)
        self.run_async(exercise())

    def test_remote_library_cannot_invoke_edit_or_create_even_directly(self):
        self.provider.remote_storage = True
        async def exercise():
            library = await open_vault(self.app, self.provider, 'Vault', 'files')
            self.assertIsNone(library)
            from features.notes_library.notes import NotesLibrary
            with self.assertRaisesRegex(ValueError, 'local copy'):
                NotesLibrary(self.provider, 'Vault')
        self.run_async(exercise())

    def test_create_is_contained_and_never_overwrites_an_existing_note(self):
        from features.notes_library.notes import NotesLibrary
        model = NotesLibrary(self.provider, 'Vault')
        path = model.create('New note', 'Vault/Projects')
        self.assertEqual(path, 'Vault/Projects/New note.md')
        self.assertEqual(model.read(path), b'')
        with self.assertRaises(FileExistsError):
            model.create('New note', 'Vault/Projects')
        for name in ('../Escape', '.hidden', 'bad/name'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                model.create(name)
        # Blocked images remain absent so rendering can retain their alt text.
        self.assertIsNone(model.image_source('Vault/Home.md')('../outside.png'))
