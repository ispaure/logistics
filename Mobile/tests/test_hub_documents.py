"""Hub commands and search must retain the correct draft/session owner."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from logisticsmobile.app import LogisticsMobile


class HubDocumentTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_documents()

    def tearDown(self):
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_new_from_home_displays_new_editor_and_keeps_previous_draft(self):
        app = self.app
        first = app.current.id
        app.editor.value = 'Retain my draft'
        app.show_home()
        app.new_hub_document()
        self.assertEqual(app.body.children[0].children[0].text, 'Choose a file type')
        app.body.children[0].children[1].on_press()
        self.assertNotEqual(app.current.id, first)
        self.assertEqual(app.native_host.state.destination, 'documents')
        self.assertIn(app.document_view, app.body.children)
        self.assertEqual(app.store.open(first).text, 'Retain my draft')

    def test_home_open_file_lists_all_formats_and_dispatches_archives_to_reader(self):
        from unittest.mock import AsyncMock, patch
        app = self.app
        folder = app.private_root / 'LocalFiles' / 'Library'
        folder.mkdir(parents=True, exist_ok=True)
        names = ('comic.cbz', 'comic.zip', 'book.epub', 'notes.md', 'log.txt')
        for name in names:
            (folder / name).write_bytes(b'Fixture; dispatch is mocked below')
        app.show_home()
        self.assertTrue(app.loop.run_until_complete(app.open_hub_file()))
        drawer = app.adaptive.browser('documents')
        self.assertIsNone(drawer.extensions)
        self.assertTrue(app.loop.run_until_complete(drawer.open_folder({'path': 'Library'})))
        self.assertEqual({entry.label for entry in drawer.browser.entries}, set(names))
        with patch.object(app, 'open_download', new_callable=AsyncMock) as reader:
            for name in names[:3]:
                self.assertTrue(app.loop.run_until_complete(drawer.open_file({'path': 'Library/' + name})))
                reader.assert_awaited_with(path=folder / name, destination='documents')

    def test_home_browse_refreshes_local_root_after_other_views_and_search(self):
        import asyncio
        import toga
        app = self.app
        def button(widget):
            if isinstance(widget, toga.Button) and widget.text == 'Folder Hub':
                return widget
            children = list(widget.children)
            if isinstance(widget, toga.ScrollContainer) and widget.content is not None:
                children.append(widget.content)
            return next((found for child in children if (found := button(child)) is not None), None)
        async def press_home():
            app.show_home()
            action = button(app.body)
            self.assertIsNotNone(action)
            result = action.on_press()
            if result is not None:
                await result
            self.assertEqual(app.native_host.state.destination, 'files')
            self.assertIn('All files', app.folder_picker_choices)
            app.folder_buttons['All files'].on_press()
            await app.folder_browse_button.on_press()
            self.assertIn(app.files_view, app.body.children)
            self.assertEqual(app.file_storage.value, 'Local files')
            self.assertEqual(app.file_path, '')
            self.assertEqual(app.file_browser.search.value, '')
        async def exercise():
            await press_home()
            root = app.private_root / 'LocalFiles'
            (root / 'Notes').mkdir()
            (root / 'Notes' / 'Draft.md').write_text('# Draft')
            await app.browser_file_location(('Local files', 'Notes'))
            app.file_browser.search.value = 'Missing filename'
            for view in (app.show_documents, app.show_settings, app.show_documents_hub):
                view()
                await press_home()
                self.assertIn('Notes', [entry.label for entry in app.file_browser.entries])
            (root / 'New while away.txt').write_text('Fresh item')
            app.show_settings()
            await press_home()
            self.assertIn('New while away.txt', [entry.label for entry in app.file_browser.entries])
            # A pending cloud probe/credential restore must not block local entry.
            app.set_cloud_busy(True)
            try:
                await press_home()
                self.assertTrue(app.cloud_busy)
            finally:
                app.set_cloud_busy(False)
        app.loop.run_until_complete(exercise())

    def test_continue_resumes_selected_document_and_preview(self):
        app = self.app
        app.name.value = 'Notes.md'
        app.editor.value = '# Retained'
        first = app.editor_view.session.id
        app.show_preview()
        app.show_home()
        card = app.home_continue
        app.home_continue_button.on_press()
        self.assertEqual(app.workspace.active, first)
        self.assertEqual(app.editor.value, '# Retained')
        self.assertEqual(app.editor_view.session.view['markdown_mode'], 'preview')

    def test_search_wraps_unicode_literal_replacement_and_draft_recovery(self):
        app = self.app
        app.editor.value = '😀 One one ONE'
        search = app.editor_view.search
        search.query.value = 'one'
        search.next()
        self.assertEqual(search.span, (2, 5))
        search.previous()
        self.assertEqual(search.span, (10, 13))
        search.next()
        self.assertEqual(search.span, (2, 5))
        search.replacement.value = r'\1$'
        search.replace()
        self.assertEqual(app.current.text, '😀 \\1$ one ONE')
        search.case.value = True
        search.replace_all()
        self.assertEqual(app.current.text, '😀 \\1$ \\1$ ONE')
        self.assertEqual(app.store.open(app.current.id).text, app.current.text)
        self.assertTrue(app.current.modified)

    def test_search_is_owned_by_each_document_and_does_not_change_other_drafts(self):
        app = self.app
        app.editor.value = 'first first'
        first = app.editor_view
        first.search.query.value = 'first'
        app.new_hub_document()
        app.body.children[0].children[1].on_press()
        app.editor.value = 'second'
        second = app.editor_view
        second.search.query.value = 'second'
        second.search.replacement.value = 'changed'
        second.search.replace_all()
        self.assertEqual(first.document.text, 'first first')
        self.assertEqual(first.search.query.value, 'first')
        self.assertEqual(second.document.text, 'changed')

    def test_home_prioritizes_actual_active_session_and_keeps_primary_actions(self):
        import toga
        app = self.app
        app.name.value = 'Focus.md'
        app.editor.value = '# A retained draft'
        app.show_home()
        content = app.body.children[0].content
        self.assertEqual(content.children[0].text, 'Welcome to Logistics')
        self.assertIn(app.home_continue, content.children)
        self.assertEqual(app.home_continue.children[0].children[1].text, 'Focus.md')
        actions = content.children[2]
        self.assertTrue(all(isinstance(button, toga.Button) for button in actions.children))
        self.assertEqual([button.text for button in actions.children], ['+ New document', 'Open file…'])
        app.home_continue_button.on_press()
        self.assertIs(app.body.children[0], app.document_view)
        self.assertEqual(app.editor.value, '# A retained draft')

    def test_open_document_links_have_direct_close_controls_in_both_views(self):
        import toga
        app = self.app
        session = app.editor_view.session
        for row in (app.session_panel(session, close=True), app.session_card(session, app.session_summary(session))):
            actions = next(child for child in row.children if any(isinstance(button, toga.Button) for button in child.children))
            name, close = actions.children
            self.assertEqual(name.text, app.session_summary(session)[0])
            self.assertFalse(getattr(name._impl, '_row_hint', False))
            self.assertEqual(close.text, '×')
        clean = app.store.create('Close-me.txt')
        session = app.workspace.open('managed-text', clean.id, 'text', clean.name)
        row = app.session_panel(session, close=True)
        row.children[-1].children[-1].on_press()
        self.assertNotIn(session.id, app.workspace.sessions)

    def test_documents_group_only_open_files_by_type(self):
        import toga
        app = self.app
        app.preferences.save(document_card_overview='false')
        text = app.store.create('Notes.txt')
        markdown = app.store.create('Plan.MD')
        duplicate = app.store.create('Plan.MD')
        # Interleaved sessions must become contiguous type groups.
        for doc in (markdown, text, duplicate):
            app.workspace.open('managed-text', doc.id, 'text', doc.name)
        app.refresh_documents()
        content = app.build_documents_hub().content
        labels = [child.text for child in content.children if isinstance(child, toga.Label)]
        self.assertFalse(any(label.startswith('Open documents') for label in labels))
        self.assertFalse(any(hasattr(child, 'commands') for child in content.children))
        markdown_content = app.document_categories['markdown'].children[0]
        self.assertFalse(any(child.text.startswith('Opened') for child in markdown_content.children if isinstance(child, toga.Label)))
        open_rows = [child for category in app.document_categories.values()
                     for child in category.children[0].children if hasattr(child, 'session_id')]
        names = [row.children[-1].children[0].text for row in open_rows]
        self.assertLess(names.index('Notes.txt'), names.index('Plan.MD'))
        # Clean grouped rows consist only of the filename link and close button.
        self.assertTrue(all(len(row.children) == 1 for row in open_rows))
        stored_names = [child.text for child in content.children if isinstance(child, toga.Button)]
        self.assertEqual(stored_names, [])
        self.assertFalse(any(label.startswith('Stored documents') for label in labels))

    def test_card_overview_defaults_on_reflows_and_resumes_live_draft(self):
        app = self.app
        app.name.value = 'Draft.md'
        app.editor.value = '# Current draft\nStill unsaved'
        session_id = app.editor_view.session.id
        app.show_documents_hub()
        self.assertEqual(app.preferences.values['document_card_overview'], 'true')
        grid = next(grid for grid in app.document_grids
                    if any(card.session_id == session_id for card in grid.cards))
        card = next(card for card in grid.cards if card.session_id == session_id)
        self.assertIn('Current draft', card.children[1].text)
        self.assertIn('Unsaved changes', card.children[2].text)
        for width, columns in ((390, 1), (1200, 1), (390, 1)):
            grid.reflow(width)
            self.assertEqual(grid.columns, columns)
            self.assertEqual(len(grid.children[0].children), columns)
        card.children[0].children[0].on_press()
        self.assertEqual(app.workspace.active, session_id)
        self.assertEqual(app.editor.value, '# Current draft\nStill unsaved')
        card.children[0].children[1].on_press()
        self.assertIn(session_id, app.workspace.sessions)  # Unsaved close guard.

    def test_overview_setting_persists_and_feature_settings_are_grouped(self):
        import toga
        from logisticsmobile.preferences import Preferences
        app = self.app
        app.show_settings()
        content = app.body.children[0].content
        labels = [child.text for child in content.children if isinstance(child, toga.Label)]
        sections = ['App', 'Text & Markdown', 'Books & Comics', 'LM Chat', 'Folder Hub']
        self.assertEqual([label for label in labels if label in sections], sections)
        app.document_cards_choice.value = False
        app.save_preferences()
        self.assertEqual(Preferences(app.private_root).values['document_card_overview'], 'false')
        app.show_documents_hub()
        self.assertEqual(app.document_grids, [])
        self.assertTrue(any(hasattr(child, 'session_id') for card in app.document_categories.values()
                            for child in card.children[0].children))

    def test_cards_do_not_preview_provider_text_or_open_missing_records(self):
        app = self.app
        app.editor.value = 'Private provider text'
        session = app.editor_view.session
        original = session.provider
        try:
            session.provider = 'provider-session'
            card = app.session_card(session, app.session_summary(session))
            self.assertEqual(card.children[1].text, 'Text')
        finally:
            session.provider = original
        missing = app.workspace.open('managed-text', 'd' * 32, 'text')
        card = app.session_card(missing, app.session_summary(missing))
        self.assertEqual(card.children[1].text, 'Text')
        self.assertIn('Unavailable', card.children[2].text)

    def test_overview_switch_immediately_updates_retained_root_and_keeps_editor(self):
        from logisticsmobile.preferences import Preferences
        app = self.app
        app.editor.value = 'Keep this draft'
        owner = app.editor_view
        app.show_documents_hub()
        app.session_opener(owner.session.id)()
        routes = list(app.routes.screens['documents'])
        app.show_settings()
        settings_body = app.body
        for enabled in (False, True, False):
            app.document_cards_choice.value = enabled
            self.assertEqual(bool(app.document_grids), enabled)
            self.assertEqual(Preferences(app.private_root).values['document_card_overview'],
                             'true' if enabled else 'false')
            self.assertEqual(app.routes.screens['documents'], routes)
            self.assertIs(app.body, settings_body)
            self.assertIs(app.editor_view, owner)
            self.assertEqual(owner.document.text, 'Keep this draft')
        app.select_destination('documents')
        self.assertEqual(app.document_grids, [])

    def test_overview_switch_save_failure_restores_switch_and_existing_cards(self):
        from unittest.mock import patch
        app = self.app
        app.show_documents_hub()
        grids = list(app.document_grids)
        app.show_settings()
        with patch.object(app.preferences, 'save', side_effect=OSError('Cannot save settings')):
            app.document_cards_choice.value = False
        self.assertTrue(app.document_cards_choice.value)
        self.assertEqual(app.preferences.values['document_card_overview'], 'true')
        self.assertEqual(app.document_grids, grids)
        self.assertIn('Cannot save settings', app.settings_status.text)

    def test_restored_sessions_resolve_filenames_without_opening_readers(self):
        from commonUtils.runtime.document_access import LocalDocuments
        from logisticsmobile.workspace import Workspace
        from Mobile.native_tests.tests.logisticsmobile.fixtures import make_books
        app = self.app
        fixtures = app.private_root / 'fixtures'
        fixtures.mkdir()
        book, comic = make_books(fixtures)
        store = app.reader_manager().catalog.library_store
        records = [store.import_book(LocalDocuments(), path) for path in (book, comic)]
        text = app.store.create('Restored.md')
        app.workspace.open('managed-text', text.id, 'text', 'Old name')
        for record in records:
            app.workspace.open('library', record['id'], record['kind'], record['name'])
        app.workspace.save()
        app.workspace = Workspace(app.private_root)
        app.text_views.clear()
        self.assertTrue(all(not session.title for session in app.workspace.sessions.values()))
        summaries = {session.resource: app.session_summary(session)
                     for session in app.workspace.sessions.values()}
        self.assertEqual(summaries[text.id][:2], ('Restored.md', 'markdown'))
        for record in records:
            self.assertEqual(summaries[record['id']][:2], (record['name'], record['kind']))
            self.assertEqual(summaries[record['id']][2], [])
        self.assertFalse(app.readers.controllers)
        # Names stay out of the workspace manifest.
        self.assertNotIn('Restored.md', app.workspace.path.read_text())
        store.path(records[0]['id'], '.json').unlink()
        missing = next(session for session in app.workspace.sessions.values()
                       if session.resource == records[0]['id'])
        self.assertIn('Unavailable; retry to reopen', app.session_summary(missing)[2])

    def test_grouped_rows_retain_recovery_and_unavailable_status(self):
        app = self.app
        app.name.value = 'Current name.md'
        app.editor_view.session.title = 'Stale name.txt'
        self.assertEqual(app.session_summary(app.editor_view.session)[:2], ('Current name.md', 'markdown'))
        doc = app.store.create('Recovered.md')
        doc.text = 'Unsaved draft'
        app.store.checkpoint(doc)
        session = app.workspace.open('managed-text', doc.id, 'text')
        self.assertEqual(app.session_summary(session), ('Recovered.md', 'markdown', ['Recovered draft']))
        app.store.path(doc.id, '.json').unlink()
        row = app.session_panel(session, close=True, show_kind=False)
        self.assertIn('Unavailable', row.children[0].text)
        self.assertEqual(row.children[-1].children[-1].text, '×')

    def test_restart_clears_clean_sessions_keeps_drafts_conflicts_and_stored_bytes(self):
        app = self.app
        clean = app.current.id
        app.editor.value = 'Saved writing'
        app.save_document()
        app.new_document()
        app.editor.value = 'Pending draft'
        draft = app.current.id
        app.new_document()
        conflict = app.current.id
        app.current.snapshot.path.write_bytes(b'Changed elsewhere')
        app.workspace.open('managed-text', 'f' * 32, 'text')
        app.workspace.open('library', 'e' * 32, 'epub')
        app.save_workspace()
        restored = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        try:
            resources = {session.resource for session in restored.workspace.sessions.values()}
            self.assertEqual(resources, {draft, conflict, 'f' * 32})
            self.assertEqual(restored.store.open(clean).text, 'Saved writing')
            self.assertEqual(restored.store.open(draft).text, 'Pending draft')
        finally:
            restored.main_window.close()

    def test_disabled_clear_setting_restores_saved_documents(self):
        app = self.app
        app.show_settings()
        app.clear_documents_choice.value = False
        app.save_preferences()
        key = app.current.id
        app.save_workspace()
        restored = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        try:
            self.assertEqual(restored.current.id, key)
            self.assertEqual(restored.preferences.values['clear_unmodified_documents_on_restart'], 'false')
        finally:
            restored.main_window.close()

    def test_first_chat_tab_selection_mounts_without_reentrant_navigation(self):
        from unittest.mock import patch
        app = self.app
        app.show_home()
        self.assertFalse(hasattr(app, 'chat_view'))
        with patch.object(app.native_host, 'activate', side_effect=AssertionError('Nested tab selection')):
            self.assertTrue(app.select_destination('chat'))
        self.assertIn(app.chat_view, app.routes.roots['chat'].children)
        self.assertIn(app.chat_messages, app.chat_workspace.children)
        self.assertIs(app.body, app.routes.roots['chat'])
        self.assertEqual(app.native_host.state.destination, 'home')

    def test_markdown_choice_and_independent_chat_destination(self):
        app = self.app
        app.new_hub_document()
        app.body.children[0].children[2].on_press()
        self.assertEqual(app.current.name, 'Untitled.md')
        self.assertEqual(app.editor_view.session.kind, 'markdown')
        document_routes = list(app.routes.screens['documents'])
        app.native_host.root.current_tab = 'Chat'
        app.native_host._selected(app.native_host.root)
        self.assertEqual(app.native_host.state.destination, 'chat')
        self.assertIn(app.chat_view, app.body.children)
        app.show_chat_configuration()
        self.assertEqual(app.native_host.state.destination, 'chat')
        self.assertEqual(app.routes.screens['documents'], document_routes)


if __name__ == '__main__':
    unittest.main()
