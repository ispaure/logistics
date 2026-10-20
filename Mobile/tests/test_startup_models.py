"""Startup prepares durable models off-thread and defers inactive native views."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import get_ident
from unittest import TestCase
from unittest.mock import patch

from logisticsmobile.app import LogisticsMobile
from logisticsmobile.documents import DocumentStore
from logisticsmobile.preferences import Preferences
from logisticsmobile.workspace import Workspace
from logisticsmobile.startup import load_startup_models


class AsyncStartupApp(LogisticsMobile):
    def startup(self):
        from logisticsmobile.appearance import install_appearance
        from logisticsmobile.startup import begin_startup
        install_appearance(self)
        self._startup_in_progress = self._async_startup = True
        begin_startup(self)


class StartupModelTests(TestCase):
    def test_async_startup_defers_document_view_and_keeps_recovery_metadata(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            preferences = Preferences(root)
            preferences.save(clear_unmodified_documents_on_restart='false')
            store = DocumentStore(root / 'Documents')
            doc = store.create('Recovered.txt', b'Baseline')
            doc.text = 'Unsaved synthetic draft'
            store.checkpoint(doc)
            workspace = Workspace(root)
            workspace.open('managed-text', doc.id, 'text', doc.name)
            workspace.save()
            LogisticsMobile.storage_root = root
            threads = []
            original = load_startup_models
            def load(*args):
                threads.append(get_ident())
                return original(*args)
            app = None
            try:
                with patch('logisticsmobile.startup.load_startup_models', side_effect=load):
                    app = AsyncStartupApp('Logistics', 'io.github.ispaure.logisticsmobile')
                    self.assertTrue(app.loop.run_until_complete(app.startup_task))
                self.assertNotEqual(threads, [get_ident()])
                self.assertIsNone(app.current)
                self.assertEqual(app.text_views, {})
                self.assertFalse(hasattr(app, 'folder_list'))
                self.assertFalse(app.routes.roots['documents'].children)
                self.assertEqual(app._startup_display[doc.id]['name'], 'Recovered.txt')
                self.assertTrue(app._startup_display[doc.id]['modified'])
                app.show_documents(edit=True)
                self.assertEqual(app.current.id, doc.id)
                self.assertEqual(app.current.text, 'Unsaved synthetic draft')
            finally:
                if app is not None:
                    background = getattr(app, 'cloud_startup_task', None)
                    if background is not None:
                        background.cancel()
                    app.main_window.close()
                    app.loop.run_until_complete(asyncio.sleep(0))
                    app.loop.close()
                LogisticsMobile.storage_root = None
