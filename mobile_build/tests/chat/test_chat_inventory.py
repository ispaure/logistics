"""Conversation lists cache summaries only and preserve cold-start selection."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from unittest import TestCase
from unittest.mock import patch

from features.lm.mobile.storage import ChatStore
from mobile_build.tests.support.chat import create_chat_app


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

    def inventory_app(self):
        # Seed the managed app's own root before its first visit. If draining
        # fails, that fixture can retain its files independently of this case's
        # synchronous storage fixture.
        app = create_chat_app(self)
        source = self.store.path(self.data['id'])
        if source.exists():
            destination = app.private_root / 'LM' / source.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
        return app

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

    def test_non_object_profiles_are_reported_and_preserved(self):
        profile = self.store.root / 'profile.json'
        for value in (None, [], 'invalid', 1, True):
            with self.subTest(value=value):
                content = json.dumps(value).encode('utf-8')
                profile.write_bytes(content)
                with self.assertRaisesRegex(ValueError, 'Invalid mobile chat profile'):
                    self.store.profile()
                self.assertEqual(profile.read_bytes(), content)
                self.assertEqual(self.store.load(self.data['id'])['draft'], self.data['draft'])

    def test_invalid_profile_does_not_prevent_opening_existing_conversation(self):
        app = self.inventory_app()
        profile = app.private_root / 'LM' / 'profile.json'
        profile.write_bytes(b'[]')
        app.show_chat()
        self.assertEqual(app.chat_current['id'], self.data['id'])
        self.assertEqual(app.chat_prompt.value, self.data['draft'])
        self.assertIn('Invalid mobile chat profile', app.chat_status.value)
        self.assertEqual(profile.read_bytes(), b'[]')
        # The fallback must not authorize overwriting the unreadable profile.
        with self.assertRaisesRegex(OSError, 'profile changed'):
            app.chat_store.save_profile(app.chat_profile, app.chat_profile_original)
        self.assertEqual(profile.read_bytes(), b'[]')

    def test_async_first_visit_selects_existing_conversation_without_creating_another(self):
        app = self.inventory_app()
        async def exercise():
            app.show_chat()
            await app.chat_controller()._chat_inventory_task
            self.assertEqual(app.chat_current['id'], self.data['id'])
            self.assertEqual(app.chat_prompt.value, self.data['draft'])
            self.assertEqual(len(app.chat_store.summaries()[0]), 1)
            if app.chat_render_task is not None:
                await app.chat_render_task
        app.loop.run_until_complete(exercise())

    def test_typing_before_inventory_finishes_preserves_the_new_draft(self):
        app = self.inventory_app()
        async def exercise():
            app.show_chat()
            self.assertIsNone(app.chat_current)
            app.chat_prompt.value = 'Typed while discovery was running'
            draft_id = app.chat_current['id']
            await app.chat_controller()._chat_inventory_task
            self.assertEqual(app.chat_current['id'], draft_id)
            self.assertEqual(app.chat_prompt.value, 'Typed while discovery was running')
            self.assertTrue(app.checkpoint_chat())
            self.assertEqual(app.chat_store.load(draft_id)['draft'], app.chat_prompt.value)
            self.assertEqual(app.chat_store.load(self.data['id'])['draft'], self.data['draft'])
            if app.chat_render_task is not None:
                await app.chat_render_task
        app.loop.run_until_complete(exercise())

    def _verify_connect_during_discovery(self, existing):
        if not existing:
            self.store.path(self.data['id']).unlink()
        app = self.inventory_app()

        async def exercise():
            app.show_chat()
            controller = app.chat_controller()
            app.set_chat_busy(True)
            await controller._chat_inventory_task
            self.assertIsNone(app.chat_current)
            self.assertTrue(controller._chat_needs_initial_selection)
            app.set_chat_busy(False)
            await controller._chat_inventory_task
            self.assertIsNotNone(app.chat_current)
            self.assertFalse(controller._chat_needs_initial_selection)
            if existing:
                self.assertEqual(app.chat_current['id'], self.data['id'])
                self.assertEqual(app.chat_prompt.value, self.data['draft'])
            self.assertEqual(len(app.chat_store.summaries()[0]), 1)
            if app.chat_render_task is not None:
                await app.chat_render_task

        app.loop.run_until_complete(exercise())

    def test_connect_during_discovery_retains_existing_conversation(self):
        self._verify_connect_during_discovery(True)

    def test_connect_during_empty_discovery_creates_initial_conversation(self):
        self._verify_connect_during_discovery(False)
