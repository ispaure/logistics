"""Conversation UI state and recovery using Toga's explicit dummy backend."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from copy import deepcopy
from threading import Event
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

    def test_retired_host_discards_delayed_model_results_and_errors(self):
        app = self.app
        self.configure('http://127.0.0.1:1234')
        app.chat_prompt.value = 'Pending draft'

        async def exercise(error):
            entered, release = asyncio.Event(), Event()
            loop = asyncio.get_running_loop()

            def models():
                loop.call_soon_threadsafe(entered.set)
                if not release.wait(3):
                    raise RuntimeError('Model test gate timed out')
                if error:
                    raise ValueError('Delayed model failure')
                return ['Late model']

            with patch('features.lm.mobile.ui.ChatClient') as factory:
                factory.return_value.models.side_effect = models
                task = asyncio.create_task(app.refresh_chat_models())
                try:
                    await asyncio.wait_for(entered.wait(), 3)
                    status = app.chat_status.value
                    items = list(app.chat_models.items)
                    profile = app.chat_store.profile()
                    app.active_host = False
                    app.chat_client.cancel()
                    release.set()
                    await asyncio.wait_for(task, 3)
                    self.assertIsNone(app.chat_client)
                    self.assertFalse(app.chat_busy)
                    self.assertFalse(app.chat_refresh.enabled)
                    self.assertEqual(app.chat_status.value, status)
                    self.assertEqual(list(app.chat_models.items), items)
                    self.assertEqual(app.chat_store.profile(), profile)
                    key = app.chat_current['id']
                    app.new_chat()
                    self.assertEqual(app.chat_current['id'], key)
                    await app.refresh_chat_models()
                    await app.send_chat()
                    factory.assert_called_once()
                finally:
                    release.set()
                    await asyncio.gather(task, return_exceptions=True)
                    app.active_host = True
                    app.set_chat_busy(False)

        for error in (False, True):
            with self.subTest(error=error):
                app.loop.run_until_complete(exercise(error))

    def test_retired_host_saves_terminal_stream_without_publishing_controls(self):
        app = self.app
        self.configure('http://127.0.0.1:1234')

        async def exercise(error):
            entered, release = asyncio.Event(), Event()
            loop = asyncio.get_running_loop()

            def stream(payload, fragment):
                fragment('Published partial')
                loop.call_soon_threadsafe(entered.set)
                if not release.wait(3):
                    raise RuntimeError('Stream test gate timed out')
                fragment('Discard this late fragment')
                if error:
                    raise ValueError('Delayed stream failure')
                return 'stop'

            app.chat_prompt.value = 'Question'
            with patch('features.lm.mobile.ui.ChatClient') as factory:
                factory.return_value.stream.side_effect = stream
                task = asyncio.create_task(app.send_chat())
                try:
                    await asyncio.wait_for(entered.wait(), 3)
                    async with asyncio.timeout(2):
                        while app.chat_current['messages'][-1]['content'] != 'Published partial':
                            await asyncio.sleep(.01)
                    app.chat_prompt.value = 'Keep the next draft'
                    self.assertTrue(app.checkpoint_chat())
                    status = app.chat_status.value
                    revision = app.chat_render_revision
                    app.active_host = False
                    app.chat_client.cancel()
                    release.set()
                    await asyncio.wait_for(task, 3)
                    saved = app.chat_store.load(app.chat_current['id'])
                    self.assertEqual(saved['messages'][-1]['status'], 'failed' if error else 'complete')
                    self.assertEqual(saved['messages'][-1]['content'], 'Published partial')
                    self.assertEqual(saved['draft'], 'Keep the next draft')
                    self.assertIsNone(app.chat_client)
                    self.assertFalse(app.chat_busy)
                    self.assertEqual(app.chat_send.accessible_name, 'Stop')
                    self.assertEqual(app.chat_status.value, status)
                    self.assertEqual(app.chat_render_revision, revision)
                finally:
                    release.set()
                    await asyncio.gather(task, return_exceptions=True)
                    app.active_host = True
                    app.set_chat_busy(False)

        for error in (False, True):
            with self.subTest(error=error):
                app.loop.run_until_complete(exercise(error))

    def test_retired_host_discards_queued_transcript_acknowledgement(self):
        app = self.app

        async def exercise(outcome):
            entered, release = asyncio.Event(), asyncio.Event()

            async def evaluate(script):
                entered.set()
                await release.wait()
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

            with patch.object(app.chat_transcript, 'evaluate_javascript', side_effect=evaluate) as js:
                app.chat_transcript_loaded()
                task = app.chat_render_task
                try:
                    await asyncio.wait_for(entered.wait(), 3)
                    status = app.chat_status.value
                    app.active_host = False
                    release.set()
                    await asyncio.wait_for(task, 3)
                    self.assertEqual(app.chat_status.value, status)
                    self.assertTrue(app.chat_render_ready)
                    self.assertIsNone(app.chat_render_key)
                    self.assertEqual(app.chat_render_entries, [])
                    app.chat_transcript_loaded()
                    self.assertIs(app.chat_render_task, task)
                    js.assert_called_once()
                finally:
                    release.set()
                    await asyncio.gather(task, return_exceptions=True)
                    app.active_host = True

        for outcome in (True, False, ValueError('Retired WebView')):
            with self.subTest(outcome=outcome):
                app.loop.run_until_complete(exercise(outcome))

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
        title = 'A long conversation title that needs space to display fully'
        model = 'model-' + 'x' * 65
        app.chat_current['title'] = title
        app.chat_profile['model'] = model
        with patch.object(app.adaptive, 'content_width') as available, patch.object(app.adaptive, 'width') as window:
            for width in (1000, 720, 370, 1000):
                available.return_value = window.return_value = width
                app.update_chat_header()
                pane_width = width - (min(320, width // 3) + 12 if width >= 640 else 0)
                self.assertEqual(app.chat_title.style.width, pane_width - 16)
                self.assertEqual(app.chat_model_label.style.width, pane_width - 16)
                self.assertIs(app.chat_title.parent.parent, app.chat_transcript_card)
                for label, source in ((app.chat_title, title), (app.chat_model_label, 'Server · ' + model)):
                    self.assertEqual(''.join(label.text.split()), ''.join(source.split()))
                    self.assertEqual('\n' in label.text, width < 1000)

    def test_batched_drafts_never_persist_the_session_api_key(self):
        self.app.chat_key.value = 'SESSION-ONLY-API-KEY-SENTINEL'
        self.app.chat_prompt.value = 'Synthetic draft'
        self.app.loop.run_until_complete(wait_for_chat_writes(self.app.chat_store))
        self.assertEqual(self.app.chat_store.load(self.app.chat_current['id'])['draft'], 'Synthetic draft')
        for path in self.app.private_root.rglob('*.json'):
            self.assertNotIn(b'SESSION-ONLY-API-KEY-SENTINEL', path.read_bytes())

    def test_laptop_tool_removal_keeps_focused_composer_mounted(self):
        from features.lm.mobile.laptop import mount
        import toga
        parent = toga.Box()
        tools, composer = toga.Box(), toga.Box()
        parent.add(tools, composer)
        with patch.object(parent, 'remove', wraps=parent.remove) as remove:
            mount(parent, [composer])
        self.assertEqual(list(parent.children), [composer])
        remove.assert_called_once_with(tools)

    def test_keyboard_edge_accepts_overlapping_docked_but_ignores_floating_keyboard(self):
        from features.lm.mobile.laptop import docked_keyboard_top
        from types import SimpleNamespace
        from unittest.mock import Mock
        def rect(x, y, width, height):
            return SimpleNamespace(origin=SimpleNamespace(x=x, y=y),
                                   size=SimpleNamespace(width=width, height=height))
        window = Mock()
        window.bounds = rect(0, 0, 800, 600)
        keyboard = rect(0, 350, 800, 250)
        window.convertRect.return_value = keyboard
        native = Mock()
        native.bounds = rect(0, 0, 400, 600)
        native.convertRect.return_value = rect(-200, 300, 800, 250)
        owner = SimpleNamespace(native_host=SimpleNamespace(adapter=SimpleNamespace(
            keyboard_visible=True, keyboard_frame=keyboard)),
            main_window=SimpleNamespace(_impl=SimpleNamespace(native=window)))
        self.assertEqual(docked_keyboard_top(owner, native), 300)
        window.convertRect.return_value = rect(10, 200, 350, 200)
        self.assertIsNone(docked_keyboard_top(owner, native))
        owner.native_host.adapter.keyboard_visible = False
        self.assertIsNone(docked_keyboard_top(owner, native))

    def test_month_groups_expand_in_place_and_keep_stable_conversation_keys(self):
        owner = self.app.chat_controller()
        listing = owner.chat_conversation_list
        recent = dict(id='1' * 32, title='Recent', updated='2026-11-02T00:00:00+00:00')
        older = dict(id='2' * 32, title='Older', updated='2026-10-02T00:00:00+00:00')
        records = [recent, older]
        owner._publish_chat_inventory(records, [])
        self.assertEqual([(row.tree_depth, row.tree_expanded) for row in listing.data],
                         [(0, True), (1, None), (0, False)])
        old_group = listing.data[2]
        listing.select_index(2)
        listing.on_select()
        self.assertTrue(listing.data[2].tree_expanded)
        listing.tree_actions.toggle(old_group)
        self.assertTrue(listing.data[2].tree_expanded)  # Stale native cell.
        owner._publish_chat_inventory(records, [])
        self.assertEqual(listing.data[3].key, older['id'])
        with patch.object(owner, 'open_chat') as open_chat:
            listing.select_index(3)
            listing.on_select()
            open_chat.assert_called_once_with(older['id'])
        listing.tree_actions.toggle(listing.data[2])
        self.assertEqual(len(listing.data), 3)

    def test_short_keyboard_viewport_prioritizes_retained_composer(self):
        from toga.style.pack import NONE, PACK
        owner = self.app.chat_controller()
        prompt = owner.chat_prompt
        prompt.value = 'Visible draft'
        owner.set_chat_status('Status')
        compactable = (owner.chat_header, owner.chat_conversation_heading, owner.chat_setup_box, owner.chat_status_box)
        with patch('mobile.keyboard.picker_keyboard_visible', return_value=True) as keyboard, \
                patch.object(owner, 'chat_available_height', return_value=130):
            owner.render_chat_workspace()
            self.assertTrue(all(item.style.display == NONE for item in compactable))
            self.assertIs(prompt.parent, owner.chat_composer)
            self.assertEqual(prompt.value, 'Visible draft')
            keyboard.return_value = False
            owner.render_chat_workspace()
        self.assertTrue(all(item.style.display == PACK for item in compactable))

    def test_large_conversation_inventory_uses_one_recycled_control_and_stable_keys(self):
        app = self.app
        records = [dict(id=f'{index:032x}', title=f'Conversation {index}', updated='2026-11-02T00:00:00+00:00')
                   for index in range(1000)]
        controller = app.chat_controller()
        with patch('features.lm.mobile.ui.toga.Button', side_effect=AssertionError('No per-conversation controls')):
            controller._publish_chat_inventory(records, [])
        listing = app.chat_conversation_list
        self.assertEqual(len(listing.data), 1001)
        self.assertEqual(app.chat_conversation_buttons, [])
        self.assertIs(listing.parent, app.chat_sidebar_content)
        with patch.object(controller, 'open_chat') as open_chat:
            listing.select_index(18)
            listing.on_select()
            open_chat.assert_called_once_with(records[17]['id'])
            open_chat.reset_mock()
            app.set_chat_busy(True)
            listing.select_index(19)
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
        app.chat_drawer_open = True
        with patch.object(controller, 'open_chat') as open_chat:
            for _ in range(3):
                controller.select_chat(SimpleNamespace(value='Active'))
                listing.select_index(0)
                listing.on_select()
            open_chat.assert_not_called()
            self.assertTrue(app.chat_drawer_open)
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
