"""Mobile notebook position through real Home and Local host routes."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import AsyncMock

from commonUtils.testing.stages import TestStage
from commonUtils.runtime.resources.local import LocalFiles
from features.notebooks.notebook import Notebook
from features.notebooks.mobile.brush_presets import PREFERENCE, change_preset, read_presets
from mobile_build.tests.support.app import mobile_app
from Python.tests.notebooks.image_fixtures import paste_action
from mobile_build.tests.support.notebooks import create_storage_notebook_app
from services.documents.mobile_storage import open_provider_document

TEST_STAGE = TestStage.REGRESSION


class NotebookPageProgressTests(unittest.TestCase):
    def test_legacy_brush_slots_keep_their_identity_when_edited_to_match(self):
        app, _, _ = create_storage_notebook_app(self)
        app.preferences.save(**{PREFERENCE: '[[17,6,2],[17,7,1]]'})
        first, second = read_presets(app.preferences.values[PREFERENCE])
        updated = change_preset(app.preferences, {
            'op': 'update-brush-preset', 'id': first['id'], 'preset': second['brush'],
        })
        self.assertEqual(updated, [dict(first, brush=second['brush']), second])
        self.assertEqual(read_presets(app.preferences.reload()[PREFERENCE]), updated)
        self.assertEqual(change_preset(app.preferences, {
            'op': 'remove-brush-preset', 'id': first['id'],
        }), [second])

    def test_pasted_cutouts_and_page_recover_without_saving_the_source(self):
        app, _, _ = create_storage_notebook_app(self)
        run = app.loop.run_until_complete
        path = app.private_root / 'Cutouts.rmdoc'
        book = Notebook.new('Cutouts')
        book.add_page()
        original = book.to_bytes()
        path.write_bytes(original)

        self.assertTrue(run(app.open_local_document(path, destination='home')))
        panel = app.notebook_panel
        panel.web.evaluate_javascript = AsyncMock(return_value=True)
        run(panel.perform({'op': 'page', 'index': 1}))
        paste = paste_action()
        run(panel.perform(paste))
        run(panel.perform(paste))
        run(panel.perform({'op': 'page', 'index': 0}))
        run(panel.perform({'op': 'page', 'index': 1}))
        script = panel.web.evaluate_javascript.call_args.args[0]
        self.assertEqual(script.count(paste['src']), 1)
        self.assertEqual(path.read_bytes(), original)

        # Start a fresh process while the original editor is still open.
        result = subprocess.run([sys.executable, __file__, str(app.storage_root), str(path)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(state, dict(page_id=book.pages[1].id, images=[paste['src']] * 2, dirty=True))
        self.assertEqual(path.read_bytes(), original)

    def test_home_and_local_reopen_visible_page_and_brush_settings_without_writing_ink(self):
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
        run(panel.perform({'op': 'brush-color', 'tool': 15, 'color': 6}))
        run(panel.perform({'op': 'brush-intensity', 'tool': 14, 'intensity': 64}))
        run(panel.perform({'op': 'brush-intensity', 'tool': 13, 'intensity': 91}))
        run(panel.perform({'op': 'eraser-kind', 'kind': 'whole'}))
        self.assertFalse(panel.state()['snap_to_text'])
        run(panel.perform({'op': 'snap-to-text', 'enabled': True}))
        run(panel.perform({'op': 'working-brush', 'brush': [17, 6, 3]}))
        run(panel.perform({'op': 'page', 'index': 2}))
        run(panel.perform({'op': 'brush-color', 'tool': 18, 'color': -1}))
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
        self.assertEqual(reopened.state()['brush_colors'], {15: 6, 18: -1})
        self.assertEqual(reopened.state()['brush_intensities'], {14: 64, 13: 91})
        self.assertEqual(reopened.state()['eraser_kind'], 'whole')
        self.assertTrue(reopened.state()['snap_to_text'])
        self.assertEqual(reopened.state()['working_brush'], [17, 6, 3])
        self.assertFalse(reopened.document.dirty)
        self.assertTrue(app.close_session(reopened.session.id))

        self.assertTrue(run(app.open_local_document(path, destination='home')))
        self.assertEqual(app.notebook_panel.state()['page_id'], selected)
        self.assertEqual(app.notebook_panel.state()['eraser_kind'], 'whole')
        self.assertEqual(app.notebook_panel.state()['brush_colors'], {15: 6, 18: -1})
        self.assertEqual(app.notebook_panel.state()['brush_intensities'], {14: 64, 13: 91})
        self.assertEqual(path.read_bytes(), original)

    def test_cutout_can_be_pasted_repeatedly_after_opening_another_notebook(self):
        app, _, _ = create_storage_notebook_app(self)
        run = app.loop.run_until_complete
        source, target = (app.private_root / name for name in ('Source.rmdoc', 'Target.rmdoc'))
        for path in (source, target):
            path.write_bytes(Notebook.new(path.stem).to_bytes())
        self.assertTrue(run(app.open_local_document(source, destination='home')))
        panel = app.notebook_panel
        panel.web.evaluate_javascript = AsyncMock(return_value=True)
        run(panel.perform({'op': 'copy-cutout', 'src': paste_action()['src'], 'width': 100, 'height': 100}))
        self.assertFalse(panel.state()['cutout_clipboard']['incoming'])
        self.assertTrue(app.close_session(panel.session.id))
        self.assertTrue(run(app.open_local_document(target, destination='home')))
        panel = app.notebook_panel
        panel.web.evaluate_javascript = AsyncMock(return_value=True)
        self.assertTrue(panel.state()['cutout_clipboard']['incoming'])
        paste = dict(op='paste-cutout', layer=panel.editor.notebook.page(0).layers[0][0],
                     corners=paste_action()['corners'], clipboard_id=panel.state()['cutout_clipboard']['id'])
        run(panel.perform(paste))
        run(panel.perform(paste))
        self.assertEqual(len(panel.state()['images']), 2)
        run(panel.perform({'op': 'clear-cutout'}))
        self.assertIsNone(panel.state()['cutout_clipboard'])


if __name__ == '__main__':
    with mobile_app(root=Path(sys.argv[1])) as app:
        restore = getattr(app, 'startup_document_task', None)
        if restore is not None:
            opened = app.loop.run_until_complete(restore)
        else:
            opened = app.loop.run_until_complete(app.open_local_document(Path(sys.argv[2]), destination='home'))
        if not opened:
            raise RuntimeError('Notebook recovery did not open')
        panel = app.notebook_panel
        try:
            state = panel.state()
            print(json.dumps(dict(page_id=state['page_id'], images=[image['src'] for image in state['images']],
                                  dirty=panel.document.dirty)))
        finally:
            panel.dispose()
