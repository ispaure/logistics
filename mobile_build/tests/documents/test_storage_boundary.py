"""Shared mobile document dispatch and native privacy choices."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from features.notebooks.notebook import Notebook, MAX_ARCHIVE
from services.documents.storage import DocumentResource
from mobile_build.tests.documents import test_notebook_storage as storage_fixture


class MobileStorageBoundaryTests(unittest.TestCase):
    setUp = storage_fixture.NotebookStorageTests.setUp
    tearDown = storage_fixture.NotebookStorageTests.tearDown
    run_async = storage_fixture.NotebookStorageTests.run_async

    def test_workspace_drawer_opens_encrypted_notebook_through_shared_host(self):
        from mobile.file_drawer import FileDrawer
        DocumentResource.publish(self.provider, 'Drawer.rmdoc', Notebook.new('Drawer notebook').to_bytes(), max_bytes=MAX_ARCHIVE)
        drawer = SimpleNamespace(provider=self.provider, app=self.app, destination='files',
            provider_client=self.client, provider_generation=self.client.generation,
            status=SimpleNamespace(value=''), navigation=SimpleNamespace(wide=True, render=Mock()))
        self.assertTrue(self.run_async(FileDrawer.open_file(drawer, {'path': 'Drawer.rmdoc'})), drawer.status.value)
        self.assertEqual(self.app.notebook_panel.editor.notebook.name, 'Drawer notebook')
        self.assertTrue(self.app.notebook_panel.session.transient)

    def test_unsupported_private_markdown_backend_refuses_persistent_fallback(self):
        from services.documents.mobile_views import markdown_webview
        with patch('commonUtils.ui.native.private_webview.private_webview_supported', return_value=False), \
                patch('services.documents.mobile_views.document_webview') as factory:
            with self.assertRaisesRegex(ValueError, 'Source mode'):
                markdown_webview(private=True)
        factory.assert_not_called()
