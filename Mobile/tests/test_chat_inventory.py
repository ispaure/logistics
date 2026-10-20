"""Conversation lists cache summaries only and preserve cold-start selection."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from unittest import TestCase
from unittest.mock import patch

from features.lm.mobile.storage import ChatStore


class ChatInventoryTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.store = ChatStore(self.root / 'LM')
        self.data = self.store.new()
        self.data['title'] = 'Existing conversation'
        self.data['draft'] = 'Content not needed by inventory'
        self.store.save(self.data)

    def test_summaries_exclude_content_and_skip_unchanged_record_reads(self):
        with patch.object(self.store, '_bytes', side_effect=AssertionError('No unchanged reads')):
            records, warnings = self.store.summaries()
        self.assertFalse(warnings)
        self.assertEqual(set(records[0]), {'id', 'title', 'updated'})
        self.assertNotIn('Content not needed', repr(self.store._summaries))

    def test_external_changes_and_corruption_invalidate_summaries(self):
        path = self.store.path(self.data['id'])
        value = json.loads(path.read_text())
        value['title'] = 'External title'
        path.write_text(json.dumps(value))
        self.assertEqual(self.store.summaries()[0][0]['title'], 'External title')
        path.write_text('invalid')
        self.assertTrue(self.store.summaries()[1])
        self.assertEqual(self.store.cached_summaries()[0], [])

    def test_async_first_visit_selects_existing_conversation_without_creating_another(self):
        from logisticsmobile.app import LogisticsMobile
        LogisticsMobile.storage_root = self.root
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(app.loop.close)
        self.addCleanup(app.main_window.close)
        async def exercise():
            app.show_chat()
            await app.chat_controller()._chat_inventory_task
            self.assertEqual(app.chat_current['id'], self.data['id'])
            self.assertEqual(app.chat_prompt.value, self.data['draft'])
            self.assertEqual(len(app.chat_store.summaries()[0]), 1)
            if app.chat_render_task is not None:
                await app.chat_render_task
        app.loop.run_until_complete(exercise())
