"""Receipt accounting, immutable export resume and independent failure phases."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from commonUtils.testing.stages import TestStage
from features.notebooks.notebook import Notebook
from features.notebooks.remarkable_store import TabletSnapshot
from tests.notebooks.corpus_receipts import run_batch

TEST_STAGE = TestStage.REGRESSION
FOLDER = '10000000-0000-4000-8000-000000000001'


def accepted(path, pages, row):
    for phase in ('editor_open', 'page_render', 'save_reopen'):
        row[phase] = dict(status='passed')


class CorpusReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.books = [Notebook.new('Same'), Notebook.new('Same')]
        self.metadata = {FOLDER: dict(type='CollectionType', visibleName='Nested')}
        self.metadata.update({book.id: dict(type='DocumentType', visibleName='Same', parent=FOLDER) for book in self.books})
        self.snapshot = TabletSnapshot.from_metadata(self.metadata)
        self.data = {book.id: book.to_bytes() for book in self.books}
        self.calls = []

    def batch(self, snapshot, workspace, retrieve, inspect):
        return run_batch(snapshot, workspace, retrieve, inspect, document_ids=[key for key, entry in snapshot.entries.items() if not entry.directory])

    def retrieve(self, identity, path):
        self.calls.append(identity)
        with path.open('xb') as stream:
            stream.write(self.data[identity])

    def test_duplicate_titles_and_nested_inventory_resume_without_export(self):
        first = self.batch(self.snapshot, self.root, self.retrieve, accepted)
        self.assertEqual(first['totals'], dict(inventory=3, visible_inventory=3, excluded=0, exclusions={}, metadata_occurrences=3,
            unidentified_records=0, folders=1, documents=2, selected_documents=2, outcomes={'passed': 2}, reconciled=True))
        second = self.batch(self.snapshot, self.root, self.retrieve, accepted)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(list((self.root / 'exports').glob('*.rmdoc'))), 2)
        self.assertTrue(all(row['retrieval']['reused'] and row['original_unchanged'] for row in second['items'] if not row['directory']))

    def test_changed_export_is_preserved_and_rejected(self):
        self.batch(self.snapshot, self.root, self.retrieve, accepted)
        target = self.root / 'exports' / (self.books[0].id + '.rmdoc')
        target.write_bytes(b'changed')
        result = self.batch(self.snapshot, self.root, self.retrieve, accepted)
        self.assertEqual(target.read_bytes(), b'changed')
        self.assertEqual(result['totals']['outcomes'], {'source_changed': 1, 'passed': 1})
        self.assertEqual(len(self.calls), 2)

    def test_interruption_keeps_verified_first_export_and_retries_pending(self):
        def interrupted(identity, target):
            if self.calls:
                raise KeyboardInterrupt
            self.retrieve(identity, target)
        with self.assertRaises(KeyboardInterrupt):
            self.batch(self.snapshot, self.root, interrupted, accepted)
        result = self.batch(self.snapshot, self.root, self.retrieve, accepted)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result['totals']['outcomes'], {'passed': 2})

    def test_archive_and_render_failures_are_separate_and_counted(self):
        self.data[self.books[0].id] = b'invalid zip'
        def bad_render(path, pages, row):
            row['editor_open'] = dict(status='passed')
            row['page_render'] = dict(status='failed')
            raise ValueError('private identifying detail')
        result = self.batch(self.snapshot, self.root, self.retrieve, bad_render)
        self.assertEqual(result['totals']['outcomes'], {'archive_failed': 1, 'page_render_failed': 1})
        self.assertNotIn('private identifying detail', (self.root / 'manifest.json').read_text())

    def test_unverified_interrupted_file_is_never_replaced(self):
        def partial(identity, target):
            target.write_bytes(b'partial')
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.batch(self.snapshot, self.root, partial, accepted)
        result = self.batch(self.snapshot, self.root, self.retrieve, accepted)
        self.assertEqual(result['totals']['outcomes'], {'retrieval_failed': 1, 'passed': 1})
        self.assertIn(b'partial', [p.read_bytes() for p in (self.root / 'exports').iterdir()])

    def test_changed_inventory_refuses_resume(self):
        self.batch(self.snapshot, self.root, self.retrieve, accepted)
        del self.metadata[self.books[0].id]
        with self.assertRaisesRegex(ValueError, 'same captured inventory'):
            self.batch(TabletSnapshot.from_metadata(self.metadata), self.root, self.retrieve, accepted)

    def test_unfiled_and_unknown_metadata_scope_is_explicit(self):
        self.metadata[self.books[0].id]['parent'] = 'missing'
        self.metadata['10000000-0000-4000-8000-000000000099'] = dict(type='UnknownType')
        result = self.batch(TabletSnapshot.from_metadata(self.metadata), self.root, self.retrieve, accepted)
        self.assertEqual(result['totals']['inventory'], 4)
        self.assertEqual(result['totals']['exclusions'], {'unsupported_type': 1})
        row = next(row for row in result['items'] if row['id'] == self.books[0].id)
        self.assertEqual(row['parent'], 'unfiled')
        self.assertTrue(row['issue'])

    def test_save_failure_is_not_counted_as_render_failure(self):
        def failed_save(path, pages, row):
            row['editor_open'] = row['page_render'] = dict(status='passed')
            row['save_reopen'] = dict(status='failed')
            raise OSError('save failed')
        result = self.batch(self.snapshot, self.root, self.retrieve, failed_save)
        self.assertEqual(result['totals']['outcomes'], {'save_reopen_failed': 2})

    def test_resume_rejects_missing_duplicate_or_retargeted_rows(self):
        import json
        result = self.batch(self.snapshot, self.root, self.retrieve, accepted)
        for items in (result['items'][:-1], result['items'] + result['items'][:1],
                      [dict(result['items'][0], id='../escape'), *result['items'][1:]]):
            (self.root / 'manifest.json').write_text(json.dumps(dict(result, items=items)))
            with self.assertRaisesRegex(ValueError, 'item identity'):
                self.batch(self.snapshot, self.root, self.retrieve, accepted)

    def test_missing_verified_original_is_not_reacquired(self):
        self.batch(self.snapshot, self.root, self.retrieve, accepted)
        (self.root / 'exports' / (self.books[0].id + '.rmdoc')).unlink()
        result = self.batch(self.snapshot, self.root, self.retrieve, accepted)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(result['totals']['outcomes'], {'source_changed': 1, 'passed': 1})

    def test_callback_cannot_delete_an_original_and_pass(self):
        def removed(path, pages, row):
            accepted(path, pages, row)
            path.unlink()
        result = self.batch(self.snapshot, self.root, self.retrieve, removed)
        self.assertEqual(result['totals']['outcomes'], {'source_changed': 2})

    def test_read_issues_occurrences_and_unidentified_survive_resume(self):
        bad = '10000000-0000-4000-8000-000000000098'
        observations = [(key, 'read') for key in self.metadata] + [(bad, 'unreadable_metadata'), (self.books[0].id, 'unreadable_metadata'), ('', 'unidentified_entry')]
        snapshot = TabletSnapshot.from_metadata(self.metadata, observations=observations)
        self.batch(snapshot, self.root, self.retrieve, accepted)
        result = self.batch(snapshot, self.root, self.retrieve, accepted)
        self.assertEqual(result['totals']['metadata_occurrences'], 5)
        self.assertEqual(result['totals']['unidentified_records'], 1)
        self.assertEqual(result['totals']['exclusions'], {'unreadable_metadata': 1})

    def test_unsupported_backing_is_accounted_without_hiding_malformed_metadata(self):
        self.books[0].content['fileType'] = 'epub'
        self.data[self.books[0].id] = self.books[0].to_bytes()
        self.books[1].metadata['visibleName'] = ['invalid title']
        self.data[self.books[1].id] = self.books[1].to_bytes()
        inspected = []
        result = self.batch(self.snapshot, self.root, self.retrieve, lambda *args: inspected.append(args))
        self.assertEqual(inspected, [])
        self.assertEqual(result['totals']['outcomes'], {'editor_open_unsupported': 1, 'editor_open_failed': 1})
        self.assertTrue(all(row['original_unchanged'] for row in result['items'] if not row['directory']))

    def test_conservative_readiness_does_not_invent_pixel_expectations(self):
        from tests.notebooks.corpus_prepare import conservative_page_receipt
        expected = dict(index=4, count=19, strokes=[{}, {}, {}], images=[{}], background=None,
                        password_required=False, warning='', scene_order=['ink-1', 'image-1'], template_settings=dict(visible=False),
                        template_available=False, template_editable=True)
        measured = dict(index=4, count=19, strokes=3, images=1, canvas=[100, 200], dpr=2,
                        css_scale=.4, background=False, scene_order=['ink-1', 'image-1'], visible_images=1, decoded_images=1)
        result = conservative_page_receipt(expected, measured)
        self.assertEqual(result['status'], 'observed')
        self.assertNotIn('ink_pixels', result['measured'])
        for updates, status in ((dict(password_required=True), 'blocked'),
                                (dict(warning='opaque page'), 'unsupported'),
                                (dict(template_settings=dict(visible=True)), 'unsupported')):
            self.assertEqual(conservative_page_receipt(dict(expected, **updates), measured)['status'], status)
        with self.assertRaises(AssertionError):
            conservative_page_receipt(expected, dict(measured, index=0))
        with self.assertRaises(AssertionError):
            conservative_page_receipt(expected, dict(measured, css_scale=float('nan')))
        with self.assertRaises(AssertionError):
            conservative_page_receipt(expected, dict(measured, scene_order=['image-1', 'ink-1']))
        with self.assertRaises(AssertionError):
            conservative_page_receipt(expected, dict(measured, decoded_images=0))

    def test_acquisition_is_empty_by_default_and_selection_is_bound_on_resume(self):
        result = run_batch(self.snapshot, self.root, self.retrieve, accepted)
        self.assertEqual(self.calls, [])
        self.assertEqual(result['totals']['outcomes'], {'not_selected': 2})
        self.assertEqual(result['totals']['selected_documents'], 0)
        with self.assertRaisesRegex(ValueError, 'same captured inventory'):
            self.batch(self.snapshot, self.root, self.retrieve, accepted)
        selected = self.books[0].id
        result = run_batch(self.snapshot, self.root / 'selected', self.retrieve, accepted, document_ids=[selected])
        self.assertEqual(self.calls, [selected])
        self.assertEqual(result['totals']['outcomes'], {'passed': 1, 'not_selected': 1})
        self.assertEqual(result['document_ids'], [selected])
        for ids in ([FOLDER], [selected, selected], ['outside-inventory']):
            with self.assertRaisesRegex(ValueError, 'distinct visible document IDs'):
                run_batch(self.snapshot, self.root / 'rejected', self.retrieve, accepted, document_ids=ids)
        self.assertFalse((self.root / 'rejected').exists())

    def test_old_schema_is_rejected_without_rewriting_its_receipt(self):
        import json
        result = self.batch(self.snapshot, self.root, self.retrieve, accepted)
        result['schema'] = 2
        path = self.root / 'manifest.json'
        original = json.dumps(result).encode()
        path.write_bytes(original)
        with self.assertRaisesRegex(ValueError, 'same captured inventory'):
            self.batch(self.snapshot, self.root, self.retrieve, accepted)
        self.assertEqual(path.read_bytes(), original)

    def test_cli_has_no_live_endpoint_option(self):
        import subprocess
        import sys
        output = self.root / 'live-output'
        result = subprocess.run([sys.executable, '-m', 'tests.notebooks.corpus_prepare',
            '--output', str(output), '--host', 'synthetic.invalid'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('unrecognized arguments: --host', result.stderr)
        self.assertFalse(output.exists())
