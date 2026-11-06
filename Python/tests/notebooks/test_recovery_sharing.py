"""Checkpoint history retains immutable native ink once, not once per edit."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from features.notebooks.editor import Editor
from features.notebooks.notebook import Notebook
from features.notebooks.recovery import Repository
from features.notebooks._vendor.rmscene import scene_stream as ss


class RecoverySharingTests(unittest.TestCase):
    def test_discard_replaces_recovery_base_with_complete_saved_archive(self):
        from features.notebooks.notebook import MAX_ARCHIVE
        from features.notebooks.storage import NotebookDocument
        from services.documents.storage import local_document_resource

        for replaced in (False, True):
            with self.subTest(replaced=replaced), TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / 'source.rmdoc'
                original = Notebook.new('Saved', template='Logistics Daily planner')
                original.members['opaque/future.bin'] = b'\x01\xffsaved member'
                source.write_bytes(original.to_bytes())
                repository = Repository(root / 'recovery')
                with local_document_resource(source, max_bytes=MAX_ARCHIVE) as resource:
                    document = NotebookDocument(Notebook.read(resource.read()), resource=resource,
                                                recovery=repository)
                    Editor(document.book, document.checkpoint).apply(dict(op='template',
                        name='Logistics Meeting notes', format='pro', visible=True))
                    if replaced:
                        replacement = Notebook.new('Replacement', template='Logistics Restaurant review')
                        replacement.content['fileType'] = 'pdf'
                        replacement.members[replacement.id + '.pdf'] = b'%PDF-opaque embedded source'
                        replacement.members['opaque/future.bin'] = b'\x02\xfereplacement member'
                        replacement.members[f'{replacement.id}/{replacement.pages[0].id}.future'] = b'page sidecar'
                        source.write_bytes(replacement.to_bytes())
                    saved_bytes = source.read_bytes()
                    expected = Notebook.read(saved_bytes)
                    document.discard()
                    recovered = repository.open(document.key)
                    self.assertEqual(recovered.id, expected.id)
                    self.assertEqual(recovered.members, expected.members)
                    self.assertEqual([page.template for page in recovered.pages],
                                     [page.template for page in expected.pages])
                    self.assertEqual(source.read_bytes(), saved_bytes)
                    self.assertFalse(document.dirty)

    def test_discard_base_publication_failures_keep_source_and_draft_retryable(self):
        from unittest.mock import Mock, patch
        from features.notebooks.notebook import MAX_ARCHIVE
        from features.notebooks.storage import NotebookDocument
        from services.documents.storage import local_document_resource

        for failure in ('base', 'manifest', 'binding'):
            with self.subTest(failure=failure), TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / 'source.rmdoc'
                original = Notebook.new('Original', template='Logistics Daily planner')
                original.members['opaque/future.bin'] = b'original opaque member'
                source.write_bytes(original.to_bytes())
                repository = Repository(root / 'recovery')
                changed = Mock()
                with local_document_resource(source, max_bytes=MAX_ARCHIVE) as resource:
                    document = NotebookDocument(Notebook.read(resource.read()), resource=resource,
                                                recovery=repository, changed=changed)
                    editor = Editor(document.book, document.checkpoint)
                    editor.apply(dict(op='template', name='Logistics Meeting notes', format='pro', visible=True))
                    draft = document.book
                    draft_members = dict(draft.members)
                    revision = resource.revision
                    replacement = Notebook.new('Replacement', template='Logistics Restaurant review')
                    replacement.members['opaque/future.bin'] = b'replacement opaque member'
                    source.write_bytes(replacement.to_bytes())
                    saved_bytes = source.read_bytes()
                    manifest = repository.root / document.key / 'state.json'
                    before = manifest.read_bytes()
                    target = {'base': 'features.notebooks.recovery.atomic_write_bytes',
                              'manifest': 'features.notebooks.recovery.atomic_write_json'}
                    failing = (patch(target[failure], side_effect=OSError('Publication unavailable'))
                               if failure != 'binding' else
                               patch.object(document, 'changed', side_effect=OSError('Publication unavailable')))
                    with failing:
                        with self.assertRaisesRegex(OSError, 'Publication unavailable'):
                            document.discard()
                    self.assertTrue(document.dirty)
                    self.assertIs(document.book, draft)
                    self.assertEqual(resource.revision, revision)
                    self.assertEqual(source.read_bytes(), saved_bytes)
                    if failure != 'binding':
                        self.assertEqual(manifest.read_bytes(), before)
                    # Any still-open draft can checkpoint its own complete base
                    # after failure, even if discard already published recovery.
                    editor.apply(dict(op='stroke', points=[[20, 30, .5]]))
                    recovered = repository.open(document.key)
                    self.assertEqual(recovered.id, draft.id)
                    self.assertEqual(recovered.members['opaque/future.bin'], b'original opaque member')
                    for name, data in draft_members.items():
                        if name.endswith(('.template', '.logistics-template.json')):
                            self.assertEqual(recovered.members[name], data)
                    self.assertEqual(len(recovered.page(0).strokes), 1)
                    document.discard()
                    self.assertEqual(repository.open(document.key).members, Notebook.read(saved_bytes).members)
                    self.assertEqual(source.read_bytes(), saved_bytes)
                    self.assertFalse(document.dirty)

    def test_rejected_binding_checkpoint_keeps_recovery_and_editor_aligned(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from features.notebooks.storage import NotebookDocument

        with TemporaryDirectory() as directory:
            book = Notebook.new('Binding failure')
            repository = Repository(Path(directory))
            resource = SimpleNamespace(policy=SimpleNamespace(writable=True), check=Mock())
            changed = Mock(side_effect=OSError('Source binding unavailable'))
            document = NotebookDocument(book, resource=resource, recovery=repository, changed=changed)
            editor = Editor(book, document.checkpoint)
            before = (repository.root / document.key / 'state.json').read_bytes()
            with self.assertRaisesRegex(OSError, 'Source binding unavailable'):
                editor.apply(dict(op='stroke', points=[[20, 30, .5]]))
            self.assertEqual(len(book.page(0).strokes), 0)
            self.assertEqual(len(repository.open(document.key).page(0).strokes), 0)
            self.assertEqual((repository.root / document.key / 'state.json').read_bytes(), before)
            self.assertEqual((editor.undo, editor.redo), ([], []))
            self.assertFalse(document.dirty)
            changed.side_effect = None
            editor.apply(dict(op='stroke', points=[[40, 50, .5]]))
            self.assertEqual(len(book.page(0).strokes), 1)
            self.assertEqual(len(repository.open(document.key).page(0).strokes), 1)
            self.assertEqual(len(editor.undo), 1)
            self.assertTrue(document.dirty)

    def test_source_binding_precedes_recovery_and_failed_recovery_is_retryable(self):
        import json
        from unittest.mock import patch
        from commonUtils.runtime.resources.local import LocalFiles
        from features.notebooks.notebook import MAX_ARCHIVE
        from features.notebooks.storage import NotebookDocument
        from services.documents.storage import DocumentResource
        from services.documents.mobile_storage import notebook_binding, remember_notebook_resource

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.rmdoc'
            source.write_bytes(Notebook.new('Ordinary source').to_bytes())
            original = source.read_bytes()
            provider = LocalFiles(root)
            resource = DocumentResource(provider, source.name, max_bytes=MAX_ARCHIVE)
            self.addCleanup(resource.close)
            book = Notebook.read(resource.read())
            repository = Repository(root / 'recovery')
            document = NotebookDocument(book, resource=resource, recovery=repository,
                                        changed=remember_notebook_resource)
            remember_notebook_resource(document)
            binding = notebook_binding(repository, document.key)
            binding_before = binding.read_bytes()
            manifest = repository.root / document.key / 'state.json'
            manifest_before = manifest.read_bytes()
            editor = Editor(book, document.checkpoint)
            action = dict(op='stroke', points=[[20, 30, .5]])
            with patch('commonUtils.persistence.atomic_write_json', side_effect=OSError('Binding unavailable')):
                with self.assertRaisesRegex(OSError, 'Binding unavailable'):
                    editor.apply(action)
            self.assertEqual(binding.read_bytes(), binding_before)
            self.assertEqual(manifest.read_bytes(), manifest_before)
            self.assertFalse(document.dirty)

            def reject_recovery(*args):
                self.assertTrue(json.loads(binding.read_bytes())['dirty'])
                raise OSError('Recovery unavailable')

            with patch.object(repository, 'save', side_effect=reject_recovery):
                with self.assertRaisesRegex(OSError, 'Recovery unavailable'):
                    editor.apply(action)
            self.assertEqual(manifest.read_bytes(), manifest_before)
            self.assertEqual(len(repository.open(document.key).page(0).strokes), 0)
            self.assertEqual(len(book.page(0).strokes), 0)
            self.assertFalse(document.dirty)
            self.assertEqual((editor.undo, editor.redo), ([], []))
            self.assertEqual(source.read_bytes(), original)
            # The conservative marker selects this still-valid old recovery
            # after a restart; the next accepted edit commits exactly once.
            self.assertTrue(json.loads(binding.read_bytes())['dirty'])
            editor.apply(action)
            self.assertEqual(len(repository.open(document.key).page(0).strokes), 1)
            self.assertEqual(len(editor.undo), 1)
            editor.apply(dict(op='undo'))
            self.assertEqual(len(repository.open(document.key).page(0).strokes), 0)
            editor.apply(dict(op='redo'))
            self.assertEqual(len(repository.open(document.key).page(0).strokes), 1)
            self.assertEqual(source.read_bytes(), original)

    def test_long_history_shares_points_and_survives_undo_redo_and_reopen(self):
        with TemporaryDirectory() as directory:
            book = Notebook.new('Checkpoint sharing')
            for _ in range(3):
                book.add_page()
            repository = Repository(Path(directory))
            key = repository.create(book)
            editor = Editor(book, lambda value: repository.save(key, value))
            for index in range(60):
                editor.apply(dict(op='page', index=index % 4))
                editor.apply(dict(op='stroke', tool=15, color=6, width=2,
                    points=[[100 + j, 200 + index, .2 + .7 * j / 31] for j in range(32)]))
            pages = book.pages + [page for snapshot in editor.undo for page in snapshot[0]]
            strokes = {id(stroke) for page in pages for stroke in page.ink.strokes}
            blocks = {id(block) for page in pages for block in page.ink._blocks
                      if isinstance(block, ss.SceneLineItemBlock) and not block.item.deleted_length}
            self.assertEqual(len(strokes), 60)
            self.assertEqual(len(blocks), 60)
            expected = [book.page(i).to_bytes() for i in range(4)]
            for _ in range(50):
                editor.apply(dict(op='undo'))
            self.assertEqual(sum(len(book.page(i).strokes) for i in range(4)), 10)
            for _ in range(50):
                editor.apply(dict(op='redo'))
            self.assertEqual([book.page(i).to_bytes() for i in range(4)], expected)
            reopened = repository.open(key)
            self.assertEqual([reopened.page(i).to_bytes() for i in range(4)], expected)
            # Moving a shared native stroke must leave the Undo version intact.
            editor.apply(dict(op='page', index=0))
            original = book.page(0).strokes[0]
            original_payload = deepcopy(original.payload())
            editor.apply(dict(op='transform', ids=[original.id], dx=5, dy=7))
            self.assertEqual(original.payload(), original_payload)
            self.assertIsNot(book.page(0).strokes[0], original)
            editor.apply(dict(op='undo'))
            self.assertEqual(book.page(0).strokes[0].payload(), original_payload)


if __name__ == '__main__':
    unittest.main()
