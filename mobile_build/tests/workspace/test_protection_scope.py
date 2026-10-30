"""Protection is an explicit lifetime contribution, independent of UI discovery."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from types import SimpleNamespace
from services.protection import ProtectionScope


class ProtectionScopeTests(unittest.TestCase):
    def test_credentials_protect_process_before_any_window_exists(self):
        credentials = [object()]
        scope = ProtectionScope(lambda: tuple(credentials))
        self.assertTrue(scope.protected())
        window = scope.window()
        self.assertEqual(window.gates(), tuple(credentials))
        credentials.clear()
        self.assertFalse(scope.protected())

    def test_retained_draft_survives_credential_removal_and_release_is_idempotent(self):
        gate = object()
        credentials = [gate]
        scope = ProtectionScope(lambda: tuple(credentials))
        first, second = scope.window(), scope.window()
        draft = SimpleNamespace(gate=gate)
        release = first.register(draft, lambda: (draft.gate,))
        self.assertEqual(first.gates(), (gate,))  # One challenge, two contributions.
        credentials.clear()
        self.assertTrue(scope.protected())
        self.assertEqual(second.gates(), ())  # Another scene has no local challenge.
        release()
        release()
        self.assertFalse(scope.protected())

    def test_replacement_and_host_disposal_do_not_release_another_window(self):
        scope = ProtectionScope(lambda: ())
        first, second = scope.window(), scope.window()
        owner = object()
        old, new = object(), object()
        stale_release = first.register(owner, lambda: (old,))
        first.register(owner, lambda: (new,))
        stale_release()
        second.register(object(), lambda: (old,))
        self.assertEqual(first.gates(), (new,))
        first.dispose()
        first.dispose()
        self.assertTrue(scope.protected())
        with self.assertRaises(ValueError):
            first.register(owner, lambda: (new,))
        second.dispose()
        self.assertFalse(scope.protected())

    def test_registered_sources_are_independent_and_stale_release_cannot_remove_replacement(self):
        scope = ProtectionScope()
        source, other = object(), object()
        first, second = object(), object()
        gates = lambda: (first,)
        stale = scope.register_credentials(source, gates)
        release = scope.register_credentials(source, gates)
        other_release = scope.register_credentials(other, lambda: (second,))
        stale()
        self.assertEqual(scope.window().gates(), (first, second))
        release()
        self.assertEqual(scope.credentials(), (second,))
        other_release()
        self.assertFalse(scope.protected())

    def test_application_composes_shared_scope_and_credentials_publish_before_ui_observers(self):
        from mobile.protection import for_credentials
        from features.rclone.mobile.credential_state import NativeCredentialState
        state = NativeCredentialState()
        scope = for_credentials(state)
        self.assertIs(for_credentials(state), scope)
        self.assertFalse(hasattr(state, 'protection'))
        self.assertIsNot(for_credentials(NativeCredentialState()), scope)
        events = []
        class Observer:
            def credentials_changed(self):
                events.append(scope.active)
        observer = Observer()
        state.observers.add(observer)
        info = {'epoch': 1, 'packages': [{'package_name': 'Fixture.zip', 'saved': False}]}
        state.publish('import', {'package_name': 'Fixture.zip', 'password': 'fixture', 'session_only': True}, info)
        self.assertTrue(scope.protected())
        self.assertEqual(events, [True])
        window = scope.window()
        self.assertEqual(window.gates(), state.privacy_gates())
        state.publish('clear', {}, {'epoch': 2})
        self.assertEqual(events, [True, False])
        self.assertFalse(scope.protected())
        window.dispose()

    def test_application_scope_accepts_a_non_rclone_source(self):
        from threading import RLock
        from weakref import WeakSet
        from mobile.protection import for_credentials
        class Source:
            lock = RLock()
            def __init__(self):
                self.protection_observers = WeakSet()
                self.gates = [object()]
            def privacy_gates(self):
                return tuple(self.gates)
        source = Source()
        scope = for_credentials(source)
        self.assertTrue(scope.active)
        source.gates.clear()
        for observer in tuple(source.protection_observers):
            observer.credentials_changed()
        self.assertFalse(scope.active)

    def test_failed_protection_effect_does_not_skip_document_publication_observers(self):
        from mobile.protection import for_credentials
        from features.rclone.mobile.credential_state import NativeCredentialState
        state = NativeCredentialState()
        scope = for_credentials(state)
        events = []
        class Listener:
            def protection_changed(self, active):
                raise RuntimeError('fixture effect failure')
        class Observer:
            def credentials_changed(self):
                events.append(scope.active)
        listener, observer = Listener(), Observer()
        scope.listeners.add(listener)
        state.document_observers.add(observer)
        with self.assertRaisesRegex(RuntimeError, 'fixture effect failure'):
            state.publish('import', {'package_name': 'Fixture.zip', 'password': 'fixture', 'session_only': True},
                          {'epoch': 1, 'packages': [{'package_name': 'Fixture.zip', 'saved': False}]})
        self.assertTrue(scope.protected())
        self.assertEqual(events, [True])


    def test_gate_suppliers_can_query_the_scope_from_another_thread(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import get_ident
        publisher = get_ident()
        scope = ProtectionScope()
        query = False
        with ThreadPoolExecutor(max_workers=1) as pool:
            def gates():
                if query and get_ident() == publisher:
                    return pool.submit(scope.credentials).result(timeout=2)
                return ()
            scope.register_credentials(self, gates)
            query = True
            scope.changed()

    def test_slow_older_snapshot_cannot_replace_a_newer_protection_update(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event, get_ident
        publisher = get_ident()
        entered, release = Event(), Event()
        credentials = []
        def gates():
            snapshot = tuple(credentials)
            if get_ident() != publisher:
                entered.set()
                if not release.wait(2):
                    raise AssertionError('A blocked snapshot prevented another publication')
            return snapshot
        scope = ProtectionScope(gates)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(scope.changed)
            try:
                self.assertTrue(entered.wait(2))
                credentials.append(object())
                scope.changed()
            finally:
                release.set()
            pending.result(timeout=2)
        self.assertTrue(scope.active)
        self.assertTrue(scope.protected())

class AuthenticationTests(unittest.TestCase):
    def test_manual_lock_and_failed_wifi_cannot_be_revived_by_late_success(self):
        from services.session_auth import ResumePassword
        gate = ResumePassword('secret')
        gate.lock(reason='lifecycle')
        revision = gate.revision
        gate.deny_wifi(revision)
        gate.lock(reason='lifecycle')  # A duplicate notification is not a new waiver.
        self.assertFalse(gate.waive_lifecycle(revision))
        gate.lock()
        self.assertFalse(gate.waive_lifecycle(gate.revision))
        self.assertFalse(gate.authorize(revision))
        self.assertTrue(gate.authorize(gate.revision))

    def test_credential_observers_can_read_from_another_thread(self):
        from concurrent.futures import ThreadPoolExecutor
        from features.rclone.mobile.credential_state import NativeCredentialState
        state = NativeCredentialState()
        with ThreadPoolExecutor(max_workers=1) as pool:
            class Observer:
                def credentials_changed(self):
                    self.gates = pool.submit(state.privacy_gates).result(timeout=2)
            observer = Observer()
            state.observers.add(observer)
            state.publish('clear', {}, {'epoch': 1})
            self.assertEqual(observer.gates, ())
