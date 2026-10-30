"""Credential loading stays local and refuses publication contention promptly."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
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
            with CloudClient.credential_state.lock:
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

    def test_real_request_notifies_after_releasing_the_credential_publication_lock(self):
        from concurrent.futures import ThreadPoolExecutor
        from features.rclone.mobile.credential_state import NativeCredentialState
        from mobile.protection import for_credentials
        client = CloudClient.__new__(CloudClient)
        state = client.credential_state = NativeCredentialState()
        scope = for_credentials(state)
        payload = ctypes.create_string_buffer(json.dumps(dict(ok=True, result=[], credential_state=dict(
            epoch=1, packages=[dict(package_name='Fixture.zip', saved=False)]))).encode())
        client.call, client.free = Mock(return_value=ctypes.addressof(payload)), Mock()
        with ThreadPoolExecutor(max_workers=1) as pool:
            class Observer:
                def credentials_changed(self):
                    self.gates = pool.submit(state.privacy_gates).result(timeout=2)
                    self.protected = scope.active
            observer = Observer()
            state.observers.add(observer)
            client.request('import', package='synthetic', package_name='Fixture.zip',
                           password='fixture', session_only=True)
            self.assertEqual(observer.gates, state.privacy_gates())
            self.assertTrue(observer.protected)

    def test_clear_and_package_forget_notify_after_outer_lock_and_vault_work(self):
        from concurrent.futures import ThreadPoolExecutor
        from types import SimpleNamespace
        from features.rclone.mobile.credential_state import NativeCredentialState
        for operation in ('clear', 'forget_package', 'service_clear', 'service_forget_package'):
            with self.subTest(operation=operation):
                client = CloudClient.__new__(CloudClient)
                state = client.credential_state = NativeCredentialState()
                client.vault = SimpleNamespace(unlock=Mock(return_value={}), forget=Mock())
                payload = ctypes.create_string_buffer(json.dumps(dict(ok=True,
                    result=dict(package_name='Remaining.zip'),
                    credential_state=dict(epoch=1, packages=[]))).encode())
                client.call, client.free = Mock(return_value=ctypes.addressof(payload)), Mock()
                with ThreadPoolExecutor(max_workers=1) as pool:
                    class Observer:
                        def credentials_changed(self):
                            self.gates = pool.submit(state.privacy_gates).result(timeout=.5)
                            self.name = client.package_name
                            self.erased = client.vault.forget.called
                    observer = Observer()
                    state.observers.add(observer)
                    from features.rclone.mobile.service import native_service
                    from features.rclone.mobile.credential_retention import NativeCredentialForget
                    if operation in ('clear', 'service_clear'):
                        if operation == 'clear':
                            client.clear()
                        else:
                            native_service(client).credentials.forget()
                        self.assertTrue(observer.erased)
                        self.assertEqual(observer.name, '')
                    else:
                        if operation == 'forget_package':
                            client.forget_package('Fixture.zip')
                        else:
                            from pathlib import Path
                            native_service(client).credentials.forget(NativeCredentialForget(
                                lambda: None, Path('.'), 'Fixture.zip'))
                        self.assertEqual(observer.name, 'Remaining.zip')
                    self.assertEqual(observer.gates, ())
