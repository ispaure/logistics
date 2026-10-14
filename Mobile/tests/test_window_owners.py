import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from logisticsmobile.window_owners import WindowOwners
from logisticsmobile.workspace import Workspace
from pathlib import Path
import toga
from logisticsmobile.app import LogisticsMobile


class WindowOwnerTests(unittest.TestCase):
    def test_independent_host_callbacks_and_restoration(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            manager = app.scene_manager
            manager.window_class = toga.Window
            child = manager.make_host('b' * 32)
            self.assertNotEqual(app.current.id, child.current.id)
            self.assertIsNot(app.routes, child.routes)
            child.editor.value = 'Child draft'
            app.editor.value = 'Primary draft'
            self.assertFalse(child.open_document(app.current.id))
            self.assertEqual(child.editor.value, 'Child draft')
            child.show_settings()
            self.assertTrue(child.checkpoint())
            key = child.current.id
            manager.disconnect(child)
            restored = manager.make_host('b' * 32)
            self.assertEqual(restored.current.id, key)
            self.assertEqual(restored.editor.value, 'Child draft')
            self.assertEqual(restored.native_host.state.destination, 'settings')
            self.assertEqual(app.editor.value, 'Primary draft')

    def test_duplicate_writer_private_boundary_and_release(self):
        with TemporaryDirectory() as directory:
            owners = WindowOwners()
            a, b = Workspace(directory + '/a'), Workspace(directory + '/b')
            for key, workspace in [('a', a), ('b', b)]:
                owners.attach(key, SimpleNamespace(workspace=workspace))
                workspace.window_owners, workspace.window_id = owners, key
            first = a.open('managed-text', 'a' * 32, 'text')
            with self.assertRaisesRegex(ValueError, 'another window'):
                b.open('managed-text', 'a' * 32, 'text')
            with self.assertRaisesRegex(ValueError, 'protected'):
                b.open('provider-session', 'secret', 'text', transient=True)
            self.assertFalse(a.close(first.id, guard=lambda value: False))
            self.assertEqual(owners.writers[first.identity], 'a')
            self.assertTrue(a.close(first.id, guard=lambda value: True))
            second = b.open('managed-text', 'a' * 32, 'text')
            owners.detach('b')
            self.assertNotIn(second.identity, owners.writers)
