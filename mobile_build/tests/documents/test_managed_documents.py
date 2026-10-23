"""Picker completions remain attached to their originating document lifetime."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from commonUtils.runtime.resources.documents import LocalDocuments
from mobile.app import LogisticsMobile


class ManagedDocumentTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        LogisticsMobile.storage_root = self.root
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.app.show_documents()

    def test_import_after_switch_retains_new_draft_and_publishes_separate_session(self):
        app = self.app
        origin = app.editor_view
        source = self.root / 'import.txt'
        source.write_bytes(b'Imported copy')

        async def exercise():
            selected = app.loop.create_future()
            async def pick(host):
                return await selected
            with patch('mobile.pickers.pick_document', new=pick):
                task = asyncio.create_task(app.import_document(origin=origin))
                await asyncio.sleep(0)
                self.assertFalse(origin.import_button.enabled)
                app.new_document(name='Current.txt', content='Keep this draft')
                current = app.current
                active = app.workspace.active
                selected.set_result((LocalDocuments(), source))
                await task
            self.assertIs(app.current, current)
            self.assertEqual(app.editor.value, 'Keep this draft')
            self.assertEqual(app.workspace.active, active)
            imported = [view for view in app.text_views.values()
                        if view.document.name == 'import.txt']
            self.assertEqual(len(imported), 1)
            self.assertEqual(imported[0].document.text, 'Imported copy')
            self.assertIn('Open documents', origin.status.text)
            self.assertTrue(origin.import_button.enabled)

        app.loop.run_until_complete(exercise())

    def test_export_after_origin_closes_does_not_publish_to_new_draft(self):
        app = self.app
        origin = app.editor_view

        async def exercise():
            exported = app.loop.create_future()
            async def export(host, name, data):
                return await exported
            with patch('mobile.pickers.export_document', new=export):
                task = asyncio.create_task(app.export_document(origin=origin))
                await asyncio.sleep(0)
                self.assertFalse(origin.export_button.enabled)
                app.new_document(name='Current.txt', content='Still editing')
                current = app.current
                app.workspace.close(origin.session.id, guard=lambda session: True)
                origin_status = origin.status.text
                current_status = app.status.text
                exported.set_result(True)
                await task
            self.assertIs(app.current, current)
            self.assertEqual(app.status.text, current_status)
            self.assertEqual(origin.status.text, origin_status)
            self.assertEqual(app.editor.value, 'Still editing')
            self.assertTrue(origin.export_button.enabled)

        app.loop.run_until_complete(exercise())
