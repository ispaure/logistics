"""Recovery identity, malformed-command rollback and canvas lifetime contracts."""
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import quote

from features.notebooks.bridge import Bridge, RetiredCanvas
from features.notebooks.editor import Editor
from features.notebooks.notebook import Notebook
from features.notebooks.protocol import document_state, stroke_script, update_script
from features.notebooks.recovery import Repository
from features.notebooks.storage import NotebookDocument


class NotebookProtocolTests(unittest.TestCase):
    def test_malformed_actions_leave_ink_history_and_checkpoint_unchanged(self):
        with TemporaryDirectory() as directory:
            repo = Repository(directory)
            book = Notebook.new()
            key = repo.create(book)
            editor = Editor(book, lambda value: repo.save(key, value))
            manifest = Path(directory, key, 'state.json')
            previous = manifest.read_bytes()
            for action in ({'op': 'page', 'index': True}, {'op': 'rename', 'name': []},
                           {'op': 'layer-visible', 'layer': 'a', 'visible': 'false'},
                           {'op': 'erase', 'ids': [1]}, {'op': 'unknown'},
                           {'op': 'transform', 'ids': [], 'dx': float('nan'), 'dy': 0}):
                with self.subTest(action=action), self.assertRaises(ValueError):
                    editor.apply(action)
                self.assertEqual(manifest.read_bytes(), previous)
                self.assertEqual(editor.undo, [])
                self.assertEqual(book.page(0).strokes, [])

    def test_independent_recovery_identities_keep_independent_revisions(self):
        with TemporaryDirectory() as directory:
            repo = Repository(directory)
            book = Notebook.new()
            first = repo.create(book)
            stale = repo.open(first)
            second = repo.create(book)
            editor = Editor(book, lambda value: repo.save(first, value))
            editor.apply({'op': 'rename', 'name': 'Edited'})
            repo.save(second, book)
            self.assertEqual(repo.open(first).name, 'Edited')
            self.assertEqual(repo.open(second).name, 'Edited')
            with self.assertRaisesRegex(ValueError, 'another window'):
                repo.save(first, stale)
            self.assertNotIn('_recovery_revision', vars(book))

    def test_source_reload_adopts_observed_revision_without_bypassing_conflicts(self):
        with TemporaryDirectory() as directory:
            repo = Repository(directory)
            key = repo.create(Notebook.new())
            observed = repo.open(key)
            replacement = Notebook.new('Reloaded source')
            repo.adopt(key, replacement, observed)
            repo.save(key, replacement)
            another = Notebook.new('Stale reload')
            repo.adopt(key, another, observed)
            with self.assertRaisesRegex(ValueError, 'another window'):
                repo.save(key, another)

    def test_invalid_action_can_be_acknowledged_before_the_next_command(self):
        bridge = Bridge()
        editor = Editor(Notebook.new())
        def command(sequence, action):
            return bridge.command(bridge.url + '?command=' + quote(json.dumps(
                {'sequence': sequence, 'action': action})))
        action = command(1, {'op': 'page', 'index': 'bad'})
        with self.assertRaises(ValueError) as error:
            editor.apply(action)
        self.assertIn(str(error.exception), update_script(editor.state(), str(error.exception)))
        editor.apply(command(2, {'op': 'rename', 'name': 'Still editable'}))
        self.assertEqual(editor.notebook.name, 'Still editable')
        bridge.retire()
        self.assertIsNone(command(3, {'op': 'delete-page'}))

    def test_stroke_response_and_full_response_share_unsaved_draft_status(self):
        document = NotebookDocument(Notebook.new())
        editor = Editor(document.book, document.checkpoint)
        self.assertEqual(document_state(editor, document)['save_status'], 'Not saved yet')
        editor.apply({'op': 'stroke', 'points': [[20, 30, .5]]})
        self.assertEqual(document_state(editor, document)['save_status'], 'Unsaved changes')
        self.assertIn('Unsaved changes', stroke_script(editor, document))
        self.assertNotIn('strokes', stroke_script(editor, document))

    def test_retired_canvas_stops_an_awaited_continuation(self):
        async def run():
            bridge = Bridge()
            async def operation():
                await asyncio.sleep(0)
                bridge.retire()
                return 'completed'
            with self.assertRaises(RetiredCanvas):
                await bridge.wait(operation())
        asyncio.run(run())
