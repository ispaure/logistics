"""Vault detection, rooted Markdown browsing and revoked private reads."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from toga_dummy.utils import EventLog

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceSelection
from mobile.app import LogisticsMobile
from mobile.browser_ui import FileBrowser
from mobile.obsidian import VaultBrowser, vault_root, open_vault


class ObsidianTests(unittest.TestCase):
    def test_private_note_render_can_expand_beyond_source_limit(self):
        from services.documents.storage import DocumentPolicy
        from features.notes_library.notes import MAX_NOTE, MAX_PREVIEW_HTML
        # Valid source expands past 2 MiB after HTML escaping.
        (self.vault / 'Expanded.md').write_text('& ' * 400000)
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.access.policy = DocumentPolicy(False, True)
            surface = owner.access.webview(max_bytes=MAX_PREVIEW_HTML)
            self.assertEqual(surface.max_html_bytes, MAX_PREVIEW_HTML)
            with patch.object(self.app.main_window, 'dialog') as dialog, \
                    patch.object(owner.web, 'set_content', wraps=owner.web.set_content) as publish:
                self.assertTrue(await owner.open_note('Vault/Expanded.md'))
                dialog.assert_not_called()
            self.assertGreater(len(publish.call_args.args[1].encode('utf-8')), MAX_NOTE)
            self.assertEqual(owner.path, 'Vault/Expanded.md')
            self.assertEqual(owner.notice.text, '')
        self.run_async(exercise())

    def test_private_preview_limit_uses_popup_and_retains_published_page(self):
        from services.documents.storage import DocumentPolicy
        from unittest.mock import AsyncMock
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            self.assertTrue(await owner.open_note('Vault/Home.md'))
            owner.access.policy = DocumentPolicy(False, True)
            history, base = list(owner.history), owner.base
            def check(html, max_bytes):
                # Exercise the real rejection without allocating 32 MiB.
                from services.documents.mobile_storage import NotesDocumentAccess
                NotesDocumentAccess.validate_preview(owner.access, html, 1)
            async def show(dialog):
                self.assertFalse(owner.page_loading.active)
                self.assertIn(owner.web, owner.article.children)
            with patch.object(owner.access, 'validate_preview', side_effect=check), \
                    patch.object(owner.web, 'set_content') as publish, \
                    patch.object(self.app.main_window, 'dialog', new=AsyncMock(side_effect=show)) as dialog:
                self.assertFalse(await owner.open_note('Vault/Projects/Plan.MD'))
                dialog.assert_awaited_once()
                message = EventLog.performed_actions(dialog.call_args.args[0], 'create ErrorDialog')[0]['message']
                self.assertIn('in-memory preview limit', message)
                publish.assert_not_called()
            self.assertEqual(owner.path, 'Vault/Home.md')
            self.assertEqual(owner.history, history)
            self.assertEqual(owner.base, base)
            self.assertEqual(owner.notice.text, '')
            self.assertEqual(set(owner.library._media), {'Vault/Home.md'})
        self.run_async(exercise())

    def test_failed_cancelled_and_superseded_note_attempts_retire_only_abandoned_media(self):
        from dataclasses import replace
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            current = owner.library._media['Vault/Home.md']
            original_host = owner.host
            for cancel in (False, True):
                attempts = []
                def preview(text, **kwargs):
                    attempts.append(owner.library._media['Vault/Projects/Plan.MD'])
                    if not cancel:
                        raise ValueError('Rejected preview')
                    self.app.loop.call_soon_threadsafe(owner.page_loading.cancel)
                    return '<html><body>Cancelled preview</body></html>'
                owner.host = replace(original_host, preview=preview)
                self.assertFalse(await owner.open_note('Vault/Projects/Plan.MD'))
                self.assertTrue(attempts[0].closed)
                self.assertFalse(current.closed)
                self.assertEqual(set(owner.library._media), {'Vault/Home.md'})
            entered, released, attempts = Event(), Event(), []
            def preview(text, **kwargs):
                attempts.append(owner.library._media['Vault/Projects/Plan.MD'])
                entered.set()
                if not released.wait(5):
                    raise RuntimeError('Delayed preview timed out')
                return '<html><body>Superseded preview</body></html>'
            owner.host = replace(original_host, preview=preview)
            task = asyncio.create_task(owner.open_note('Vault/Projects/Plan.MD'))
            try:
                for _ in range(100):
                    if entered.is_set():
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(entered.is_set())
                owner.host = original_host
                self.assertTrue(await owner.open_note('Vault/Home.md'))
                released.set()
                self.assertFalse(await task)
                self.assertTrue(attempts[0].closed)
                self.assertFalse(owner.library._media['Vault/Home.md'].closed)
            finally:
                released.set()
                await task
                owner.host = original_host
        self.run_async(exercise())

    def setUp(self):
        import toga
        factory = patch('services.documents.mobile_views.document_webview',
                        side_effect=lambda resource=None, **options: toga.WebView(**options))
        factory.start()
        self.addCleanup(factory.stop)
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        LogisticsMobile.storage_root = self.root / 'app'
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.main_window._impl.dialog_responses['ErrorDialog'] = [None] * 10
        self.vault = self.root / 'Vault'
        (self.vault / '.obsidian').mkdir(parents=True)
        (self.vault / '.obsidian/private.md').write_text('# Configuration')
        (self.vault / 'Projects').mkdir()
        (self.vault / 'Projects/Plan.MD').write_text('# Plan\n\n**Nested note**')
        (self.vault / 'Home.md').write_text('# Home\n\n[Plan](Projects/Plan.MD)')
        (self.vault / 'attachment.txt').write_text('Not a note')
        self.provider = LocalFiles(self.root)

    def tearDown(self):
        owner = getattr(self.app, 'vault_browser', None)
        if owner:
            owner.dispose()
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.temporary.cleanup()

    def run_async(self, awaitable):
        return self.app.loop.run_until_complete(awaitable)

    def test_detection_requires_local_directory_marker_and_current_root(self):
        rows = self.provider.list('Vault')
        self.assertEqual(vault_root(self.provider, 'Vault', rows), 'Vault')
        self.assertEqual(vault_root(ResourceSelection(self.provider), 'Vault', rows), 'Vault')
        self.assertIsNone(vault_root(SimpleNamespace(), 'Vault', rows))
        self.assertIsNone(vault_root(self.provider, '', self.provider.list('')))
        self.assertIsNone(vault_root(self.provider, 'Vault', [dict(path='Vault/.obsidian', directory=False)]))
        self.assertEqual(vault_root(LocalFiles(self.vault), '', LocalFiles(self.vault).list('')), '')

    def test_library_owns_screen_and_nested_editor_returns_to_library(self):
        from mobile.reader_lifecycle import document_route, session_route
        owner = self.run_async(open_vault(self.app, self.provider, 'Vault', 'files'))
        route = 'notes-library:' + owner.session.id
        self.assertTrue(document_route(route))
        self.assertFalse(session_route(route))
        self.assertTrue(self.app._document_tabs_hidden)
        self.assertFalse(hasattr(owner.view, '_workspace_frame'))
        self.assertTrue(self.run_async(owner.open_note('Vault/Home.md')))
        self.assertTrue(self.run_async(owner.open_editor()))
        self.assertIsNotNone(owner.embedded)
        self.assertEqual(self.app.visible_reader(), owner.session.id)
        self.assertEqual(self.app.routes.screens['files'][-1][0], route)
        owner.close()
        self.run_async(owner._close_task)
        self.assertEqual(self.app.native_host.state.destination, 'files')
        self.assertFalse(self.app.routes.screens['files'])
        self.assertFalse(self.app._document_tabs_hidden)

    def test_close_during_transfer_and_pending_note_read_keeps_transfer_running(self):
        from unittest.mock import Mock
        app = self.app
        app.show_cloud(present=False)
        app.show_locations()
        owner = self.run_async(open_vault(app, self.provider, 'Vault', 'files'))
        key = owner.session.id
        entered, released = Event(), Event()
        original = self.provider.open
        def delayed(path):
            entered.set()
            if not released.wait(5):
                raise RuntimeError('Note read fixture timed out')
            return original(path)
        async def exercise():
            restore = getattr(app, 'cloud_restore_task', None)
            if restore is not None:
                await restore
            app.cloud_client = SimpleNamespace(generation=1, cancel=Mock(), package_records=[])
            app.transfer_busy = True
            app.set_cloud_busy(True)
            generation = app.cloud_client.generation
            with patch.object(self.provider, 'open', side_effect=delayed), \
                    patch.object(app.cloud_client, 'cancel', new=Mock()) as cancel, \
                    patch.object(owner.web, 'set_content') as publish:
                task = asyncio.create_task(owner.open_note('Vault/Home.md'))
                try:
                    for _ in range(100):
                        if entered.is_set():
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(entered.is_set())
                    self.assertTrue(owner.close_button.enabled)
                    owner.close_button.on_press()
                    self.assertNotIn(key, app.workspace.sessions)
                    self.assertFalse(app.routes.screens['files'])
                    self.assertEqual(app.native_host.state.destination, 'files')
                    self.assertFalse(app._document_tabs_hidden)
                    self.assertTrue(app.transfer_busy)
                    self.assertTrue(app.cloud_busy)
                    self.assertEqual(app.cloud_client.generation, generation)
                    cancel.assert_not_called()
                    publish.reset_mock()  # Disposing clears the page; late reads must not replace it.
                finally:
                    released.set()
                    await task
                    app.transfer_busy = False
                    app.set_cloud_busy(False)
                publish.assert_not_called()
        self.run_async(exercise())

    def test_file_browser_has_no_vault_action(self):
        browser = FileBrowser()
        try:
            browser.set_entries(ResourceSelection(self.provider), 'Vault', self.provider.list('Vault'))
            self.assertFalse(hasattr(browser, 'vault_button'))
            self.assertFalse(any(getattr(button, 'control_icon', '') == 'obsidian'
                for button in browser.navigation_controls.children))
        finally:
            self.run_async(browser.close())

    def test_slow_note_and_history_reads_show_loading_and_clear_on_failure(self):
        owner = self.run_async(open_vault(self.app, self.provider, 'Vault', 'files'))
        async def exercise():
            await owner.open_note('Vault/Home.md')
            await owner.open_note('Vault/Projects/Plan.MD')
            entered, released = Event(), Event()
            original = owner.library.read
            def slow(path, **kwargs):
                entered.set()
                if not released.wait(5):
                    raise RuntimeError('Slow read timed out')
                return original(path, **kwargs)
            with patch.object(owner.library, 'read', side_effect=slow):
                task = asyncio.create_task(owner.navigate_history(-1))
                try:
                    for _ in range(100):
                        if entered.is_set():
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(entered.is_set())
                    self.assertTrue(owner.page_loading.active)
                    self.assertIs(owner.page_loading.panel.parent, owner.article)
                    self.assertEqual(owner.path, 'Vault/Projects/Plan.MD')
                finally:
                    released.set()
                    await task
            self.assertFalse(owner.page_loading.active)
            self.assertEqual(owner.path, 'Vault/Home.md')
            from unittest.mock import AsyncMock
            with patch.object(owner.library, 'read', side_effect=OSError('Offline')), \
                    patch.object(self.app.main_window, 'dialog', new=AsyncMock()) as dialog:
                self.assertFalse(await owner.open_note('Vault/Projects/Plan.MD'))
                self.assertEqual(EventLog.performed_actions(dialog.call_args.args[0], 'create ErrorDialog')[0]['message'], 'Offline')
            self.assertFalse(owner.page_loading.active)
            self.assertEqual(owner.notice.text, '')
        self.run_async(exercise())

    def test_nested_markdown_preview_and_adaptive_tree_keep_provider_identity(self):
        owner = self.run_async(open_vault(self.app, self.provider, 'Vault', 'files'))
        def paths():
            return [next(child.vault_path for child in row.children if hasattr(child, 'vault_path')) for row in owner.rows.children]
        self.assertEqual(paths(), ['Vault/Projects', 'Vault/attachment.txt', 'Vault/Home.md'])
        self.assertEqual([row.children[1].browser_entry_kind for row in owner.rows.children], ['folder', 'file', 'file'])
        self.run_async(owner.toggle_folder('Vault/Projects'))
        self.assertEqual(paths(), ['Vault/Projects', 'Vault/Projects/Plan.MD', 'Vault/attachment.txt', 'Vault/Home.md'])
        self.assertEqual(owner.rows.children[1].children[0].style.width, 20)
        self.assertTrue(self.run_async(owner.open_note('Vault/Projects/Plan.MD')))
        self.assertEqual(owner.path, 'Vault/Projects/Plan.MD')
        selected = next(row for row in owner.rows.children if any(getattr(child, 'vault_path', None) == owner.path for child in row.children))
        self.assertEqual(selected._impl._surface_roles[0], 'hover')
        owner.reflow(390)
        self.assertIs(owner.toolbar.parent, owner.view)
        self.assertEqual(list(owner.sidebar.view.children), [owner.article])
        owner.menu.on_press()
        self.assertEqual(list(owner.sidebar.view.children), [owner.article])
        self.assertEqual(owner.sidebar.side, 'files')
        owner.reflow(900)
        self.assertEqual(list(owner.sidebar.view.children), [owner.tree, owner.article])
        self.assertIsNone(owner.sidebar.overlay)
        self.assertFalse(owner.sidebar.sidebar_open)
        self.assertIs(owner.toolbar.parent, owner.article)
        self.assertIn(owner.toolbar, owner.article.children)
        self.assertTrue(all(button.parent is owner.secondary for button in
            (owner.back_button, owner.forward_button, owner.reader_actions_button)))
        self.assertIsNone(owner.up_button.parent)
        self.assertIsNone(owner.speech.button.parent)
        self.assertIn('Read aloud…', [label for label, _ in owner.reader_actions.actions])
        owner.reflow(390)
        self.assertEqual(list(owner.sidebar.view.children), [owner.article])
        self.assertIs(owner.toolbar.parent, owner.view)
        owner.reflow(900)
        self.assertTrue(self.run_async(owner.open_editor()))
        self.assertIs(owner.embedded.library, owner)
        self.assertEqual(owner.embedded.path, 'Vault/Projects/Plan.MD')
        self.assertIs(owner.embedded.resource.provider, self.provider)
        with patch.object(self.app, 'folder_path_visible', side_effect=lambda path, **kw: 'Projects' not in path):
            self.app.refresh_folder_visibility()
            self.assertEqual(paths(), ['Vault/attachment.txt', 'Vault/Home.md'])

    def test_links_stay_within_vault_and_text_opens_in_library(self):
        owner = self.run_async(open_vault(self.app, self.provider, 'Vault', 'files'))
        self.run_async(owner.open_note('Vault/Home.md'))
        owner.follow_link(owner.web, owner.base + '?target=Projects%2FPlan.MD')
        self.run_async(asyncio.sleep(.05))
        self.assertEqual(owner.path, 'Vault/Projects/Plan.MD')

        for target in ('../../outside.md', '/tmp/outside.md', '../.obsidian/private.md', 'https://example.com/note.md'):
            self.assertFalse(owner.follow_link(owner.web, target))
        self.assertTrue(self.run_async(owner.open_note('Vault/attachment.txt')))
        self.assertEqual(owner.path, 'Vault/attachment.txt')
        self.assertTrue(self.run_async(owner.open_note('Vault/Projects/Plan.MD')))
        self.assertFalse(self.run_async(owner.open_note('Vault/.obsidian/private.md')))
        self.assertFalse(self.run_async(owner.open_note('outside.md')))
        self.assertEqual(owner.path, 'Vault/Projects/Plan.MD')

    def test_folder_landing_note_opens_directly_and_remains_a_manageable_child(self):
        landing = self.vault / 'Projects/Projects.md'
        landing.write_text('# Projects\n')
        owner = self.run_async(open_vault(self.app, self.provider, 'Vault', 'files'))
        def folder_row():
            return next(row for row in owner.rows.children
                        if any(getattr(child, 'vault_path', None) == 'Vault/Projects' for child in row.children))
        self.assertEqual(folder_row().children[1].browser_entry_kind, 'folder_document')
        self.run_async(next(child for child in folder_row().children if hasattr(child, 'vault_path')).on_press())
        self.assertEqual(owner.path, 'Vault/Projects/Projects.md')
        self.run_async(folder_row().children[2].on_press())
        self.assertIn('Vault/Projects/Projects.md', [child.vault_path for row in owner.rows.children for child in row.children if hasattr(child, 'vault_path')])
        self.assertEqual(owner.selected_path, 'Vault/Projects')
        child = next(child for row in owner.rows.children for child in row.children
                     if getattr(child, 'vault_path', None) == 'Vault/Projects/Projects.md')
        self.run_async(child.on_press())
        self.assertEqual(owner.selected_path, 'Vault/Projects/Projects.md')
        owner.library.move('Vault/Projects/Projects.md', 'Vault/Projects/Overview.md')
        self.run_async(owner.load_folder('Vault'))
        self.run_async(owner.load_folder('Vault/Projects'))
        self.assertEqual(folder_row().children[1].browser_entry_kind, 'folder')
        self.assertIn('Vault/Projects/Overview.md', [child.vault_path for row in owner.rows.children for child in row.children if hasattr(child, 'vault_path')])

    def test_oversized_and_linked_notes_do_not_replace_the_current_preview(self):
        owner = self.run_async(open_vault(self.app, self.provider, 'Vault', 'files'))
        self.assertTrue(self.run_async(owner.open_note('Vault/Home.md')))
        (self.vault / 'Huge.md').write_bytes(b'x' * (3 * 1024 * 1024))
        (self.vault / 'Link.md').symlink_to(self.vault / 'Home.md')
        for path in ('Vault/Huge.md', 'Vault/Link.md'):
            self.assertFalse(self.run_async(owner.open_note(path)))
            self.assertEqual(owner.path, 'Vault/Home.md')

    def test_private_read_cannot_publish_after_credentials_are_revoked(self):
        class PrivateFiles(LocalFiles):
            private = True
        provider = PrivateFiles(self.root)
        client = self.app.cloud_client = SimpleNamespace(generation=1, cancel=lambda: None)
        def capture(path):
            generation = client.generation
            def check():
                if client.generation != generation:
                    raise ValueError('Source access revoked')
            return check
        provider.capture_access = capture
        owner = VaultBrowser(self.app, provider, 'Vault', 'files')
        self.app.vault_browser = owner
        entered, released = Event(), Event()
        original = provider.open
        def delayed(path):
            entered.set()
            if not released.wait(5):
                raise RuntimeError('Private read fixture timed out')
            return original(path)
        async def exercise():
            with patch.object(provider, 'open', side_effect=delayed), patch.object(owner.web, 'set_content') as publish:
                task = asyncio.create_task(owner.open_note('Vault/Home.md'))
                try:
                    for _ in range(100):
                        if entered.is_set():
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(entered.is_set())
                    client.generation += 1
                    released.set()
                    self.assertFalse(await task)
                    publish.assert_not_called()
                finally:
                    released.set()
                    await task
        self.run_async(exercise())
        owner.dispose()
        self.assertEqual(owner.rows.children, [])
        self.assertIsNone(owner.path)
        self.assertEqual(owner.title.text, 'Notes Library closed')

    def test_credential_catalog_cleanup_clears_private_vault_preview(self):
        self.app.show_cloud(present=False)
        class PrivateFiles(LocalFiles):
            private = True
        owner = self.run_async(open_vault(self.app, PrivateFiles(self.root), 'Vault', 'files'))
        self.assertTrue(self.run_async(owner.open_note('Vault/Home.md')))
        self.app.clear_private_catalog()
        self.assertFalse(owner.valid())
        self.assertIsNone(owner.path)
        self.assertEqual(owner.rows.children, [])
