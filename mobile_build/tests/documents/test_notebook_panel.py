"""Installed mobile destination, local recovery and shared drawing command bridge."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from mobile.app import LogisticsMobile
from mobile.navigation import DESTINATIONS
from features.notebooks.notebook import Notebook
from features.notebooks.workspace import Editor


class NotebookPanelTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        LogisticsMobile.storage_root=Path(self.temp.name)
        self.addCleanup(setattr,LogisticsMobile,'storage_root',None)
        self.app=LogisticsMobile('Logistics','io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)

    def test_destination_order_and_retained_workspace(self):
        app=self.app
        self.assertEqual(DESTINATIONS[:3],('home','notebooks','files'))
        app.select_destination('notebooks')
        app.native_host.activate('notebooks')
        panel=app.notebook_panel
        self.assertIn(panel.view,app.routes.roots['notebooks'].children)
        app.loop.run_until_complete(panel.new())
        book=panel.editor.notebook
        panel.editor.apply(dict(op='stroke',points=[[100,100,.4],[130,140,.7]],tool=12,width=3))
        app.select_destination('home')
        app.native_host.activate('home')
        app.select_destination('notebooks')
        self.assertIs(app.notebook_panel.editor.notebook,book)
        restored=panel.repository.open(panel.key)
        self.assertEqual(len(restored.page(0).strokes),1)
        self.assertEqual(restored.page(0).strokes[0].tool,12)

    def test_workspace_opens_a_notebook_copy_without_changing_source(self):
        from unittest.mock import patch
        from commonUtils.runtime.resources.local import LocalFiles
        app = self.app
        owner = app.read_managed_file.__self__
        path = Path(self.temp.name) / 'from-workspaces.rmdoc'
        path.write_bytes(Notebook.new('From Workspaces').to_bytes())
        original = path.read_bytes()
        app.loop.run_until_complete(app.show_files())
        with patch.object(owner, 'selected_file', return_value=(LocalFiles(path.parent), path.name)):
            result = app.loop.run_until_complete(owner.read_managed_file())
        self.assertTrue(result)
        self.assertEqual(app.native_host.state.destination, 'notebooks')
        self.assertEqual(app.notebook_panel.editor.notebook.name, 'From Workspaces')
        app.notebook_panel.editor.apply(dict(op='add-page'))
        self.assertEqual(path.read_bytes(), original)

    def test_workspace_rmdoc_open_honors_navigation_veto(self):
        from unittest.mock import patch
        from commonUtils.runtime.resources.local import LocalFiles
        app = self.app
        owner = app.read_managed_file.__self__
        path = Path(self.temp.name) / 'veto.rmdoc'
        path.write_bytes(Notebook.new().to_bytes())
        provider = LocalFiles(path.parent)
        # Build ordinary local controls before supplying an explicit selection.
        app.loop.run_until_complete(app.show_files())
        with patch.object(owner, 'selected_file', return_value=(provider, path.name)), \
                patch.object(app, 'select_destination', return_value=False):
            result = app.loop.run_until_complete(owner.read_managed_file())
        self.assertFalse(result)
        self.assertFalse(hasattr(app, 'notebook_panel'))

    def test_copy_and_reopen_synthetic_import(self):
        app=self.app
        app.select_destination('notebooks')
        panel=app.notebook_panel
        path=Path(self.temp.name)/'sample.rmdoc'
        path.write_bytes(Notebook.new('Original').to_bytes())
        original=path.read_bytes()
        app.loop.run_until_complete(panel.open_path(path))
        panel.editor.apply(dict(op='add-page'))
        self.assertEqual(path.read_bytes(),original)
        self.assertEqual(len(panel.repository.open(panel.key).pages),2)

    def test_invalid_workspace_import_reports_failure(self):
        from unittest.mock import patch
        from commonUtils.runtime.resources.local import LocalFiles
        path = Path(self.temp.name) / 'damaged.rmdoc'
        path.write_bytes(b'not a ZIP')
        owner = self.app.read_managed_file.__self__
        self.app.loop.run_until_complete(self.app.show_files())
        with patch.object(owner, 'selected_file', return_value=(LocalFiles(path.parent), path.name)):
            result = self.app.loop.run_until_complete(owner.read_managed_file())
        self.assertFalse(result)
        self.assertIn('Invalid RMDOC', self.app.notebook_panel.status.text)

    def test_retired_canvas_and_busy_commands_do_not_consume_current_sequence(self):
        import json
        from urllib.parse import quote
        self.app.select_destination('notebooks')
        panel = self.app.notebook_panel
        self.app.loop.run_until_complete(panel.new())
        old = panel.web
        self.app.loop.run_until_complete(panel.new())
        self.assertIsNone(old.on_navigation_starting._raw)
        command = panel.bridge.url + '?command=' + quote(json.dumps(dict(sequence=1,action=dict(op='rename',name='Current'))))
        panel.navigate(old, command)
        self.assertEqual(panel.bridge.sequence, 0)
        panel.busy = True
        panel.navigate(panel.web, command)
        self.assertEqual(panel.bridge.sequence, 0)
        panel.busy = False
        panel.navigate(panel.web, command)
        self.assertTrue(panel.busy)
        self.app.loop.run_until_complete(asyncio.sleep(.1))
        self.assertEqual(panel.editor.notebook.name, 'Current')
        self.assertFalse(panel.busy)

    def test_disposal_during_import_cannot_reopen_canvas(self):
        from threading import Event
        self.app.select_destination('notebooks')
        panel = self.app.notebook_panel
        started, released = Event(), Event()
        def read():
            started.set()
            if not released.wait(5):
                raise TimeoutError('fixture was not released')
            return Notebook.new('Pending')
        async def scenario():
            loading = asyncio.create_task(panel.load(read))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                self.assertFalse(await panel.new())
                panel.dispose()
            finally:
                released.set()
            self.assertFalse(await loading)
            self.assertIsNone(panel.web)
            self.assertFalse(panel.busy)
        self.app.loop.run_until_complete(scenario())

    def test_failed_canvas_acknowledgement_offers_reopen_of_saved_content(self):
        from unittest.mock import AsyncMock, patch
        self.app.select_destination('notebooks')
        panel = self.app.notebook_panel
        self.app.loop.run_until_complete(panel.new())
        key = panel.key
        with patch.object(panel.web, 'evaluate_javascript', AsyncMock(side_effect=RuntimeError('view unavailable'))):
            self.app.loop.run_until_complete(panel.perform(dict(op='rename', name='Saved content')))
        self.assertIsNone(panel.web)
        self.assertIn('Reopen it to resume', panel.status.text)
        self.assertEqual(panel.repository.open(key).name, 'Saved content')


if __name__=='__main__':
    unittest.main()
