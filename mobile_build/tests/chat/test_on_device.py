"""On-device inference shares recovery/cancellation without contacting HTTP."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from features.lm.mobile.on_device import OnDeviceClient, MODELS, client_for
from features.lm.mobile.transport import ChatCancelled
from features.lm.mobile.storage import ChatStore, DEFAULT_SETTINGS
from mobile.app import LogisticsMobile


class Bridge:
    def __init__(self, status='available', snapshots=None):
        self.value = status
        self.snapshots = iter(snapshots or [dict(text='Hello', done=True)])
        self.closed = False
        self.payload = None
        self.prepared = False

    def status(self):
        return self.value

    def prepare(self, cancelled):
        self.prepared = True
        self.value = 'available'

    def start(self, payload):
        self.payload = payload

    def snapshot(self):
        return next(self.snapshots)

    def close(self):
        self.closed = True


class OnDeviceTests(unittest.TestCase):
    def test_native_stream_preserves_messages_and_emits_only_new_text(self):
        bridge = Bridge(snapshots=[dict(text='Hi', done=False), dict(text='Hi there', done=True)])
        payload = dict(messages=[dict(role='system', content='Instructions'),
            dict(role='user', content='Hello')], max_tokens=256)
        parts = []
        with patch('features.lm.mobile.on_device.native_bridge', return_value=bridge), patch('socket.socket', side_effect=AssertionError('No HTTP')):
            self.assertEqual(OnDeviceClient('apple').stream(payload, parts.append), 'stop')
        self.assertEqual(parts, ['Hi', ' there'])
        self.assertEqual(bridge.payload, payload)
        self.assertTrue(bridge.closed)

    def test_cancel_stops_native_worker_and_keeps_published_text(self):
        client = OnDeviceClient('apple')
        bridge = Bridge(snapshots=[dict(text='Partial', done=False)])
        parts = []
        def accept(text):
            parts.append(text)
            client.cancel()
        with patch('features.lm.mobile.on_device.native_bridge', return_value=bridge):
            with self.assertRaises(ChatCancelled):
                client.stream({}, accept)
        self.assertEqual(parts, ['Partial'])
        self.assertTrue(bridge.closed)

    def test_unavailable_model_never_starts_inference_or_falls_back(self):
        bridge = Bridge(status='Turn on Apple Intelligence in Settings.')
        with patch('features.lm.mobile.on_device.native_bridge', return_value=bridge), patch('socket.socket', side_effect=AssertionError('No HTTP')):
            with self.assertRaisesRegex(ValueError, 'Turn on'):
                OnDeviceClient('apple').stream({}, lambda text: None)
        self.assertIsNone(bridge.payload)
        self.assertTrue(bridge.closed)

    def test_model_assets_download_only_during_explicit_preparation(self):
        bridge = Bridge(status='downloadable')
        with patch('features.lm.mobile.on_device.native_bridge', return_value=bridge):
            self.assertEqual(OnDeviceClient('nano').models(), [MODELS['nano']])
        self.assertTrue(bridge.prepared)
        bridge = Bridge(status='downloadable')
        with patch('features.lm.mobile.on_device.native_bridge', return_value=bridge):
            with self.assertRaisesRegex(ValueError, 'Prepare Gemini Nano'):
                OnDeviceClient('nano').stream({}, lambda text: None)
        self.assertFalse(bridge.prepared)

    def test_native_errors_preserve_partial_reply_and_close(self):
        bridge = Bridge(snapshots=[dict(text='Partial', done=True, error='Context full')])
        parts = []
        with patch('features.lm.mobile.on_device.native_bridge', return_value=bridge):
            with self.assertRaisesRegex(ValueError, 'Context full'):
                OnDeviceClient('apple').stream({}, parts.append)
        self.assertEqual(parts, ['Partial'])
        self.assertTrue(bridge.closed)

    def test_profiles_are_backwards_compatible_and_provider_is_validated(self):
        profile = dict(schema=1, base_url='', model='', settings=dict(DEFAULT_SETTINGS))
        self.assertEqual(ChatStore.validate_profile(profile), profile)
        profile.update(provider='apple', model=MODELS['apple'])
        self.assertEqual(ChatStore.validate_profile(profile), profile)
        profile['provider'] = []
        with self.assertRaises(ValueError):
            ChatStore.validate_profile(profile)
        profile['provider'] = 'unknown'
        with self.assertRaises(ValueError):
            ChatStore.validate_profile(profile)
        with self.assertRaises(ValueError):
            client_for(profile)


class OnDeviceUITests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name)
        with patch('features.lm.mobile.ui.platform_provider', return_value='apple'):
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

    def test_native_model_works_without_url_or_key_and_saves_recovery_record(self):
        app = self.app
        app.chat_provider.value = MODELS['apple']
        self.assertFalse(app.chat_url.enabled)
        self.assertFalse(app.chat_model.enabled)
        with patch('features.lm.mobile.on_device.native_bridge', side_effect=lambda provider: Bridge()), patch('socket.socket', side_effect=AssertionError('No network')):
            app.loop.run_until_complete(app.refresh_chat_models())
            self.assertEqual(app.chat_model.value, MODELS['apple'])
            app.chat_controller().select_chat_provider(app.chat_provider)
            self.assertEqual(app.chat_model.value, MODELS['apple'])
            app.chat_prompt.value = 'Hello'
            app.loop.run_until_complete(app.send_chat())
        data = app.chat_store.load(app.chat_current['id'])
        self.assertEqual(data['messages'][-1]['content'], 'Hello')
        self.assertEqual(data['messages'][-1]['status'], 'complete')
        self.assertEqual(app.chat_profile['provider'], 'apple')
        self.assertLessEqual(app.chat_profile['settings']['context_tokens'], 4096)
        self.assertTrue(app.chat_send.enabled)
        app.chat_provider.value = 'OpenAI-compatible server'
        self.assertTrue(app.chat_url.enabled)
        self.assertTrue(app.chat_model.enabled)
        self.assertEqual(app.chat_model.value, '')

    def test_unavailable_device_cannot_save_a_selected_model(self):
        app = self.app
        app.chat_provider.value = MODELS['apple']
        with patch('features.lm.mobile.on_device.native_bridge', return_value=Bridge(status='Unsupported device')):
            app.loop.run_until_complete(app.refresh_chat_models())
        self.assertEqual(app.chat_model.value, '')
        self.assertFalse(app.chat_send.enabled)
        self.assertIn('Unsupported device', app.chat_status.value)
