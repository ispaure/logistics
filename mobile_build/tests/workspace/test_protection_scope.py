"""Protection is an explicit lifetime contribution, independent of UI discovery."""
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
