"""Mobile LM contracts with synthetic loopback responses and private records."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from features.lm.domain import build_request, message
from features.lm.mobile.storage import ChatStore, DEFAULT_SETTINGS, export_chat
from logisticsmobile.chat_fixture import fixture_server
from features.lm.mobile.transport import ChatClient, ChatCancelled


class MobileChatTests(unittest.TestCase):
    def test_mobile_chat_records_recover_drafts_interruptions_and_reject_conflicts(self):
        with TemporaryDirectory() as directory:
            store = ChatStore(Path(directory).resolve())
            data = store.new()
            data['draft'] = 'recover me'
            data['messages'] = [message('user', 'Hello'), message('assistant', 'partial', 'streaming')]
            with patch('os.link', side_effect=PermissionError('No hard links')):
                store.save(data)
            loaded = store.load(data['id'])
            self.assertEqual(loaded['draft'], 'recover me')
            self.assertEqual(loaded['messages'][-1]['status'], 'interrupted')
            stale = deepcopy(loaded)
            store.save(loaded)
            with self.assertRaises(OSError):
                store.save(stale)
            self.assertIn('partial', export_chat(loaded))
            store.path(data['id']).write_bytes(b'broken record')
            self.assertTrue(store.items()[1])
            with self.assertRaises(ValueError):
                store.save(loaded)
            self.assertEqual(store.path(data['id']).read_bytes(), b'broken record')

    def test_mobile_chat_refresh_and_stream_use_only_configured_endpoint(self):
        with patch('socket.getfqdn', side_effect=AssertionError('Loopback fixtures must not perform DNS')), \
                fixture_server() as (url, started, release, requests):
            client = ChatClient(url, 'synthetic-key')
            self.assertEqual(client.models(), ['fixture-model'])
            data = dict(model='fixture-model', settings=DEFAULT_SETTINGS, profile_id='mobile',
                        messages=[message('user', 'Hello')])
            payload, metadata = build_request(data)
            fragments = []
            self.assertEqual(client.stream(payload, fragments.append), 'stop')
            self.assertEqual(''.join(fragments), 'Native fixture reply')
            self.assertEqual([r[1] for r in requests], ['/v1/models', '/v1/chat/completions'])
            self.assertEqual(requests[-1][2], 'Bearer synthetic-key')
            self.assertNotIn('tools', requests[-1][3])
            self.assertEqual(metadata['omitted_turns'], 0)

    def test_mobile_chat_cancel_interrupts_blocked_read_and_rejects_redirects_tools(self):
        with fixture_server(mode='pause') as (url, started, release, requests):
            client = ChatClient(url)
            errors = []
            def stream():
                try:
                    client.stream({'model': 'fixture-model'}, lambda text: None)
                except Exception as error:
                    errors.append(error)
            thread = Thread(target=stream)
            thread.start()
            self.assertTrue(started.wait(5))
            # Simulate Windows retaining a blocked file-backed socket read:
            # cancellation must not depend on shutdown waking that reader.
            with patch('socket.socket.shutdown', return_value=None):
                client.cancel()
            thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertIsInstance(errors[0], ChatCancelled)
        for mode in ('redirect', 'tools', 'incomplete'):
            with fixture_server(mode=mode) as (url, started, release, requests):
                client = ChatClient(url)
                with self.assertRaises(ValueError):
                    client.models() if mode == 'redirect' else client.stream({}, lambda text: None)
                if mode == 'redirect':
                    self.assertEqual(len(requests), 1)

    def test_mobile_chat_profile_never_accepts_stored_api_keys(self):
        with TemporaryDirectory() as directory:
            store = ChatStore(Path(directory).resolve())
            profile, original = store.profile()
            profile.update(base_url='https://example.invalid/v1', model='fixture-model')
            profile, original = store.save_profile(profile, original)
            self.assertNotIn('api_key', store.profile()[0])
            with self.assertRaises(ValueError):
                store.save_profile(dict(profile, api_key='never persist this'), original)
            with self.assertRaises(ValueError):
                ChatClient('https://user:secret@example.invalid/v1')
            with self.assertRaises(ValueError):
                ChatClient(profile['base_url'], 'key\r\nInjected: header')
