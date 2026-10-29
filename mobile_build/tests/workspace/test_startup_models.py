"""Startup prepares durable models off-thread and defers inactive native views."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import get_ident
from unittest import TestCase
from unittest.mock import patch

from mobile.app import LogisticsMobile
from mobile.documents import DocumentStore
from mobile.preferences import Preferences
from mobile.workspace import Workspace
from mobile.startup import load_startup_models


class AsyncStartupApp(LogisticsMobile):
    def startup(self):
        from mobile.appearance import install_appearance
        from mobile.startup import begin_startup
        install_appearance(self)
        self._startup_in_progress = self._async_startup = True
        begin_startup(self)


class StartupModelTests(TestCase):
    def test_restart_cleanup_preserves_only_active_saved_document_when_restore_enabled(self):
        for restore in ('true', 'false'):
            with self.subTest(restore=restore), TemporaryDirectory() as directory:
                root = Path(directory)
                Preferences(root).save(restore_last_document=restore)
                store = DocumentStore(root / 'Documents')
                clean = store.create('Other.txt', b'Saved')
                active = store.create('Active.txt', b'Saved')
                workspace = Workspace(root)
                workspace.open('managed-text', clean.id, 'text')
                workspace.open('managed-text', active.id, 'text')
                workspace.save()
                models = load_startup_models(root, root)
                resources = {session.resource for session in models['workspace'].sessions.values()}
                self.assertEqual(resources, {active.id} if restore == 'true' else set())
                self.assertEqual(store.open(clean.id).text, 'Saved')

    def test_native_startup_reopens_local_epub_before_revealing_workspace(self):
        from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            restored = None
            try:
                fixtures = root / 'fixtures'
                fixtures.mkdir()
                epub, _ = make_books(fixtures)
                self.assertTrue(app.loop.run_until_complete(app.open_download(path=epub)))
                app.loop.run_until_complete(app.next_book_page())
                selected = app.workspace.active
                app.checkpoint()
                restored = AsyncStartupApp('Logistics', 'io.github.ispaure.logisticsmobile')
                self.assertTrue(restored.loop.run_until_complete(restored.startup_task))
                self.assertEqual(restored.native_host.state.destination, 'documents')
                self.assertEqual(restored.workspace.active, selected)
                self.assertIsNotNone(restored.readers.active.book_reader)
                self.assertEqual(restored.readers.active.book_record['position'], 1)
            finally:
                hosts = [app, *([restored] if restored is not None else [])]
                for host in hosts:
                    background = getattr(host, 'cloud_startup_task', None)
                    if background is not None:
                        background.cancel()
                    host.main_window.close()
                for loop in {host.loop for host in hosts}:
                    loop.run_until_complete(asyncio.sleep(0))
                    loop.close()

    def test_async_startup_opens_active_document_and_keeps_recovery_metadata(self):
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
                with patch('mobile.startup.load_startup_models', side_effect=load):
                    app = AsyncStartupApp('Logistics', 'io.github.ispaure.logisticsmobile')
                    self.assertTrue(app.loop.run_until_complete(app.startup_task))
                self.assertNotEqual(threads, [get_ident()])
                self.assertEqual(app.current.id, doc.id)
                self.assertEqual(app.native_host.state.destination, 'documents')
                self.assertFalse(hasattr(app, 'folder_list'))
                self.assertEqual(app._startup_display[doc.id]['name'], 'Recovered.txt')
                self.assertTrue(app._startup_display[doc.id]['modified'])
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
