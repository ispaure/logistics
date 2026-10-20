"""Batched recovery cannot persist session-only drafts or revive retired files."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import get_ident
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from logisticsmobile.documents import DocumentStore


class DeferredCheckpointTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = DocumentStore(Path(directory.name))
        self.doc = self.store.create('fixture.txt', b'Baseline')
        self.loop = asyncio.get_running_loop()

    async def settle(self):
        await asyncio.sleep(.3)
        await asyncio.gather(*self.store._writes)

    async def test_edits_coalesce_and_publish_on_a_worker(self):
        from logisticsmobile.documents import atomic_write_json
        threads = []
        def write(*args, **kwargs):
            threads.append(get_ident())
            return atomic_write_json(*args, **kwargs)
        with patch('logisticsmobile.documents.atomic_write_json', side_effect=write):
            for number in range(50):
                self.doc.text = str(number)
                self.store.queue_checkpoint(self.doc, self.loop)
            await self.settle()
        self.assertEqual(len(threads), 1)
        self.assertNotEqual(threads[0], get_ident())
        self.assertEqual(self.store.open(self.doc.id).text, '49')

    async def test_privatizing_cancels_pending_plaintext_and_keeps_baseline(self):
        self.doc.text = 'SESSION-ONLY-SENTINEL'
        self.store.queue_checkpoint(self.doc, self.loop)
        self.store.privatize(self.doc)
        self.store.queue_checkpoint(self.doc, self.loop)
        await self.settle()
        for path in self.store.root.iterdir():
            self.assertNotIn(b'SESSION-ONLY-SENTINEL', path.read_bytes())
        self.assertEqual(self.store.open(self.doc.id).text, 'Baseline')

    async def test_delete_cannot_be_undone_by_a_queued_write(self):
        self.doc.text = 'Discarded edit'
        self.store.queue_checkpoint(self.doc, self.loop)
        self.store.delete(self.doc)
        await self.settle()
        self.assertFalse(list(self.store.root.iterdir()))

    async def test_explicit_flush_keeps_latest_draft_and_cancels_timer(self):
        self.doc.text = 'Latest edit'
        self.store.queue_checkpoint(self.doc, self.loop)
        self.store.flush_checkpoints()
        self.assertEqual(self.store.open(self.doc.id).text, 'Latest edit')
        self.assertFalse(self.store._pending)
        self.assertFalse(self.store._timers)
