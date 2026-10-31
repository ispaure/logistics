"""Hub commands and search must retain the correct draft/session owner."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from mobile.app import LogisticsMobile


def widgets(root):
    yield root
    for child in root.children:
        yield from widgets(child)
    if getattr(root, 'content', None) is not None:
        yield from widgets(root.content)


def labels(root):
    import toga
    return [widget.text for widget in widgets(root) if isinstance(widget, toga.Label)]


def open_documents(content):
    import toga
    heading = next(widget for widget in widgets(content)
                   if isinstance(widget, toga.Label) and widget.text == 'All open')
    return heading.parent


class HubDocumentTests(unittest.TestCase):
    def test_document_sections_have_one_outline_and_borderless_row_actions(self):
        import toga
        from mobile import palette
        self.addCleanup(palette.set_eink_enabled, False)
        self.app.editor.value = 'Retain draft status'
        for contrast in (False, True):
            palette.set_eink_enabled(contrast)
            self.app.build_documents_hub()
            for section in (self.app.document_open_list, self.app.document_recent_list, self.app.document_saved_list):
                groups = [widget for widget in widgets(section) if getattr(widget, '_document_group', False)]
                self.assertEqual(len(groups), 1 if section is self.app.document_open_list else 0)
                if not groups:
                    continue
                self.assertTrue(groups[0]._impl._surface_eink_outlined)
                for child in widgets(groups[0]):
                    if child is not groups[0]:
                        self.assertFalse(getattr(child._impl, '_surface_eink_outlined', False))
                        if isinstance(child, toga.Box) and child.style.height != 1:
                            self.assertEqual(child._impl._surface_roles[0], 'transparent')
            home = self.app.build_home()
            # The whole Recent section can move to the trailing pane on tablets.
            recent = home.trailing
            groups = [widget for widget in widgets(recent) if getattr(widget, '_document_group', False)]
            self.assertEqual(len(groups), 1)
            self.assertIn('See all in Documents', [getattr(widget, 'text', '') for widget in widgets(groups[0])])

    def test_empty_document_messages_stay_outside_action_groups(self):
        import toga
        from unittest.mock import patch
        from mobile import palette
        self.addCleanup(palette.set_eink_enabled, False)
        app = self.app
        app.workspace.sessions.clear()
        with patch.object(app, 'recent_items', return_value=[]), \
                patch.object(app.store, 'cached_summaries', return_value=[]), \
                patch.object(app, 'show_library') as show_library:
            for contrast in (False, True):
                palette.set_eink_enabled(contrast)
                for query in ('', 'missing'):
                    app.documents_query = query
                    hub = app.build_documents_hub()
                    app.document_search.value = query
                    for section in (app.document_open_list, app.document_recent_list, app.document_saved_list):
                        self.assertFalse(any(getattr(widget, '_document_group', False) for widget in widgets(section)))
                        message = section.children[-1]
                        self.assertIsInstance(message, toga.Label)
                        self.assertEqual(message._impl._surface_roles[:2], ('transparent', 'muted'))
                        self.assertFalse(message._impl._surface_eink_outlined)
                        self.assertIn('No matching' if query else 'No ', message.text)
                    action = next(widget for widget in widgets(hub) if isinstance(widget, toga.Button)
                                  and widget.text == 'Open Books & Comics library')
                    action.on_press()
            self.assertEqual(show_library.call_count, 4)
            home = app.build_home()
            message = next(widget for widget in widgets(home.trailing) if isinstance(widget, toga.Label)
                           and widget.text == 'No recent documents.')
            self.assertIs(message.parent, home.trailing)
            groups = [widget for widget in widgets(home.trailing) if getattr(widget, '_document_group', False)]
            self.assertEqual(len(groups), 1)
            self.assertNotIn(message, list(widgets(groups[0])))
            self.assertIn('See all in Documents', [getattr(widget, 'text', '') for widget in widgets(groups[0])])

    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_documents(destination='documents')

    def tearDown(self):
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_clear_recent_button_preserves_open_and_saved_documents(self):
        import toga
        from mobile.workspace import Session
        app = self.app
        saved = app.store.create('Keep.txt', b'Saved content')
        app.recent_documents.remember(Session('closed', 'managed-text', saved.id, 'text'))
        sessions = dict(app.workspace.sessions)
        app.build_documents_hub()
        button = next(widget for widget in widgets(app.document_recent_list)
                      if isinstance(widget, toga.Button) and widget.text == 'Clear')
        self.assertEqual(button._impl._surface_roles[1], 'accent')
        app.loop.run_until_complete(button.on_press())
        self.assertEqual(app.recent_documents.sessions(), [])
        self.assertEqual(app.workspace.sessions, sessions)
        self.assertEqual(app.store.open(saved.id).text, 'Saved content')
        self.assertIn('No closed recent documents.', labels(app.document_recent_list))
        from mobile.recent_documents import RecentDocuments
        self.assertEqual(RecentDocuments(app.recent_documents.path.parent).sessions(), [])

    def test_locked_cloud_recent_renders_source_and_requests_credentials(self):
        from mobile.workspace import Session
        from unittest.mock import AsyncMock, patch
        app = self.app
        session = Session('live', 'provider-session', 'memory-only', 'markdown', title='Cloud note.md', transient=True)
        app.recent_documents.remember_file(session,
            dict(type='remote', remote='Drive', identity='a' * 64, key='Cloud note.md'))
        recent, summary = app.recent_items()[0]
        row = app.recent_row(recent, summary)
        self.assertEqual(len(row.children[0].children), 1)
        self.assertEqual([glyph for glyph, _ in row.children[0].children[0].leading_icons],
                         ['storage_remote', 'storage_crypt'])
        app.build_documents_hub()
        with patch.object(app, 'require_remote_credentials_async', new_callable=AsyncMock, return_value=False) as unlock:
            app.loop.run_until_complete(app.recent_opener(recent)())
            self.assertNotIn('identity', unlock.await_args.kwargs)

    def test_recent_hides_deleted_local_reference_but_preserves_history(self):
        from mobile.workspace import Session
        app = self.app
        path = app.private_root / 'Recent.txt'
        path.write_text('original')
        source = dict(type='local', path=str(path))
        app.recent_documents.remember_file(Session('old', 'provider-session', 'old', 'text',
                                                 title=path.name, transient=True), source)
        history = list(app.recent_documents.items)
        self.assertTrue(any(session.provider == 'file-reference' for session, _ in app.recent_items()))
        path.unlink()
        self.assertFalse(any(session.provider == 'file-reference' for session, _ in app.recent_items()))
        # Missing removable storage must not erase history or create an empty file.
        self.assertEqual(app.recent_documents.items, history)
        self.assertFalse(path.exists())
        path.write_text('returned')
        self.assertTrue(any(session.provider == 'file-reference' for session, _ in app.recent_items()))

    def test_recent_deletion_after_render_explains_missing_file(self):
        from mobile.workspace import Session
        from unittest.mock import AsyncMock, patch
        app = self.app
        path = app.private_root / 'Gone.txt'
        path.write_text('original')
        app.recent_documents.remember_file(Session('old', 'provider-session', 'old', 'text',
                                                 title=path.name, transient=True),
                                           dict(type='local', path=str(path)))
        recent = next(session for session, _ in app.recent_items() if session.provider == 'file-reference')
        opener = app.recent_opener(recent)
        path.unlink()
        import toga
        with (patch.object(app.main_window, 'dialog', new_callable=AsyncMock),
              patch('mobile.hub_ui.toga.InfoDialog', wraps=toga.InfoDialog) as info):
            app.loop.run_until_complete(opener())
        self.assertIn('moved or deleted', info.call_args.args[1])
        self.assertFalse(path.exists())
        self.assertFalse(any(session.provider == 'file-reference' for session, _ in app.recent_items()))

    def test_recent_library_copy_survives_original_deletion_with_icon_only(self):
        from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
        from commonUtils.runtime.resources.documents import LocalDocuments
        from mobile.workspace import Session
        app = self.app
        fixtures = app.private_root / 'fixtures'
        fixtures.mkdir()
        book, _ = make_books(fixtures)
        store = app.reader_manager().catalog.library_store
        record = store.import_book(LocalDocuments(), book)
        session = Session('', 'library', record['id'], record['kind'])
        app.recent_documents.remember(session)
        book.unlink()
        recent, summary = next(item for item in app.recent_items() if item[0].resource == record['id'])
        row = app.recent_row(recent, summary)
        self.assertNotIn('Saved copy on device', labels(row))
        self.assertIn('storage_local', [glyph for glyph, _ in row.document_button.leading_icons])
        self.assertEqual(store.read_record(record['id'])[0]['name'], record['name'])

    def test_recent_cloud_open_shows_activity_until_finished_and_cleans_up_on_failure(self):
        import asyncio
        import toga
        from unittest.mock import AsyncMock, patch
        from mobile.workspace import Session
        app = self.app
        session = Session('live', 'provider-session', 'memory-only', 'markdown', title='Cloud note.md', transient=True)
        app.recent_documents.remember_file(session,
            dict(type='remote', remote='Drive', identity='a' * 64, key='Cloud note.md'))
        recent, _ = app.recent_items()[0]

        async def check():
            for destination in ('home', 'documents'):
                for outcome in ('success', 'failure', 'cancel'):
                    if destination == 'home':
                        app.show_home()
                    else:
                        app.show_documents_hub()
                    original = app.body
                    started, finish = asyncio.Event(), asyncio.Event()
                    async def delayed_open(*args):
                        started.set()
                        await finish.wait()
                        if outcome == 'failure':
                            raise OSError('Offline')
                        return True
                    with (patch('mobile.document_sources._reopen_file', side_effect=delayed_open),
                          patch.object(app.main_window, 'dialog', new_callable=AsyncMock)):
                        task = asyncio.create_task(app.recent_opener(recent)())
                        await started.wait()
                        self.assertIsNot(app.body, original)
                        self.assertTrue(app.routes.screens[destination][-1][0].startswith('file-loading:'))
                        panel = app.body.children[0]
                        self.assertEqual(labels(panel), ['Cloud note.md', 'Preparing document…'])
                        progress = next(child for child in widgets(panel) if isinstance(child, toga.ProgressBar))
                        self.assertTrue(progress.is_running)
                        # Completion returns to the retained origin unless the
                        # user has already navigated to a replacement screen.
                        if outcome == 'failure':
                            app.show_documents_hub()
                        replacement = app.body if outcome == 'failure' else original
                        if outcome == 'cancel':
                            task.cancel()
                            with self.assertRaises(asyncio.CancelledError):
                                await task
                        else:
                            finish.set()
                            await task
                        self.assertFalse(progress.is_running)
                        self.assertIsNone(app._file_loading)
                        self.assertFalse(any(route.startswith('file-loading:')
                                             for route, *_ in app.routes.screens[destination]))
                        self.assertIs(app.body, replacement)
        app.loop.run_until_complete(check())

    def test_new_from_home_displays_new_editor_and_keeps_previous_draft(self):
        app = self.app
        first = app.current.id
        app.editor.value = 'Retain my draft'
        app.show_home()
        app.loop.run_until_complete(app.new_hub_document())
        form = app.editor_picker()
        form.save_as_name.value = 'My notes'
        app.loop.run_until_complete(form.browser_editor_location(('Local', '')))
        app.loop.run_until_complete(app.editor_picker().confirm_editor_file())
        owner = app.private_sessions.active
        self.assertEqual(owner.crypt_reader.name, 'My notes.txt')
        self.assertEqual(app.current.id, first)
        self.assertEqual(app.native_host.state.destination, 'home')
        self.assertIn(owner.crypt_view, app.body.children)
        self.assertEqual(app.store.open(first).text, 'Retain my draft')

    def test_hubs_split_whole_sections_and_restore_compact_order(self):
        from unittest.mock import patch
        app = self.app
        for build, destination in ((app.build_home, 'home'), (app.build_documents_hub, 'documents')):
            with self.subTest(destination=destination):
                with patch.object(app.adaptive, 'content_width', return_value=390):
                    hub = build()
                    original = list(hub.content.children)
                    trailing = hub.trailing
                    self.assertFalse(hub.paired)
                with patch.object(app.adaptive, 'content_width', return_value=960):
                    hub.reflow(app, destination)
                    self.assertTrue(hub.paired)
                    self.assertEqual(len(hub.children), 2)
                    self.assertIs(trailing.parent, hub.trailing_content)
                    self.assertNotIn(trailing, hub.content.children)
                    self.assertEqual(hub.leading_scroll.style.width, 480)
                    self.assertEqual(hub.trailing_scroll.style.width, 480)
                    self.assertEqual(hub.leading_scroll.style.flex, 0)
                    # Relayout must reuse the controls and their callbacks.
                    hub.reflow(app, destination)
                    self.assertIs(hub.trailing, trailing)
                with patch.object(app.adaptive, 'content_width', return_value=390):
                    hub.reflow(app, destination)
                    self.assertFalse(hub.paired)
                    self.assertEqual(list(hub.content.children), original)
                    self.assertEqual(len(hub.children), 1)

    def test_retained_native_hub_cannot_keep_a_landscape_minimum_in_portrait(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from toga.style.pack import NONE
        app = self.app
        hub = app.build_home()
        bounds = SimpleNamespace(size=SimpleNamespace(width=750))
        with patch.object(type(hub._impl), '__module__', 'toga_iOS.widgets.box'), \
                patch.object(hub._impl, 'native', SimpleNamespace(bounds=bounds), create=True):
            with patch.object(app.adaptive, 'content_width', return_value=900):
                hub.reflow(app, 'home')
                self.assertTrue(hub.paired)
                self.assertEqual(hub.leading_scroll.style.width, 375)
            with patch.object(app.adaptive, 'content_width', return_value=402):
                hub.reflow(app, 'home')
                self.assertFalse(hub.paired)
                self.assertEqual(hub.leading_scroll.style.width, NONE)
                self.assertIs(hub.trailing.parent, hub.content)
            bounds.size.width = 350
            with patch.object(app.adaptive, 'content_width', return_value=900):
                hub.reflow(app, 'home')
                self.assertFalse(hub.paired)

    def test_partial_fold_forces_sections_and_accounts_for_asymmetric_safe_area(self):
        from unittest.mock import patch
        app = self.app
        for build, destination in ((app.build_home, 'home'), (app.build_documents_hub, 'documents')):
            with self.subTest(destination=destination), patch.object(app.adaptive, 'content_width', return_value=620):
                hub = build()
                from mobile.fold_layout import Division
                with patch('mobile.fold_layout.division', return_value=Division(620 * .46, 0, 0, 700)) as seam:
                    hub.reflow(app, destination)
                    seam.assert_called_once_with(app, hub)
                    self.assertTrue(hub.paired)
                    self.assertAlmostEqual(hub.leading_scroll.style.width, 620 * .46, delta=1)
                    self.assertAlmostEqual(hub.trailing_scroll.style.width, 620 * .54, delta=1)
                    self.assertIs(hub.trailing.parent, hub.trailing_content)
                hub.reflow(app, destination)
                self.assertFalse(hub.paired)

    def test_hub_resize_reflows_both_retained_tabs(self):
        from unittest.mock import patch
        app = self.app
        app.show_home()
        app.show_documents_hub()
        home, documents = app.home_sections, app.documents_sections
        self.assertFalse(hasattr(documents, '_workspace_frame'))
        self.assertIn(documents.leading_scroll, documents.children)
        self.assertTrue(hasattr(app.routes.roots['documents'].children[0], '_workspace_frame'))
        with patch.object(app.adaptive, 'content_width', return_value=900):
            app.adaptive.render()
        self.assertTrue(home.paired)
        self.assertTrue(documents.paired)
        with patch.object(app.adaptive, 'content_width', return_value=390):
            app.adaptive.render()
        self.assertFalse(home.paired)
        self.assertFalse(documents.paired)

    def test_home_heading_is_compact_and_keeps_native_home_label(self):
        import toga
        app = self.app
        app.workspace.active = None
        view = app.build_home()
        labels = [child.text for child in view.content.children if isinstance(child, toga.Label)]
        self.assertEqual(labels[0], 'Home')
        self.assertEqual(view.content.style.margin_top, 8)
        self.assertEqual(view.content.children[0].style.margin_top, 0)
        self.assertNotIn('Read. Write. Organize.', labels)
        self.assertEqual(app.native_host.labels[0], 'Home')

    def test_home_shows_five_recent_files_and_links_to_the_full_documents_workspace(self):
        import toga
        app = self.app
        for index in range(8):
            doc = app.store.create(f'History {index}.txt')
            session = app.workspace.open('managed-text', doc.id, 'text', doc.name)
            app.recent_documents.remember(session)
        app.show_documents_hub()
        app.document_search.value = 'No matching name'
        app.show_home()
        buttons = list({id(widget): widget for widget in widgets(app.body)
                        if isinstance(widget, toga.Button)}.values())
        self.assertEqual(len([button for button in buttons if button.text.startswith('History ')]), 5)
        self.assertNotIn('Your spaces', labels(app.body))
        self.assertNotIn('All open', labels(app.body))
        self.assertFalse(any(button.text == 'Continue' for button in buttons))
        next(button for button in buttons if button.text == 'See all in Documents').on_press()
        self.assertEqual(app.native_host.state.destination, 'documents')
        self.assertEqual(app.document_search.value, '')
        self.assertEqual(len([widget for widget in widgets(app.document_open_list)
                              if hasattr(widget, 'session_id')]), len(app.workspace.sessions))

    def test_documents_search_retains_input_and_finds_saved_files_beyond_recent(self):
        import toga
        from mobile.workspace import Session
        app = self.app
        hidden = app.store.create('Old saved draft.md', b'# Old content')
        for index in range(12):
            doc = app.store.create(f'Recent {index}.txt')
            app.recent_documents.remember(Session('', 'managed-text', doc.id, 'text', title=doc.name))
        app.refresh_documents()
        app.show_documents_hub()
        search = app.document_search
        search.value = 'OLD SAVED'
        self.assertIs(app.document_search, search)
        found = [widget for widget in widgets(app.document_saved_list)
                 if isinstance(widget, toga.Button) and widget.text == 'Old saved draft.md']
        self.assertEqual(len(found), 1)
        self.assertIn('No matching open documents.', labels(app.document_open_list))
        self.assertIn('No matching recent documents.', labels(app.document_recent_list))
        app.loop.run_until_complete(found[0].on_press())
        self.assertEqual(app.current.id, hidden.id)
        self.assertEqual(app.editor.value, '# Old content')

    def test_documents_lists_active_first_and_does_not_repeat_open_files_in_history(self):
        import toga
        app = self.app
        first = app.editor_view.session
        app.new_document()
        active = app.editor_view.session
        app.recent_documents.remember(first)
        app.recent_documents.remember(active)
        app.show_documents_hub()
        rows = [widget for widget in widgets(app.document_open_list) if hasattr(widget, 'session_id')]
        self.assertEqual(rows[0].session_id, active.id)
        self.assertEqual([widget.text for widget in widgets(app.document_recent_list)
                          if isinstance(widget, toga.Button)], ['Clear'])
        app.document_search.value = 'No such filename'
        app.document_search.value = ''
        rows = [widget for widget in widgets(app.document_open_list) if hasattr(widget, 'session_id')]
        self.assertEqual({row.session_id for row in rows}, {first.id, active.id})

    def test_folder_hub_sync_shortcut_precedes_credential_without_transfer_headers(self):
        app = self.app
        app.transfer_busy = True
        app.show_locations()
        app.change_folder_source('rclone')
        view = app.body.children[0]
        frame = view._workspace_frame
        self.assertIsNone(view.transfer_banner)
        self.assertIs(frame.main.children[0], app._sync_status_controls['files'][1])
        credential_row = app.folder_credential.parent
        self.assertIs(frame.main.children[1], app.folder_source_tabs)
        self.assertFalse(app.folder_local_header.children)
        self.assertIn(app.folder_picker_header, frame.main.children)
        self.assertEqual(list(app.folder_picker_header.children), [credential_row])
        self.assertIsNone(app.folder_transfers_button.parent)
        app.transfer_busy = False
        app.transfer_notification = True
        app.transfer_complete = True
        app.refresh_transfer_status()
        self.assertNotIn(view.transfer_banner, view.children)
        app.dismiss_transfer_status()
        self.assertNotIn(view.transfer_banner, view.children)

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
        drawer = app.adaptive.browser(app.native_host.state.destination)
        self.assertIsNone(drawer.extensions)
        self.assertTrue(app.loop.run_until_complete(drawer.open_folder({'path': 'Library'})))
        self.assertEqual({entry.label for entry in drawer.browser.entries}, set(names))
        with patch.object(app, 'open_download', new_callable=AsyncMock) as reader:
            for name in names[:3]:
                self.assertTrue(app.loop.run_until_complete(drawer.open_file({'path': 'Library/' + name})))
                reader.assert_awaited_with(path=folder / name, destination='home')

    def test_home_browse_refreshes_local_root_after_other_views_and_search(self):
        import toga
        app = self.app
        from services.documents.locations import use_shared_local, _shared_local_roots
        shared_directory = TemporaryDirectory()
        self.addCleanup(shared_directory.cleanup)
        shared = Path(shared_directory.name)
        use_shared_local(app.private_root, shared)
        self.addCleanup(_shared_local_roots.pop, app.private_root, None)
        def button(widget):
            if isinstance(widget, toga.Button) and widget.text == 'Workspaces':
                return widget
            children = list(widget.children)
            if isinstance(widget, toga.ScrollContainer) and widget.content is not None:
                children.append(widget.content)
            return next((found for child in children if (found := button(child)) is not None), None)
        async def press_home():
            app.show_home()
            # Workspaces remains a destination command; Home no longer repeats
            # its tab as a large shortcut card.
            await app.show_home_files()
            self.assertEqual(app.native_host.state.destination, 'files')
            self.assertIn('All files', app.folder_picker_choices)
            app.change_folder_source('Local')
            await app.folder_buttons['All files'].on_press()
            self.assertIn(app.files_view, app.body.children)
            self.assertEqual(app.file_storage.value, 'Shared files')
            self.assertEqual(app.file_path, '')
            self.assertEqual(app.file_browser.search.value, '')
        async def exercise():
            await press_home()
            root = shared
            (root / 'Notes').mkdir()
            (root / 'Notes' / 'Draft.md').write_text('# Draft')
            await app.browser_file_location(('Shared files', 'Notes'))
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

    def test_home_recent_resumes_selected_document_and_preview(self):
        app = self.app
        app.name.value = 'Notes.md'
        app.editor.value = '# Retained'
        first = app.editor_view.session.id
        app.show_preview()
        app.show_home()
        recent = next(widget for widget in widgets(app.body)
                      if getattr(widget, 'text', '') == 'Notes.md')
        app.loop.run_until_complete(recent.on_press())
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
        app.create_chosen_document('txt', name='Second.txt')
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
        self.assertEqual(content.children[0].text, 'Home')
        self.assertIsNone(app.home_continue)
        self.assertIn('Focus.md', [getattr(widget, 'text', '') for widget in widgets(content)])
        self.assertNotIn('Markdown', labels(content))
        self.assertNotIn('Markdown', labels(app.recent_row(app.editor_view.session, app.session_summary(app.editor_view.session))))
        self.assertNotIn('Markdown', labels(app.session_panel(app.editor_view.session)))
        actions = app.home_actions
        self.assertTrue(all(isinstance(button, toga.Button) for button in actions.children))
        self.assertEqual([button.text for button in actions.children], ['Open file…', 'New document'])
        recent = next(widget for widget in widgets(content) if getattr(widget, 'text', '') == 'Focus.md')
        app.loop.run_until_complete(recent.on_press())
        self.assertIs(app.body.children[0], app.document_view)
        self.assertEqual(app.editor.value, '# A retained draft')

    def test_open_document_links_have_direct_close_controls_in_both_views(self):
        import toga
        app = self.app
        session = app.editor_view.session
        for row in (app.session_panel(session, close=True),):
            actions = next(child for child in row.children if any(isinstance(button, toga.Button) for button in child.children))
            name, close = actions.children
            self.assertEqual([glyph for glyph, _ in name.leading_icons], ['storage_local'])
            self.assertEqual(name.text, app.session_summary(session)[0])
            self.assertFalse(getattr(name._impl, '_row_hint', False))
            self.assertEqual(close.text, '×')
        clean = app.store.create('Close-me.txt')
        session = app.workspace.open('managed-text', clean.id, 'text', clean.name)
        row = app.session_panel(session, close=True)
        row.children[-1].children[-1].on_press()
        self.assertNotIn(session.id, app.workspace.sessions)

    def test_documents_show_all_open_without_expanding(self):
        app = self.app
        app.preferences.save(document_card_overview='false')
        documents = [app.store.create(name) for name in ('Notes.txt', 'Plan.MD', 'Plan.MD')]
        for doc in documents:
            session = app.workspace.open('managed-text', doc.id, 'text', doc.name)
            app.recent_documents.remember(session)
        content = app.build_documents_hub().content
        self.assertIn('Recent', labels(content))
        self.assertFalse(any(getattr(widget, 'text', '').startswith('Open ·') for widget in widgets(content)))
        section = open_documents(content)
        rows = [widget for widget in widgets(section) if hasattr(widget, 'session_id')]
        self.assertEqual(len(rows), len(app.workspace.sessions))
        names = [row.children[-1].children[-2].text for row in rows]
        self.assertEqual(names.count('Plan.MD'), 2)  # Identity, not name, defines a document.
        rebuilt = open_documents(app.build_documents_hub().content)
        self.assertEqual(sum(hasattr(widget, 'session_id') for widget in widgets(rebuilt)), len(rows))
        recent = app.recent_items()
        self.assertTrue({doc.id for doc in documents} <= {item.resource for item, _ in recent})
        self.assertEqual(len(recent), len({item.identity for item, _ in recent}))

    def test_old_open_items_do_not_displace_bounded_recent_history(self):
        app = self.app
        for index in range(12):
            doc = app.store.create(f'File-{index}.txt')
            session = app.workspace.open('managed-text', doc.id, 'text', doc.name)
            app.recent_documents.remember(session)
        recent = app.recent_items()
        self.assertEqual(len(recent), 10)
        self.assertEqual([summary[0] for _, summary in recent],
                         [f'File-{index}.txt' for index in range(11, 1, -1)])
        content = app.build_documents_hub().content
        section = open_documents(content)
        self.assertEqual(sum(hasattr(widget, 'session_id') for widget in widgets(section)),
                         len(app.workspace.sessions))

    def test_recent_live_draft_uses_current_owner_and_closed_draft_recovers(self):
        app = self.app
        app.name.value = 'Live.md'
        app.editor.value = '# Keep these edits'
        owner = app.editor_view
        app.save_workspace()
        session, summary = next(item for item in app.recent_items() if item[0].resource == owner.document.id)
        self.assertIs(session, owner.session)
        self.assertTrue({'Unsaved changes', 'Draft'} <= set(summary[2]))
        row = app.recent_row(session, summary)
        self.assertEqual(labels(row), ['Open · Unsaved · Draft'])
        status = row.children[-1]
        self.assertEqual(status.style.font_size, 12)
        self.assertEqual(status._impl._surface_roles[:2], ('transparent', 'muted'))
        app.loop.run_until_complete(app.recent_opener(session)())
        self.assertIs(app.editor_view, owner)
        self.assertEqual(owner.document.text, '# Keep these edits')
        app.close_session(session.id, choice='keep')
        closed, summary = next(item for item in app.recent_items() if item[0].resource == owner.document.id)
        self.assertTrue({'Unsaved changes', 'Recovered draft'} <= set(summary[2]))
        self.assertEqual(labels(app.recent_row(closed, summary)), ['Unsaved · Recovered'])
        app.loop.run_until_complete(app.recent_opener(closed)())
        self.assertEqual(app.current.text, '# Keep these edits')
        app.save_document()
        saved, summary = next(item for item in app.recent_items() if item[0].resource == app.current.id)
        self.assertEqual(summary[2], [])
        self.assertEqual(labels(app.recent_row(saved, summary)), ['Open'])

    def test_recent_keeps_last_use_order_across_open_and_closed_documents(self):
        app = self.app
        app.editor.value = 'First'
        app.save_document()
        first = app.editor_view.session
        app.new_document()
        app.editor.value = 'Second'
        app.save_document()
        second = app.editor_view.session
        app.save_workspace()
        app.request_close_session(first.id)
        recent = app.recent_items()
        self.assertEqual([item.resource for item, _ in recent[:2]], [second.resource, first.resource])
        app.loop.run_until_complete(app.recent_opener(first)())
        self.assertEqual(app.recent_items()[0][0].resource, first.resource)

    def test_documents_stay_compact_with_legacy_card_preference(self):
        from mobile.preferences import Preferences
        app = self.app
        app.name.value = 'Draft.md'
        app.editor.value = '# Current draft\nStill unsaved'
        owner = app.editor_view
        app.preferences.path.write_text('[Mobile]\ndocument_card_overview = true\nfont_size = 20\n')
        app.preferences.reload()
        self.assertEqual(app.preferences.values['document_card_overview'], 'false')
        self.assertEqual(app.preferences.values['font_size'], '20')
        self.assertEqual(app.preferences.error, '')
        app.show_documents_hub()
        self.assertEqual(app.document_grids, [])
        self.assertFalse(any('Current draft' in value for value in labels(app.body)))
        recent = app.recent_row(owner.session, app.session_summary(owner.session))
        app.loop.run_until_complete(recent.children[0].children[0].on_press())
        self.assertIs(app.editor_view, owner)
        self.assertEqual(app.editor.value, '# Current draft\nStill unsaved')
        app.session_closer(owner.session.id)()
        self.assertIn(owner.session.id, app.workspace.sessions)
        app.preferences.save(document_card_overview='true')
        self.assertEqual(Preferences(app.private_root).values['document_card_overview'], 'false')

    def test_settings_have_no_card_overview_and_keep_feature_groups(self):
        app = self.app
        app.show_settings()
        categories = app.settings_navigation.sections
        sections = ['App', 'Text', 'Books & Comics', 'LM Chat', 'Workspaces']
        self.assertEqual([title for title in categories if title in sections], sections)
        self.assertFalse(any(getattr(widget, 'text', '') == 'Document card overview'
                             for section in categories.values() for widget in widgets(section)))
        self.assertFalse(hasattr(app, 'document_cards_choice'))
        app.save_preferences()
        self.assertEqual(app.preferences.error, '')
        app.show_documents_hub()
        self.assertEqual(app.document_grids, [])
        section = open_documents(app.routes.roots['documents'])
        self.assertTrue(any(hasattr(widget, 'session_id') for widget in widgets(section)))

    def test_restored_sessions_resolve_filenames_without_opening_readers(self):
        from commonUtils.runtime.resources.documents import LocalDocuments
        from mobile.workspace import Workspace
        from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
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
        self.assertEqual(app.session_summary(session), ('Recovered.md', 'markdown', ['Unsaved changes', 'Recovered draft']))
        app.store.path(doc.id, '.json').unlink()
        row = app.session_panel(session, close=True, show_kind=False)
        self.assertTrue(any('Unavailable' in text for text in labels(row)))
        self.assertEqual(row.close_button.text, '×')

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
        app.preferences.save(restore_last_document='false')
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
        app.settings_navigation.choose('App')
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

    def test_new_document_validation_cancel_and_plain_text(self):
        app = self.app
        previous = app.current
        count = len(app.store.documents()[0])
        app.loop.run_until_complete(app.new_hub_document())
        form = app.editor_picker()
        for invalid in ('', '../bad'):
            form.save_as_name.value = invalid
            app.loop.run_until_complete(form.browser_editor_location(('Local', '')))
            app.loop.run_until_complete(form.confirm_editor_file())
            self.assertIs(app.current, previous)
            self.assertTrue(form.save_as_status.value)
            self.assertEqual(len(app.store.documents()[0]), count)
        form.cancel_text_destination()
        self.assertIs(app.current, previous)
        app.loop.run_until_complete(app.new_hub_document())
        form = app.editor_picker()
        form.save_as_name.value = 'Notes.txt'
        form.creation_type.value = 'Markdown (.md)'
        form.creation_type.value = 'Plain text (.txt)'
        app.loop.run_until_complete(form.browser_editor_location(('Local', '')))
        app.loop.run_until_complete(app.editor_picker().confirm_editor_file())
        self.assertEqual(app.private_sessions.active.crypt_reader.name, 'Notes.txt')
        self.assertEqual(app.private_sessions.active.crypt_text.value, '')

    def test_markdown_choice_and_independent_chat_destination(self):
        app = self.app
        app.loop.run_until_complete(app.new_hub_document())
        form = app.editor_picker()
        self.assertIn(form.creation_type, form.save_as_view.children)
        form.save_as_name.value = 'Trip.markdown'
        form.creation_type.value = 'Markdown (.md)'
        app.loop.run_until_complete(form.browser_editor_location(('Local', '')))
        app.loop.run_until_complete(app.editor_picker().confirm_editor_file())
        self.assertEqual(app.private_sessions.active.crypt_reader.name, 'Trip.markdown')
        self.assertEqual(app.private_sessions.active.crypt_text.value, '')
        self.assertEqual(app.private_sessions.active.session.kind, 'markdown')
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
