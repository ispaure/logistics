"""Conversation UI state and recovery using Toga's explicit dummy backend."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from logisticsmobile.app import LogisticsMobile
from logisticsmobile.chat_fixture import fixture_server


class ChatUITests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_chat()

    def tearDown(self):
        app = self.app
        if app.chat_render_task is not None:
            app.chat_render_task.cancel()
            app.loop.run_until_complete(asyncio.gather(app.chat_render_task, return_exceptions=True))
        app.chat_actions.dispose()
        app.main_window.close()
        app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def configure(self, url):
        self.app.chat_url.value = url
        self.app.chat_model.value = 'fixture-model'

    def test_chat_cards_use_shared_surface_styling_and_keep_live_content(self):
        from logisticsmobile.appearance import _surfaces
        app = self.app
        self.assertNotIn(app.chat_transcript_card._impl, _surfaces)
        self.assertEqual(_surfaces[app.chat_sidebar._impl], 16)
        self.assertEqual(_surfaces[app.chat_prompt._impl], 12)
        self.assertIs(app.chat_transcript.parent, app.chat_transcript_card)
        app.chat_prompt.value = 'Retain the composer draft'
        app.toggle_chat_conversations()
        app.toggle_chat_conversations()
        self.assertEqual(app.chat_prompt.value, 'Retain the composer draft')

    def test_idle_status_collapses_and_growing_draft_survives_history(self):
        app = self.app
        self.assertEqual(list(app.chat_status_box.children), [])
        self.assertEqual(list(app.chat_composer.children), [app.chat_prompt, app.chat_send])
        app.chat_prompt.value = 'First\nSecond\nThird\nFourth'
        self.assertGreater(app.chat_prompt.style.height, 52)
        key = app.chat_current['id']
        app.new_chat()
        self.assertEqual(app.chat_prompt.style.height, 52)
        app.open_chat(key)
        self.assertEqual(app.chat_prompt.value, 'First\nSecond\nThird\nFourth')
        self.assertGreater(app.chat_prompt.style.height, 52)
        app.set_chat_status('A useful error')
        self.assertIn(app.chat_status, app.chat_status_box.children)
        self.assertIn(app.chat_config_status, app.chat_config_status_box.children)
        app.set_chat_status('')
        self.assertEqual(list(app.chat_status_box.children), [])

    def test_sending_keeps_next_draft_and_restores_the_single_primary_action(self):
        app = self.app
        with patch('socket.getfqdn', side_effect=AssertionError('No DNS')), fixture_server() as (url, _, _, requests):
            self.configure(url)
            async def exercise():
                app.chat_prompt.value = 'Hello'
                task = asyncio.create_task(app.chat_primary_action())
                await asyncio.sleep(.01)
                self.assertTrue(app.chat_busy)
                self.assertEqual(app.chat_send.text, 'Stop')
                self.assertTrue(app.chat_send.enabled)
                app.chat_prompt.value = 'Next unsent draft'
                await task
            app.loop.run_until_complete(exercise())
        self.assertEqual(app.chat_current['messages'][-1]['content'], 'Native fixture reply')
        self.assertEqual(app.chat_prompt.value, 'Next unsent draft')
        self.assertEqual(app.chat_store.load(app.chat_current['id'])['draft'], 'Next unsent draft')
        self.assertEqual(app.chat_send.text, 'Send')
        self.assertTrue(app.chat_send.enabled)
        self.assertEqual(app.chat_status.value, '')
        self.assertEqual(len(requests), 1)

    def test_stop_interrupts_stream_and_preserves_recovery_record(self):
        app = self.app
        with patch('socket.getfqdn', side_effect=AssertionError('No DNS')), fixture_server(mode='pause') as (url, started, release, _):
            self.configure(url)
            async def exercise():
                app.chat_prompt.value = 'Stop this request'
                task = asyncio.create_task(app.chat_primary_action())
                try:
                    self.assertTrue(await asyncio.to_thread(started.wait, 3))
                    await app.chat_primary_action()
                    self.assertFalse(app.chat_send.enabled)
                    await asyncio.wait_for(task, 3)
                finally:
                    release.set()
                    if not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
            app.loop.run_until_complete(exercise())
        saved = app.chat_store.load(app.chat_current['id'])
        self.assertEqual(saved['messages'][-1]['status'], 'cancelled')
        self.assertFalse(app.chat_busy)
        self.assertEqual(app.chat_send.text, 'Send')
        self.assertTrue(app.chat_send.enabled)

    def test_model_refresh_cannot_turn_the_primary_button_into_stop(self):
        app = self.app
        app.set_chat_busy(True)
        self.assertEqual(app.chat_send.text, 'Send')
        self.assertFalse(app.chat_send.enabled)
        app.set_chat_busy(False)

    def test_conversation_actions_remain_available_during_background_transfers(self):
        app = self.app
        app.cloud_busy = True
        app.chat_prompt.value = 'Keep this draft'
        key = app.chat_current['id']
        app.chat_actions.invoke(app.new_chat)
        self.assertNotEqual(app.chat_current['id'], key)
        self.assertEqual(app.chat_store.load(key)['draft'], 'Keep this draft')
        app.set_chat_busy(True, generating=True)
        current = app.chat_current['id']
        app.chat_actions.invoke(app.new_chat)
        self.assertEqual(app.chat_current['id'], current)
        app.set_chat_busy(False)
        app.cloud_busy = False

    def test_transcript_updates_coalesce_and_use_the_latest_conversation(self):
        app = self.app
        scripts = []
        async def evaluate(script):
            scripts.append(script)
            if len(scripts) == 1:
                app.new_chat()
            return True
        with patch.object(app.chat_transcript, 'evaluate_javascript', side_effect=evaluate):
            app.chat_transcript_loaded()
            app.loop.run_until_complete(app.chat_render_task)
        self.assertEqual(len(scripts), 2)
        self.assertIn(app.chat_current['id'], scripts[-1])

    def test_configuration_refreshes_heading_and_empty_state_without_connecting(self):
        app = self.app
        self.configure('http://127.0.0.1:1234/v1')
        app.save_chat_configuration()
        self.assertEqual(app.chat_model_label.text, 'fixture-model')
        app.chat_render_ready = True
        with patch.object(app.chat_transcript, 'evaluate_javascript', new=AsyncMock(return_value=True)) as evaluate:
            app.update_chat_transcript()
            app.loop.run_until_complete(app.chat_render_task)
            self.assertIn('"configured": true', evaluate.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
