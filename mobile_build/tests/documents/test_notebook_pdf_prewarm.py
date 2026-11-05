"""PDF classification yields the mobile loop and cannot publish stale editors."""
import asyncio
import threading
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from features.notebooks.editor import Editor
from features.notebooks.notebook import Notebook
from features.notebooks.mobile.panel import NotebookPanel
from services.documents.mobile_notebooks import open_notebook, notes_editor

TEST_STAGE = TestStage.REGRESSION


def protected_book():
    book = Notebook.new('Protected')
    book.content['fileType'] = 'pdf'
    book.members[book.id + '.pdf'] = b'%PDF-synthetic-classification-only'
    book.pages[0].record['redir'] = dict(value=-1)
    return book


class PdfPrewarmTests(unittest.TestCase):
    def setUp(self):
        from mobile_build.tests.documents.test_notebook_panel import NotebookPanelTests
        NotebookPanelTests.setUp(self)

    def blocked_classifier(self):
        started, released = threading.Event(), threading.Event()
        editors = []
        main_thread = threading.get_ident()
        def classify(editor, password=None):
            if not getattr(editor, '_test_prepared', False):
                self.assertNotEqual(threading.get_ident(), main_thread)
                editors.append(editor)
                started.set()
                if not released.wait(3):
                    raise TimeoutError('fixture classification was not released')
                editor._test_prepared = True
            return None
        return started, released, editors, classify

    def test_standalone_open_yields_then_mounts_the_same_prepared_editor(self):
        book = protected_book()
        started, released, editors, classify = self.blocked_classifier()
        async def scenario():
            task = asyncio.create_task(open_notebook(self.app))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                await asyncio.sleep(0)
                self.assertFalse(task.done())
                self.assertIsNone(self.app.notebook_panel.web)
            finally:
                released.set()
            self.assertTrue(await task)
            self.assertIs(self.app.notebook_panel.editor, editors[0])
            self.assertIsNotNone(self.app.notebook_panel.web)
        with patch('features.notebooks.notebook.Notebook.new', return_value=book), patch.object(Editor, 'pdf_data', classify):
            self.app.loop.run_until_complete(scenario())

    def test_navigation_during_standalone_classification_retires_owner_without_presenting(self):
        book = protected_book()
        started, released, _, classify = self.blocked_classifier()
        async def scenario():
            task = asyncio.create_task(open_notebook(self.app))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                self.app.navigation_generation += 1
            finally:
                released.set()
            self.assertFalse(await task)
            self.assertTrue(self.app.notebook_panel.closed)
            self.assertIsNone(self.app.notebook_panel.editor)
        with patch('features.notebooks.notebook.Notebook.new', return_value=book), patch.object(Editor, 'pdf_data', classify):
            self.app.loop.run_until_complete(scenario())

    def test_classification_error_uses_existing_error_route_and_retires_document(self):
        book = protected_book()
        with patch('features.notebooks.notebook.Notebook.new', return_value=book), \
                patch.object(Editor, 'pdf_data', side_effect=ValueError('Invalid PDF classification')):
            self.assertFalse(self.app.loop.run_until_complete(open_notebook(self.app)))
        panel = self.app.notebook_panel
        self.assertTrue(panel.closed)
        self.assertIsNone(panel.editor)
        self.assertEqual(panel.status.text, 'Invalid PDF classification')

    def test_cancelled_classification_retires_document_without_canceling_worker(self):
        started, released, _, classify = self.blocked_classifier()
        book = protected_book()
        async def scenario():
            task = asyncio.create_task(open_notebook(self.app))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertTrue(self.app.notebook_panel.closed)
                self.assertIsNone(self.app.notebook_panel.editor)
            finally:
                released.set()
        with patch('features.notebooks.notebook.Notebook.new', return_value=book), patch.object(Editor, 'pdf_data', classify):
            self.app.loop.run_until_complete(scenario())

    def test_private_credentials_expiring_during_classification_close_resource_without_reread(self):
        from pathlib import Path
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.storage import DocumentResource
        class PrivateFiles(LocalFiles):
            private = True
            expired = False
            def entry(self, path):
                if self.expired:
                    raise ValueError('Synthetic credentials expired')
                return super().entry(path)
        book = protected_book()
        path = Path(self.temp.name) / 'private.rmdoc'
        path.write_bytes(book.to_bytes())
        provider = PrivateFiles(path.parent)
        resource = DocumentResource(provider, path.name, max_bytes=1024 * 1024)
        started, released, _, classify = self.blocked_classifier()
        async def scenario():
            task = asyncio.create_task(open_notebook(self.app, resource=resource))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                self.assertIs(self.app.notebook_panel.document.resource, resource)
                provider.expired = True
            finally:
                released.set()
            self.assertFalse(await task)
            self.assertTrue(resource.closed)
            self.assertTrue(self.app.notebook_panel.closed)
            self.assertIsNone(self.app.notebook_panel.editor)
            self.assertIn('credentials expired', self.app.notebook_panel.status.text)
        with patch.object(Editor, 'pdf_data', classify), patch.object(provider, 'open', wraps=provider.open) as reads:
            self.app.loop.run_until_complete(scenario())
        self.assertEqual(reads.call_count, 1)

    def test_load_retires_old_canvas_and_does_not_mount_after_navigation(self):
        self.app.loop.run_until_complete(open_notebook(self.app))
        panel = self.app.notebook_panel
        started, released, _, classify = self.blocked_classifier()
        async def scenario():
            task = asyncio.create_task(panel.load(protected_book))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                self.assertIsNone(panel.web)
                self.assertTrue(panel.busy)
                self.app.navigation_generation += 1
            finally:
                released.set()
            self.assertFalse(await task)
            self.assertIsNone(panel.web)
            self.assertFalse(panel.busy)
        with patch.object(Editor, 'pdf_data', classify):
            self.app.loop.run_until_complete(scenario())

    def test_embedded_epoch_or_provider_change_rejects_stale_mount(self):
        from pathlib import Path
        from commonUtils.runtime.resources.local import LocalFiles
        for mutate in ('epoch', 'provider'):
            with self.subTest(mutate=mutate):
                book = protected_book()
                path = Path(self.temp.name) / (mutate + '.rmdoc')
                path.write_bytes(book.to_bytes())
                library = NS(provider=LocalFiles(path.parent), epoch=1, valid=lambda:True, session=NS(dirty=False))
                started, released, _, classify = self.blocked_classifier()
                async def scenario():
                    task = asyncio.create_task(notes_editor(self.app, library, path.name))
                    try:
                        self.assertTrue(await asyncio.to_thread(started.wait, 2))
                        if mutate == 'epoch':
                            library.epoch += 1
                        else:
                            library.provider = LocalFiles(path.parent)
                    finally:
                        released.set()
                    with self.assertRaisesRegex(ValueError, 'Notes Library closed'):
                        await task
                with patch.object(Editor, 'pdf_data', classify):
                    self.app.loop.run_until_complete(scenario())


class PdfPrewarmOwnershipTests(unittest.IsolatedAsyncioTestCase):
    async def test_document_replacement_during_resource_check_cannot_finish_prewarm(self):
        started, released = threading.Event(), threading.Event()
        main_thread = threading.get_ident()
        def check():
            self.assertNotEqual(threading.get_ident(), main_thread)
            started.set()
            if not released.wait(3):
                raise TimeoutError('fixture validation was not released')
        resource = NS(check=check)
        document = NS(resource=resource)
        editor = NS(notebook=NS(content={'fileType':'pdf'}), pdf_data=lambda:None)
        panel = NS(editor=editor, document=document, closed=False, app=NS(active_host=True))
        task = asyncio.create_task(NotebookPanel.prewarm_pdf(panel))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            panel.document = NS(resource=resource)
        finally:
            released.set()
        self.assertFalse(await task)

    async def test_closed_replaced_or_inactive_editor_cannot_finish_prewarm(self):
        for field in ('closed', 'editor', 'active_host'):
            started, released = threading.Event(), threading.Event()
            def classify():
                started.set()
                if not released.wait(3):
                    raise TimeoutError('fixture classification was not released')
            editor = NS(notebook=NS(content={'fileType':'pdf'}), pdf_data=classify)
            panel = NS(editor=editor, closed=False, app=NS(active_host=True))
            task = asyncio.create_task(NotebookPanel.prewarm_pdf(panel))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                if field == 'active_host':
                    panel.app.active_host = False
                else:
                    setattr(panel, field, True if field == 'closed' else object())
            finally:
                released.set()
            self.assertFalse(await task)
