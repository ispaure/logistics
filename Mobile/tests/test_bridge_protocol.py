"""Python and Go share public synthetic protocol fixtures, without real credentials."""
import ctypes
import json
from pathlib import Path
import unittest
from unittest.mock import Mock
from features.rclone.mobile.bridge_protocol import ACTIONS, decode_envelope
from features.rclone.mobile.cloud import CloudClient

ROOT = Path(__file__).resolve().parents[2]


class BridgeProtocolTests(unittest.TestCase):
    def test_action_names_match_the_shared_fixture(self):
        fixture = json.loads((ROOT / 'Mobile/rclone_bridge/protocol_contract.json').read_text())
        self.assertEqual(fixture['schema'], 1)
        self.assertEqual(ACTIONS, set(fixture['actions']))

    def test_malformed_envelope_still_frees_the_native_response(self):
        for data in (b'[]', b'{"ok":1}', b'bad JSON'):
            client = CloudClient.__new__(CloudClient)
            payload = ctypes.create_string_buffer(data)
            client.call = Mock(return_value=ctypes.addressof(payload))
            client.free = Mock()
            with self.assertRaises(ValueError):
                client.request('vault_info')
            client.free.assert_called_once()

    def test_false_response_is_a_valid_envelope_and_unknown_actions_never_call_native(self):
        self.assertEqual(decode_envelope(b'{"ok":false,"error":"fixture"}')['error'], 'fixture')
        client = CloudClient.__new__(CloudClient)
        client.call = Mock()
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            client.request('not-an-action')
        client.call.assert_not_called()
