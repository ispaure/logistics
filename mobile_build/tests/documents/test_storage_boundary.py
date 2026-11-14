"""Shared mobile document dispatch and native privacy choices."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from shutil import rmtree
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import toga
from toga_dummy.utils import EventLog

from features.notebooks.notebook import Notebook, MAX_ARCHIVE
from mobile.app import LogisticsMobile
from mobile.obsidian import open_vault
from mobile_build.tests.support.app import create_app
from mobile_build.tests.support.notebooks import create_notebook, create_storage_notebook_app
from mobile_build.tests.support.notes import set_up_vault
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
        self.assertTrue(case.provider.closed)
        self.assertTrue(case.panel.closed)
        self.assertTrue(case.app.loop.is_closed())
        self.assertFalse(case.root.exists())
        self.assertIs(toga.App.app, outer_app)
        self.assertIs(asyncio.get_event_loop(), outer_loop)
        self.assertIs(LogisticsMobile.storage_root, outer_root)
        self.assertIs(mobile_views.document_webview, original_canvas)


class NotesFixtureCleanupTests(unittest.TestCase):
    def test_cancelled_setup_retires_work_and_keeps_nested_fixtures_independent(self):
        outer = unittest.TestCase()
        self.addCleanup(outer.doCleanups)
        set_up_vault(outer)
        (outer.vault / 'Home.md').write_text('outer draft', encoding='utf-8')
        outer_window = outer.app.main_window
        outer_events = EventLog._log
        outer_factory = mobile_views.document_webview

        class CancelledSetup(unittest.TestCase):
            def setUp(case):
                set_up_vault(case)
                self.assertNotEqual(case.root, outer.root)
                self.assertNotEqual(EventLog._log, outer_events)
                self.assertIn('# Home', (case.vault / 'Home.md').read_text(encoding='utf-8'))
                case.window = case.app.main_window
                case.index = case.app._directory_index_host
                case.index.runner.start()
                case.worker_finished = Event()

                async def exercise():
                    case.browser = await open_vault(case.app, case.provider, 'Vault', 'files')
                    started = asyncio.Event()

                    async def search():
                        try:
                            started.set()
                            await asyncio.Future()
                        finally:
                            self.assertTrue(case.root.exists())
                            case.worker_finished.set()

                    case.task = asyncio.create_task(search())
                    await started.wait()
                    raise asyncio.CancelledError('synthetic cancellation during setup')

                case.app.loop.run_until_complete(exercise())

            def runTest(case):
                self.fail('cancelled setup must prevent the test body from running')

        case = CancelledSetup()
        result = case.run()
        self.assertEqual(result.failures, [])
        self.assertEqual(len(result.errors), 1, result.errors)
        self.assertIn('CancelledError: synthetic cancellation during setup', result.errors[0][1])
        self.assertTrue(case.browser.cancelled.is_set())
        self.assertTrue(case.task.cancelled())
        self.assertTrue(case.worker_finished.is_set())
        self.assertTrue(case.window.closed)
        self.assertFalse(case.app.windows)
        self.assertTrue(case.app.loop.is_closed())
        self.assertTrue(case.index.closed)
        self.assertFalse(case.index.runner.worker.is_alive())
        self.assertFalse(case.root.exists())
        self.assertIs(toga.App.app, outer.app)
        self.assertIs(asyncio.get_event_loop(), outer.app.loop)
        self.assertIs(LogisticsMobile.storage_root, outer.app.storage_root)
        self.assertIs(EventLog._log, outer_events)
        self.assertIs(mobile_views.document_webview, outer_factory)
        self.assertFalse(outer_window.closed)
        self.assertEqual((outer.vault / 'Home.md').read_text(encoding='utf-8'), 'outer draft')

    def test_disposal_failure_retains_evidence_but_still_closes_app(self):
        case = unittest.TestCase()
        set_up_vault(case)
        self.addCleanup(rmtree, case.root, ignore_errors=True)
        self.addCleanup(case.doCleanups)
        window = case.app.main_window
        owner = case.app.loop.run_until_complete(open_vault(case.app, case.provider, 'Vault', 'files'))
        error = RuntimeError('synthetic browser disposal failure')

        def fail_after_disposal():
            dispose()
            raise error

        dispose = owner.dispose
        with patch.object(owner, 'dispose', side_effect=fail_after_disposal):
            with self.assertLogs('mobile.application_lifecycle', level='ERROR'):
                result = case.doCleanups()
        self.assertFalse(result)
        self.assertIn(str(case.root), ' '.join(error.__notes__))
        self.assertTrue((case.vault / 'Home.md').is_file())
        self.assertTrue(owner.cancelled.is_set())
        self.assertTrue(case.app.loop.is_closed())
        self.assertTrue(window.closed)
