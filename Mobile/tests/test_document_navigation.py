"""Document entry points preserve the selected tab and retained source panels."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from logisticsmobile.app import LogisticsMobile
from Mobile.native_tests.tests.logisticsmobile.fixtures import make_books


class DocumentNavigationTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        LogisticsMobile.storage_root = Path(directory.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.app.show_cloud(present=False)
        self.folder = self.app.private_root / 'LocalFiles' / 'Fixtures'
        self.folder.mkdir(parents=True)
        epub, comic = make_books(self.folder)
        self.paths = [epub, comic]
        for name in ('note.txt', 'note.md'):
            path = self.folder / name
            path.write_text('Retained text')
            self.paths.append(path)
        from Mobile.tests.test_pdf_reader import PDF
        path = self.folder / 'document.pdf'
        path.write_bytes(PDF)
        self.paths.append(path)

    def test_all_formats_keep_home_or_workspace_and_back_restores_same_panel(self):
        from Mobile.tests.test_pdf_reader import native_pdf

        async def exercise():
            for destination in ('home', 'files', 'documents'):
                for path in self.paths:
                    with self.subTest(destination=destination, kind=path.suffix):
                        if destination == 'home':
                            self.app.show_home()
                        elif destination == 'documents':
                            self.app.show_documents_hub()
                        else:
                            await self.app.show_files()
                            await self.app.browser_file_location(('Local files', 'Fixtures'))
                            self.app.file_browser.search.value = path.stem
                        panel = self.app.body
                        children = list(panel.children)
                        routes = list(self.app.routes.screens[destination])
                        query = self.app.file_browser.search.value if destination == 'files' else None
                        with patch('features.pdf.document.PDFDocument.open', native_pdf):
                            self.assertTrue(await self.app.open_download(path=path))
                            self.assertEqual(self.app.native_host.state.destination, destination)
                            self.assertFalse(self.app.routes.origins)
                            session = self.app.workspace.active
                            # Preview/tools are detail steps within the same tab.
                            while len(self.app.routes.screens[destination]) > len(routes):
                                self.assertTrue(self.app.routes.back())
                        self.assertIs(self.app.body, panel)
                        self.assertEqual(list(panel.children), children)
                        self.assertEqual(self.app.routes.screens[destination], routes)
                        self.assertIn(session, self.app.workspace.sessions)
                        if destination == 'files':
                            self.assertEqual(self.app.file_path, 'Fixtures')
                            self.assertEqual(self.app.file_browser.search.value, query)
            if hasattr(self.app, 'readers'):
                await self.app.readers.catalog.metadata_task
                await self.app.readers.catalog.library_scan_task
        self.app.loop.run_until_complete(exercise())

    def test_reopening_retained_editor_in_another_tab_moves_view_and_keeps_draft(self):
        app = self.app
        app.show_documents_hub()
        app.show_documents(edit=True)
        owner = app.editor_view
        owner.editor.value = 'Unsaved draft stays with this session'
        session = owner.session.id
        app.show_home()
        origin = app.body
        app.session_opener(session)()
        self.assertEqual(app.native_host.state.destination, 'home')
        self.assertIs(app.editor_view, owner)
        self.assertFalse(app.routes.screens['documents'])
        self.assertEqual(list(app.native_host.bodies['documents'].children),
                         [app.routes.roots['documents']])
        self.assertFalse(hasattr(owner.document_view, '_workspace_frame'))
        self.assertEqual(owner.editor.value, 'Unsaved draft stays with this session')
        self.assertTrue(app.routes.back())
        self.assertIs(app.body, origin)
        app.show_documents_hub()
        app.session_opener(session)()
        self.assertEqual(owner.document_view._workspace_frame.destination, 'documents')
        self.assertEqual(owner.editor.value, 'Unsaved draft stays with this session')

    def test_home_open_file_browser_and_provider_text_keep_home(self):
        app = self.app
        app.show_home()
        origin = app.body
        async def exercise():
            self.assertTrue(await app.open_hub_file())
            self.assertEqual(app.native_host.state.destination, 'home')
            browser = app.adaptive.browser('home')
            await browser.open_folder({'path': 'Fixtures'})
            panel = app.body
            self.assertTrue(await browser.open_file({'path': 'Fixtures/note.txt'}))
            owner = app.private_sessions.active
            owner.crypt_text.value = 'Provider draft retained'
            self.assertEqual(app.native_host.state.destination, 'home')
            self.assertTrue(app.routes.back())
            self.assertIs(app.body, panel)
            self.assertEqual(browser.folder, 'Fixtures')
            self.assertEqual(owner.crypt_text.value, 'Provider draft retained')
            self.assertTrue(app.routes.back())
            self.assertIs(app.body, origin)
        app.loop.run_until_complete(exercise())

    def test_library_catalog_uses_the_tab_that_opens_it(self):
        app = self.app
        app.reader_manager()  # First constructed from Home.
        for destination in ('documents', 'files', 'home'):
            app.native_host.activate(destination)
            origin = app.routes.body()
            app.show_library()
            self.assertEqual(app.native_host.state.destination, destination)
            self.assertTrue(app.routes.back())
            self.assertIs(app.body, origin)
