"""Credential loading stays local and refuses publication contention promptly."""
import ctypes
import json
import threading
import unittest
from unittest.mock import Mock

from features.rclone.mobile.cloud import CloudClient, CredentialBusyError


class CredentialLoadingTests(unittest.TestCase):
    def test_other_scene_cannot_queue_credential_loading(self):
        held, release = threading.Event(), threading.Event()
        def hold_publication():
            with CloudClient._state_lock:
                held.set()
                release.wait(3)
        holder = threading.Thread(target=hold_publication)
        holder.start()
        client = CloudClient.__new__(CloudClient)
        client._request = Mock()
        results = []
        def load():
            try:
                client.request('import', package='synthetic')
            except CredentialBusyError as error:
                results.append(str(error))
        loader = threading.Thread(target=load)
        try:
            self.assertTrue(held.wait(1))
            loader.start()
            loader.join(1)
            self.assertFalse(loader.is_alive(), 'credential load queued behind another scene')
            self.assertIn('retry', results[0])
            client._request.assert_not_called()
        finally:
            release.set()
            holder.join(3)
            if loader.ident is not None:
                loader.join(3)

    def test_native_busy_reply_does_not_publish_or_retry(self):
        client = CloudClient.__new__(CloudClient)
        payload = ctypes.create_string_buffer(json.dumps(dict(ok=False,
            error_code='credentials_busy', error='Stop the active operation, then retry.')).encode())
        client.call = Mock(return_value=ctypes.addressof(payload))
        client.free = Mock()
        client.publish_credentials = Mock()
        with self.assertRaisesRegex(CredentialBusyError, 'retry'):
            client.request('import', package='synthetic', session_only=True)
        client.call.assert_called_once()
        self.assertEqual(client.call.call_args.args[0], b'import')
        client.free.assert_called_once()
        client.publish_credentials.assert_not_called()
