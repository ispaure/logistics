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


class CloudRestoreRetirementTests(unittest.IsolatedAsyncioTestCase):
    async def test_terminal_retirement_cancels_independent_restore_and_drains_worker(self):
        import asyncio
        from types import SimpleNamespace

        from features.rclone.mobile.cloud_ui import CloudUI
        from features.rclone.mobile.credentials_ui import CredentialWorkflow
        from mobile.application_lifecycle import HostLifecycle

        for failed in (False, True):
            with self.subTest(failed=failed):
                entered, release, finished = threading.Event(), threading.Event(), threading.Event()
                client = SimpleNamespace(generation=1, vault=object(), cancel=Mock())

                def restore():
                    entered.set()
                    try:
                        if not release.wait(3):
                            raise TimeoutError('synthetic worker was not released')
                        if failed:
                            raise OSError('synthetic restore failure')
                        client.generation += 1
                        client.package_name = 'Saved.zip'
                        return ['Cloud']
                    finally:
                        finished.set()

                client.restore = restore
                host = SimpleNamespace(active_host=True, cloud_client=client, cloud_busy=False,
                    app=SimpleNamespace(feature_enabled=lambda name: True), loop=asyncio.get_running_loop(),
                    cloud_status=SimpleNamespace(value='Current'), prepare_cloud=Mock(),
                    set_cloud_busy=Mock(), _load_crypt_remote_names=Mock(), _publish_restored_connections=Mock())
                host.restore_cloud = CredentialWorkflow(host).restore_cloud
                host.cancel_cloud = CloudUI.cancel_cloud.__get__(host)
                lifecycle = HostLifecycle(host)
                lifecycle.stop_local_searches = Mock()
                lifecycle._stop_playback = Mock()
                lifecycle._invalidate_sessions = Mock()
                lifecycle._detach_window_callbacks = Mock()
                task = CloudUI.start_cloud_restore(host)
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    host.cancel_cloud()
                    self.assertEqual(task.cancelling(), 0)
                    self.assertEqual(host.cloud_status.value, 'Cancelling the remote request…')
                    host.cloud_status.value = 'Current'
                    lifecycle._retire_resources()
                    await asyncio.sleep(0)
                    lifecycle._retire_resources()
                    self.assertEqual(task.cancelling(), 1)
                    self.assertFalse(task.done())
                    self.assertFalse(finished.is_set())
                    self.assertIsNone(CloudUI.start_cloud_restore(host))
                    await host.restore_cloud(initial=True)
                finally:
                    release.set()
                    await asyncio.gather(task, return_exceptions=True)
                self.assertTrue(task.cancelled())
                self.assertTrue(finished.is_set())
                self.assertEqual(client.generation, 1 if failed else 2)
                self.assertEqual(host.cloud_status.value, 'Current')
                host.set_cloud_busy.assert_called_once_with(True)
                host._load_crypt_remote_names.assert_not_called()
                host._publish_restored_connections.assert_not_called()

    async def test_initial_restore_respects_busy_admission_and_client_replacement(self):
        import asyncio
        from types import SimpleNamespace

        from features.rclone.mobile.cloud_ui import CloudUI
        from features.rclone.mobile.credentials_ui import CredentialWorkflow

        client = SimpleNamespace(vault=object(), restore=Mock())
        replacement = SimpleNamespace(vault=object(), restore=Mock())
        host = SimpleNamespace(active_host=True, cloud_client=client, cloud_busy=True,
            app=SimpleNamespace(feature_enabled=lambda name: True), loop=asyncio.get_running_loop(),
            prepare_cloud=Mock(), set_cloud_busy=Mock())
        host.restore_cloud = CredentialWorkflow(host).restore_cloud
        self.assertIsNone(CloudUI.start_cloud_restore(host))
        host.set_cloud_busy.assert_not_called()

        host.cloud_busy = False
        task = CloudUI.start_cloud_restore(host)
        host.cloud_client = replacement
        await task
        client.restore.assert_not_called()
        replacement.restore.assert_not_called()
        host.set_cloud_busy.assert_called_once_with(True)
