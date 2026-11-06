"""Conversation UI state and recovery using Toga's explicit dummy backend."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from copy import deepcopy
import unittest
from unittest.mock import AsyncMock, patch

from mobile.chat_fixture import fixture_server
from mobile_build.tests.support.chat import create_chat_app, wait_for_chat_writes


class ChatUITests(unittest.TestCase):
    def test_configuration_disclosures_preserve_values_and_fit_narrow_width(self):
        app = self.app
        app.show_chat_configuration()
        owner = app.chat_controller()
        self.assertFalse(owner.chat_manual_box.children)
        self.assertFalse(owner.chat_generation_box.children)
        owner.chat_manual_toggle.on_press()
        app.chat_model.value = 'manual-model'
        owner.chat_generation_toggle.on_press()
        app.chat_context.value = '8192'
        app.chat_max_tokens.value = '512'
        for width in (280, 390, 900, 280):
            with patch.object(app.adaptive, 'content_width', return_value=width):
                owner.fit_chat_configuration()
            self.assertEqual(app.chat_context.value, '8192')
            self.assertEqual(app.chat_max_tokens.value, '512')
        owner.chat_manual_toggle.on_press()
        owner.chat_generation_toggle.on_press()
        self.assertFalse(owner.chat_manual_box.children)
        self.assertFalse(owner.chat_generation_box.children)
        self.assertEqual(app.chat_model.value, 'manual-model')

    def test_configuration_save_from_chat_returns_to_conversation_and_keeps_draft(self):
        app = self.app
        app.chat_prompt.value = 'Draft survives settings'
        app.show_chat_configuration()
        self.configure('http://127.0.0.1:1234')
        app.save_chat_configuration()
        self.assertEqual(app.native_host.state.destination, 'chat')
        self.assertFalse(app.routes.screens['chat'])
        self.assertEqual(app.chat_prompt.value, 'Draft survives settings')

    def test_configuration_save_is_unavailable_while_connecting(self):
        app = self.app
        self.configure('http://127.0.0.1:1234')
        app.show_chat_configuration()
        app.set_chat_busy(True)
        owner = app.chat_controller()
        self.assertFalse(owner.chat_config_save.enabled)
        app.save_chat_configuration()
        self.assertEqual(app.routes.screens['chat'][-1][0], 'chat-settings')
        app.set_chat_busy(False)
        self.assertTrue(owner.chat_config_save.enabled)

    def test_server_with_no_models_reveals_manual_id_and_does_not_leave_empty_picker(self):
        app = self.app
        self.configure('http://127.0.0.1:1234')
        owner = app.chat_controller()
        with patch('features.lm.mobile.ui.ChatClient') as client:
            client.return_value.models.return_value = []
            app.loop.run_until_complete(app.refresh_chat_models())
        self.assertIn(app.chat_model, owner.chat_manual_box.children)
        self.assertEqual(list(owner.chat_model_choices.children), [owner.chat_model_hint])

    def test_markdown_size_updates_chat_without_replacing_the_draft_or_transcript(self):
        from mobile.font_scaling import refresh
        app = self.app
        app.chat_prompt.value = 'Keep my draft'
        app.chat_transcript.evaluate_javascript = AsyncMock()
        with patch('mobile.font_scaling.native_backend', return_value='toga_iOS.widgets'):
            app.preferences.values['font_size'] = '12'
            app.preferences.values['markdown_font_size'] = '24'
            refresh(app)
            app.loop.run_until_complete(asyncio.sleep(0))
            self.assertEqual(app.chat_prompt.style.font_size, 18)
            self.assertIn("fontSize='24px'", app.chat_transcript.evaluate_javascript.call_args.args[0])
            app.show_chat()
            self.assertEqual(app.chat_prompt.style.font_size, 18)
        self.assertEqual(app.chat_prompt.value, 'Keep my draft')

    def setUp(self):
        self.app = create_chat_app(self)
        self.app.show_chat()

    def configure(self, url):
        self.app.chat_url.value = url
        self.app.chat_model.value = 'fixture-model'

    def test_client_preparation_failure_keeps_unsent_turn_out_of_saved_history(self):
        app = self.app
        self.configure('http://127.0.0.1:1234')
        app.chat_prompt.value = 'Send once after correcting the session key'
        self.assertTrue(app.checkpoint_chat())
        record = app.chat_current
        before = deepcopy(record)
        app.chat_key.value = 'synthetic invalid key'
        with patch('features.lm.mobile.ui.ChatClient.stream',
                   side_effect=lambda payload, fragment: fragment('Accepted') or 'stop') as stream:
            for _ in range(2):
                app.loop.run_until_complete(app.send_chat())
                self.assertIs(app.chat_current, record)
                self.assertEqual(record, before)
                self.assertEqual(app.chat_store.load(record['id']), before)
                self.assertEqual(app.chat_prompt.value, before['draft'])
                self.assertIn('API keys must', app.chat_status.value)
                self.assertFalse(app.chat_busy)
                self.assertIsNone(app.chat_client)
            stream.assert_not_called()
            app.chat_key.value = 'synthetic-valid-key'
            app.loop.run_until_complete(app.send_chat())
            stream.assert_called_once()
        saved = app.chat_store.load(record['id'])
        self.assertEqual([entry['role'] for entry in saved['messages']], ['user', 'assistant'])
        self.assertEqual(saved['messages'][0]['content'], before['draft'])
        self.assertEqual(saved['messages'][1]['content'], 'Accepted')
        self.assertEqual(saved['messages'][1]['status'], 'complete')
        self.assertEqual(saved['draft'], '')

    def test_laptop_preserves_transcript_and_draft_through_history_and_unfold(self):
        app = self.app
        owner = app.chat_controller()
        transcript = app.chat_transcript
        app.chat_prompt.value = 'Keep this draft'
        previous_drawer = app.chat_drawer_open
        with patch('features.lm.mobile.laptop.chat_region', return_value=(600, 280, 20)):
            app.render_chat_workspace()
            self.assertTrue(owner.laptop.active)
            self.assertIs(app.chat_transcript_card.parent, app.chat_workspace)
            self.assertIs(app.chat_composer.parent, owner.laptop.deck)
            app.toggle_chat_conversations()
            self.assertIs(app.chat_sidebar.parent, owner.laptop.deck)
            self.assertIs(app.chat_transcript_card.parent, app.chat_workspace)
            app.toggle_chat_conversations()
            self.assertEqual(app.chat_prompt.value, 'Keep this draft')
        app.render_chat_workspace()
        self.assertFalse(owner.laptop.active)
        self.assertEqual(app.chat_drawer_open, previous_drawer)
        self.assertIs(app.chat_transcript, transcript)
        self.assertIs(app.chat_composer.parent, app.chat_messages)

    def test_laptop_keyboard_keeps_compact_composer_above_hinge(self):
        from features.lm.mobile.laptop import allocation
        for height, seam, gap, status in [(600, 280, 20, 0), (300, 280, 20, 48), (200, 280, 20, 0)]:
            upper, reserved, deck, prompt, tools = allocation(height, seam, gap, status)
            self.assertGreaterEqual(prompt, 44)
            self.assertLessEqual(upper + reserved + deck, height)
            if tools:
                self.assertLess(upper, seam)
                self.assertGreater(upper + reserved, seam + gap)
            else:
                self.assertLessEqual(upper + deck, seam)
        with patch('features.lm.mobile.laptop.chat_region', return_value=(220, 280, 20)):
            self.app.render_chat_workspace()
            self.assertNotIn(self.app.chat_controller().laptop.tools, self.app.chat_controller().laptop.deck.children)

    def test_rotation_header_uses_current_safe_width_instead_of_previous_layout(self):
        app = self.app
        app.chat_drawer_open = True
        with patch.object(app.adaptive, 'content_width') as available, patch.object(app.adaptive, 'width') as window:
            for width in (720, 370, 720, 370):
                available.return_value = window.return_value = width
                app.update_chat_header()
                pane_width = width - (240 + 12 if width >= 640 else 0)
                self.assertEqual(app.chat_title.style.width, pane_width - 16)
                self.assertEqual(app.chat_model_label.style.width, pane_width - 16)
                self.assertIs(app.chat_title.parent.parent, app.chat_transcript_card)

    def test_batched_drafts_never_persist_the_session_api_key(self):
        self.app.chat_key.value = 'SESSION-ONLY-API-KEY-SENTINEL'
        self.app.chat_prompt.value = 'Synthetic draft'
        self.app.loop.run_until_complete(wait_for_chat_writes(self.app.chat_store))
        self.assertEqual(self.app.chat_store.load(self.app.chat_current['id'])['draft'], 'Synthetic draft')
        for path in self.app.private_root.rglob('*.json'):
            self.assertNotIn(b'SESSION-ONLY-API-KEY-SENTINEL', path.read_bytes())

    def test_large_conversation_inventory_uses_one_recycled_control_and_stable_keys(self):
        app = self.app
        records = [dict(id=f'{index:032x}', title=f'Conversation {index}', updated=str(index))
                   for index in range(1000)]
        controller = app.chat_controller()
        with patch('features.lm.mobile.ui.toga.Button', side_effect=AssertionError('No per-conversation controls')):
            controller._publish_chat_inventory(records, [])
        listing = app.chat_conversation_list
        self.assertEqual(len(listing.data), 1000)
        self.assertEqual(app.chat_conversation_buttons, [])
        self.assertIs(listing.parent, app.chat_sidebar_content)
        with patch.object(controller, 'open_chat') as open_chat:
            listing.select_index(17)
            listing.on_select()
            open_chat.assert_called_once_with(records[17]['id'])
            open_chat.reset_mock()
            app.set_chat_busy(True)
            listing.select_index(18)
            listing.on_select()
            open_chat.assert_not_called()
            self.assertFalse(listing.enabled)

    def test_delayed_selection_notifications_do_not_reopen_the_active_chat(self):
        from types import SimpleNamespace
        app = self.app
        controller = app.chat_controller()
        key = app.chat_current['id']
        app.chat_prompt.value = 'Draft kept through delayed selection callbacks'
        controller._publish_chat_inventory([dict(id=key, title='Active', updated='0'),
            dict(id='f' * 32, title='Other', updated='1')], [])
        listing = app.chat_conversation_list
        with patch.object(controller, 'open_chat') as open_chat:
            for _ in range(3):
                controller.select_chat(SimpleNamespace(value='Active'))
                listing.select_index(0)
                listing.on_select()
            open_chat.assert_not_called()
            controller.select_chat(SimpleNamespace(value='Other'))
            open_chat.assert_called_once_with('f' * 32)
        self.assertEqual(app.chat_current['id'], key)
        self.assertEqual(app.chat_prompt.value, 'Draft kept through delayed selection callbacks')

    def test_chat_drawer_keeps_live_content(self):
        app = self.app
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
        with patch('socket.getfqdn', side_effect=AssertionError('No DNS')), fixture_server(mode='pause') as (url, started, release, requests):
            self.configure(url)
            async def exercise():
                app.chat_prompt.value = 'Hello'
                task = asyncio.create_task(app.chat_primary_action())
                try:
                    self.assertTrue(await asyncio.to_thread(started.wait, 3))
                    self.assertTrue(app.chat_busy)
                    self.assertEqual(app.chat_send.accessible_name, 'Stop')
                    self.assertTrue(app.chat_send.enabled)
                    app.chat_prompt.value = 'Next unsent draft'
                    release.set()
                    await asyncio.wait_for(task, 3)
                finally:
                    release.set()
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
            app.loop.run_until_complete(exercise())
        self.assertEqual(app.chat_current['messages'][-1]['content'], 'Native fixture reply')
        self.assertEqual(app.chat_prompt.value, 'Next unsent draft')
        self.assertEqual(app.chat_store.load(app.chat_current['id'])['draft'], 'Next unsent draft')
        self.assertEqual(app.chat_send.accessible_name, 'Send')
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
        self.assertEqual(app.chat_send.accessible_name, 'Send')
        self.assertTrue(app.chat_send.enabled)

    def test_model_refresh_cannot_turn_the_primary_button_into_stop(self):
        app = self.app
        app.set_chat_busy(True)
        self.assertEqual(app.chat_send.accessible_name, 'Send')
        self.assertFalse(app.chat_send.enabled)
        app.set_chat_busy(False)

    def test_connect_discovers_and_saves_model_without_manual_id(self):
        app = self.app
        app.chat_url.value = 'http://192.168.1.10:1234'
        with patch('features.lm.mobile.ui.ChatClient') as client:
            client.return_value.models.return_value = ['first-model', 'second-model']
            app.loop.run_until_complete(app.refresh_chat_models())
            self.assertEqual(app.chat_model.value, 'first-model')
            self.assertEqual(app.chat_models.value, 'first-model')
            self.assertEqual(app.chat_store.profile()[0]['model'], 'first-model')
            self.assertEqual(app.chat_url.value, 'http://192.168.1.10:1234/v1')
            self.assertIn('Connected.', app.chat_config_status.value)
            app.chat_models.value = 'second-model'
            app.loop.run_until_complete(app.refresh_chat_models())
            self.assertEqual(app.chat_model.value, 'second-model')
            self.assertEqual(app.chat_models.value, 'second-model')
            self.assertEqual(app.chat_store.profile()[0]['model'], 'second-model')

    def test_save_without_model_keeps_setup_open_and_makes_no_request(self):
        app = self.app
        app.show_chat_configuration()
        with patch('features.lm.mobile.ui.ChatClient') as client, patch.object(app, 'show_chat') as show_chat:
            app.save_chat_configuration()
            client.assert_not_called()
            show_chat.assert_not_called()
        self.assertIn('Connect & load models', app.chat_config_status.value)
        self.assertIs(app.chat_config_status_box.parent, app.chat_controller().chat_save_feedback)

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
        app.preferences.values.update(font_size='12', markdown_font_size='24')
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
        self.assertIn('"font_size": 24', scripts[-1])

    def test_transcript_worker_cannot_publish_after_switching_conversations(self):
        from threading import Event, get_ident
        from features.lm.mobile.presentation import transcript_entries
        started, release = Event(), Event()
        old_key = self.app.chat_current['id']
        threads, scripts = [], []
        def parse(*args):
            threads.append(get_ident())
            started.set()
            if not release.wait(3):
                raise RuntimeError('Synthetic renderer timed out')
            return transcript_entries(*args)
        async def exercise():
            self.app.chat_transcript_loaded()
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                self.app.new_chat()
                release.set()
                await self.app.chat_render_task
            finally:
                release.set()
                await self.app.chat_render_task
        with patch('features.lm.mobile.ui.transcript_entries', side_effect=parse), \
                patch.object(self.app.chat_transcript, 'evaluate_javascript',
                             new=AsyncMock(side_effect=lambda script: scripts.append(script) or True)):
            self.app.loop.run_until_complete(exercise())
        self.assertTrue(threads)
        self.assertTrue(all(thread != get_ident() for thread in threads))
        self.assertTrue(scripts)
        self.assertTrue(all(old_key not in script for script in scripts))

    def test_configuration_refreshes_heading_and_empty_state_without_connecting(self):
        app = self.app
        self.configure('http://127.0.0.1:1234/v1')
        app.save_chat_configuration()
        self.assertEqual(app.chat_model_label.text, 'Server · fixture-model')
        app.chat_render_ready = True
        with patch.object(app.chat_transcript, 'evaluate_javascript', new=AsyncMock(return_value=True)) as evaluate:
            app.update_chat_transcript()
            app.loop.run_until_complete(app.chat_render_task)
            self.assertIn('"configured": true', evaluate.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
