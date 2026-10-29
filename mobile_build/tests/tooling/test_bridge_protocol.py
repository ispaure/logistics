"""Python and Go share public synthetic protocol fixtures, without real credentials."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import ctypes
import json
from pathlib import Path
import unittest
from unittest.mock import Mock
from features.rclone.mobile.bridge_protocol import ACTIONS, decode_envelope, request_limit_bytes, mirror_info, mirror_progress
from features.rclone.mobile.cloud import CloudClient, CredentialBusyError

ROOT = Path(__file__).resolve().parents[3]


class BridgeProtocolTests(unittest.TestCase):
    def test_action_names_match_the_shared_fixture(self):
        fixture = json.loads((ROOT / 'mobile_build/rclone_bridge/protocol_contract.json').read_text())
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

    def test_busy_response_without_optional_error_text_is_typed_and_freed(self):
        client = CloudClient.__new__(CloudClient)
        payload = ctypes.create_string_buffer(b'{"ok":false,"error_code":"credentials_busy"}')
        client.call = Mock(return_value=ctypes.addressof(payload))
        client.free = Mock()
        with self.assertRaisesRegex(CredentialBusyError, 'Credentials are in use'):
            client.request('import')
        client.free.assert_called_once()


    def test_request_limits_match_shared_contract_including_intentional_native_differences(self):
        fixture = json.loads((ROOT / 'mobile_build/rclone_bridge/protocol_contract.json').read_text())
        for limit in fixture['request_limits']:
            with self.subTest(action=limit['action']):
                self.assertEqual(request_limit_bytes(limit['action']), limit['python'])

    def test_typed_operations_refuse_malformed_results_at_the_boundary(self):
        for value in (None, {}, {'identity': 'a' * 64, 'cipher_identity': '', 'crypt': 1, 'prefix': ''}):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'mirror_info'):
                    mirror_info(Mock(request=Mock(return_value=value)), 'Remote', '')
        with self.assertRaisesRegex(ValueError, 'mirror_progress'):
            mirror_progress(Mock(request=Mock(return_value=dict(phase='Copying', done=True, total=2))), 'run')

    def test_malformed_success_result_frees_native_response_before_reporting_error(self):
        client = CloudClient.__new__(CloudClient)
        payload = ctypes.create_string_buffer(b'{"ok":true,"result":{"phase":"Copying","done":false,"total":3}}')
        client.call = Mock(return_value=ctypes.addressof(payload))
        client.free = Mock()
        with self.assertRaisesRegex(ValueError, 'mirror_progress'):
            client.request('mirror_progress', run='synthetic')
        client.free.assert_called_once()

    def test_credential_diagnostics_never_include_exception_text_or_secrets(self):
        from features.rclone.diagnostics import report_failure
        from unittest.mock import patch
        try:
            raise ValueError('synthetic-secret-token')
        except ValueError as error:
            with patch('commonUtils.runtime.diagnostics.log') as log:
                report_failure('restore saved credentials', error)
        text = str(log.call_args)
        self.assertIn('ValueError', text)
        self.assertIn('test_credential_diagnostics', text)
        self.assertNotIn('synthetic-secret-token', text)

    def test_diagnostic_sink_failure_cannot_replace_the_credential_error(self):
        from features.rclone.diagnostics import report_failure
        from unittest.mock import patch
        with patch('commonUtils.runtime.diagnostics.log', side_effect=OSError('log unavailable')):
            report_failure('restore saved credentials', ValueError('synthetic-secret-token'))
