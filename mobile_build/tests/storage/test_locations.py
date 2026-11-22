"""Check pinned location persistence and navigation across local and provider roots."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from mobile.locations import Locations
from types import SimpleNamespace
from unittest.mock import Mock


class LocationTests(unittest.TestCase):
    def test_safe_identity_dedup_and_restart_without_private_names(self):
        with TemporaryDirectory() as folder:
            store = Locations(Path(folder))
            local = store.pin('local', 'notes')
            self.assertEqual(store.pin('local', 'notes'), local)
            store.pin('remote', 'public/books', 'a' * 64)
            restored = Locations(Path(folder))
            self.assertEqual(restored.items, store.items)
            for kind, path in (('crypt', 'decrypted-name'), ('local', '../outside'), ('local', '/outside')):
                with self.assertRaises(ValueError):
                    store.pin(kind, path)
            self.assertNotIn('decrypted-name', store.path.read_text())
            restored.remove(local['id'])
            self.assertEqual(len(Locations(Path(folder)).items), 1)

    def test_conflict_malformed_and_links_preserved(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            one, two = Locations(root), Locations(root)
            one.pin('local', '')
            with self.assertRaises(OSError):
                two.pin('local', 'stale')
            data = b'{invalid'
            one.path.write_bytes(data)
            bad = Locations(root)
            self.assertTrue(bad.error)
            with self.assertRaises(ValueError):
                bad.pin('local', 'new')
            self.assertEqual(one.path.read_bytes(), data)
            one.path.unlink()
            target = root / 'outside'
            target.write_bytes(data)
            one.path.symlink_to(target)
            bad = Locations(root)
            with self.assertRaises(ValueError):
                bad.pin('local', '')
            self.assertEqual(target.read_bytes(), data)


class SecondaryWindowNavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_secondary_window_routes_explicitly_deny_local_and_remote_navigation(self):
        from mobile.window_scenes import workspace_class
        workspace = workspace_class()
        host = SimpleNamespace(show_window_boundary=Mock())
        self.assertFalse(workspace.show_cloud(host))
        self.assertFalse(await workspace.show_local_location(host))
        self.assertEqual(host.show_window_boundary.call_count, 2)
