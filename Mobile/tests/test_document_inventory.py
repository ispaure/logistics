"""Inventories retain metadata only and leave full recovery validation to open."""
import json
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from threading import get_ident

from logisticsmobile.documents import DocumentStore


class DocumentInventoryTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = DocumentStore(Path(directory.name))
        self.doc = self.store.create('fixture.md', b'Content stays out of summaries')

    def test_warm_inventory_never_decodes_recovery_content(self):
        with patch.object(self.store, 'open', side_effect=AssertionError('No full document reads')):
            records, failures = self.store.summaries()
        self.assertFalse(failures)
        self.assertEqual([(row.id, row.name) for row in records], [(self.doc.id, 'fixture.md')])
        self.assertFalse(hasattr(records[0], 'text'))
        self.assertFalse(hasattr(records[0], 'snapshot'))

    def test_external_rename_and_deletion_invalidate_cached_summaries(self):
        path = self.store.path(self.doc.id, '.json')
        record = json.loads(path.read_text())
        record['name'] = 'renamed.txt'
        path.write_text(json.dumps(record))
        self.assertEqual(self.store.summaries()[0][0].name, 'renamed.txt')
        path.unlink()
        self.assertEqual(self.store.summaries(), ([], []))
        self.assertEqual(self.store.cached_summaries(), [])

    def test_full_open_still_rejects_corrupt_original_bytes(self):
        path = self.store.path(self.doc.id, '.json')
        record = json.loads(path.read_text())
        record['original'] = 'invalid!'
        path.write_text(json.dumps(record))
        self.assertEqual(self.store.summaries()[0][0].name, 'fixture.md')
        with self.assertRaises(ValueError):
            self.store.open(self.doc.id)

    def test_private_edits_do_not_enter_summary_payloads(self):
        self.store.privatize(self.doc)
        self.doc.text = 'SESSION-ONLY-SENTINEL'
        self.store.checkpoint(self.doc)
        self.assertNotIn('SESSION-ONLY-SENTINEL', repr(self.store.summaries()))
        self.assertNotIn('SESSION-ONLY-SENTINEL', repr(self.store._summaries))

    def test_live_refresh_runs_scan_on_worker_and_coalesces_requests(self):
        from logisticsmobile.app import LogisticsMobile
        LogisticsMobile.storage_root = self.store.root / 'App'
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(app.loop.close)
        self.addCleanup(app.main_window.close)
        threads = []
        original = app.store.summaries
        def scan():
            threads.append(get_ident())
            return original()
        async def exercise():
            app.refresh_documents()
            task = app._document_refresh_task
            app.refresh_documents()
            self.assertIs(task, app._document_refresh_task)
            await task
        with patch.object(app.store, 'summaries', side_effect=scan):
            app.loop.run_until_complete(exercise())
        self.assertEqual(len(threads), 1)
        self.assertNotEqual(threads[0], get_ident())

    def test_older_inventory_does_not_select_or_replace_a_new_draft(self):
        from logisticsmobile.app import LogisticsMobile
        LogisticsMobile.storage_root = self.store.root / 'App'
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(app.loop.close)
        self.addCleanup(app.main_window.close)
        old = app.store.summaries()[0]
        app.new_document()
        current = app.current
        app.editor.value = 'Typed while inventory was scanning'
        app._publish_document_summaries(old, [])
        self.assertIs(app.current, current)
        self.assertEqual(app.editor.value, 'Typed while inventory was scanning')
        self.assertFalse(app.loading)
