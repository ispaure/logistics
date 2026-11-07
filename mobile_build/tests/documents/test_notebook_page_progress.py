"""Mobile notebook position through real Home and Local host routes."""

import unittest
from unittest.mock import AsyncMock

from commonUtils.testing.stages import TestStage
from commonUtils.runtime.resources.local import LocalFiles
from features.notebooks.notebook import Notebook
from mobile_build.tests.support.notebooks import create_storage_notebook_app
from services.documents.mobile_storage import open_provider_document

TEST_STAGE = TestStage.REGRESSION


class NotebookPageProgressTests(unittest.TestCase):
    def test_home_and_local_reopen_visible_page_without_writing_ink(self):
        app, _, _ = create_storage_notebook_app(self)
        run = app.loop.run_until_complete
        folder = app.private_root / 'Downloads' / 'Nested'
        folder.mkdir(parents=True)
        path = folder / 'Sketch.rmdoc'
        book = Notebook.new('Sketch')
        book.add_page()
        book.add_page()
        original = book.to_bytes()
        path.write_bytes(original)

        self.assertTrue(run(app.open_local_document(path, destination='home')))
        panel = app.notebook_panel
        panel.web.evaluate_javascript = AsyncMock(return_value=True)
        run(panel.perform({'op': 'page', 'index': 2}))
        selected = panel.state()['page_id']
        self.assertEqual(selected, book.pages[2].id)
        self.assertFalse(panel.document.dirty)
        self.assertFalse(panel.editor.undo)
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(app.close_session(panel.session.id))

        provider = LocalFiles(folder.parent)
        self.assertTrue(run(open_provider_document(app, provider, 'Nested/Sketch.rmdoc', destination='files')))
        reopened = app.notebook_panel
        self.assertIsNot(reopened, panel)
        self.assertEqual(reopened.state()['page_id'], selected)
        self.assertFalse(reopened.document.dirty)
        self.assertTrue(app.close_session(reopened.session.id))

        self.assertTrue(run(app.open_local_document(path, destination='home')))
        self.assertEqual(app.notebook_panel.state()['page_id'], selected)
        self.assertEqual(path.read_bytes(), original)
