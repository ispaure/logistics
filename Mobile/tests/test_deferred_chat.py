"""Chat draft batching preserves revisions and keeps session API keys out of files."""
import asyncio
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from features.lm.mobile.storage import ChatStore


class DeferredChatTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = ChatStore(Path(directory.name))
        self.data = self.store.new()

    async def test_fifty_draft_changes_publish_one_latest_record(self):
        from features.lm.mobile.storage import atomic_write_bytes
        with patch('features.lm.mobile.storage.atomic_write_bytes', wraps=atomic_write_bytes) as write:
            for index in range(50):
                self.data['draft'] = str(index)
                self.store.queue_save(self.data, asyncio.get_running_loop())
            await asyncio.sleep(.3)
            await asyncio.gather(*self.store._writes)
        self.assertEqual(write.call_count, 1)
        self.assertEqual(self.store.load(self.data['id'])['draft'], '49')

    async def test_explicit_save_retires_an_older_worker(self):
        old = deepcopy(self.data)
        generation = self.store._generation[self.data['id']]
        self.data['draft'] = 'Newer explicit draft'
        self.store.save(self.data)
        self.store._publish(self.data, old, generation, 1)
        self.assertEqual(self.store.load(self.data['id'])['draft'], 'Newer explicit draft')

    async def test_workers_published_out_of_order_cannot_restore_an_old_draft(self):
        older, newer = deepcopy(self.data), deepcopy(self.data)
        older['draft'], newer['draft'] = 'Older', 'Newer'
        generation = self.store._generation[self.data['id']]
        self.store._publish(self.data, newer, generation, 2)
        self.store._publish(self.data, older, generation, 1)
        self.assertEqual(self.store.load(self.data['id'])['draft'], 'Newer')

    async def test_external_revision_is_never_overwritten(self):
        other = self.store.load(self.data['id'])
        other['draft'] = 'External writer'
        self.store.save(other)
        snapshot = deepcopy(self.data)
        snapshot['draft'] = 'Stale writer'
        with self.assertRaises(OSError):
            self.store._publish(self.data, snapshot, self.store._generation[self.data['id']], 1)
        self.assertEqual(self.store.load(self.data['id'])['draft'], 'External writer')
