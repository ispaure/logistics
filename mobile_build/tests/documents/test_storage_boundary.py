"""Shared mobile document dispatch and native privacy choices."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import toga

from features.notebooks.notebook import Notebook, MAX_ARCHIVE
from mobile.app import LogisticsMobile
from mobile_build.tests.support.app import create_app
from mobile_build.tests.support.notebooks import create_notebook, create_storage_notebook_app
from services.documents import mobile_views
from services.documents.storage import DocumentResource


class MobileStorageBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.app, self.client, self.provider = create_storage_notebook_app(self)

    def test_workspace_drawer_opens_encrypted_notebook_through_shared_host(self):
        from mobile.file_drawer import FileDrawer
        DocumentResource.publish(self.provider, 'Drawer.rmdoc', Notebook.new('Drawer notebook').to_bytes(), max_bytes=MAX_ARCHIVE)
        drawer = SimpleNamespace(provider=self.provider, app=self.app, destination='files',
            provider_client=self.client, provider_generation=self.client.generation,
            status=SimpleNamespace(value=''), navigation=SimpleNamespace(wide=True, render=Mock()))
        self.assertTrue(self.app.loop.run_until_complete(FileDrawer.open_file(drawer, {'path': 'Drawer.rmdoc'})), drawer.status.value)
        self.assertEqual(self.app.notebook_panel.editor.notebook.name, 'Drawer notebook')
        self.assertTrue(self.app.notebook_panel.session.transient)

    def test_unsupported_private_markdown_backend_refuses_persistent_fallback(self):
        from services.documents.mobile_views import markdown_webview
        with patch('commonUtils.ui.native.private_webview.private_webview_supported', return_value=False), \
                patch('services.documents.mobile_views.document_webview') as factory:
            with self.assertRaisesRegex(ValueError, 'Source mode'):
                markdown_webview(private=True)
        factory.assert_not_called()


class NotebookFixtureCleanupTests(unittest.TestCase):
    def test_failed_setup_disposes_notebook_and_restores_app_loop_and_root(self):
        outer_app = create_app(self)
        outer_loop = asyncio.get_event_loop()
        outer_root = LogisticsMobile.storage_root
        original_canvas = mobile_views.document_webview

        class FailingSetup(unittest.TestCase):
            def setUp(self):
                self.app, self.client, self.provider = create_storage_notebook_app(self)
                self.root = self.app.storage_root
                self.panel = create_notebook(self, private=False)
                raise RuntimeError('synthetic setup failure')

            def runTest(self):
                self.fail('failed setup must prevent the test body from running')

        case = FailingSetup()
        result = case.run()
        self.assertEqual(result.failures, [])
        self.assertEqual(len(result.errors), 1, result.errors)
        self.assertIn('RuntimeError: synthetic setup failure', result.errors[0][1])
        self.assertTrue(case.panel.closed)
        self.assertTrue(case.app.loop.is_closed())
        self.assertFalse(case.root.exists())
        self.assertIs(toga.App.app, outer_app)
        self.assertIs(asyncio.get_event_loop(), outer_loop)
        self.assertIs(LogisticsMobile.storage_root, outer_root)
        self.assertIs(mobile_views.document_webview, original_canvas)
