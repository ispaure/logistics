"""Workspace ownership, recovery, stale completion and privacy invariants."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from mobile.workspace import Workspace, MAX_SESSIONS


class WorkspaceTests(unittest.TestCase):
    def test_unchanged_workspace_skips_durable_writes_but_rechecks_disk_and_view_changes(self):
        from mobile.workspace import atomic_write_json
        with TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            session = workspace.open('managed-text', 'a' * 32, 'text')
            with patch('mobile.workspace.atomic_write_json', wraps=atomic_write_json) as write:
                workspace.save()
                workspace.save()
                self.assertEqual(write.call_count, 1)
                session.view['cursor'] = 1
                workspace.save()
                self.assertEqual(write.call_count, 2)
                # Same-sized external edits must invalidate the snapshot too.
                original = workspace.path.read_text()
                workspace.path.write_text(original.replace('"cursor": 1', '"cursor": 2'))
                workspace.save()
                self.assertEqual(write.call_count, 3)
                self.assertEqual(workspace.path.read_text(), original)
                workspace.path.unlink()
                workspace.save()
                self.assertEqual(write.call_count, 4)
                target = Path(directory) / 'target.json'
                workspace.path.rename(target)
                workspace.path.symlink_to(target)
                with self.assertRaises(ValueError):
                    workspace.save()
                self.assertEqual(write.call_count, 4)

    def test_external_same_size_edit_is_detected_with_unchanged_metadata(self):
        from mobile.workspace import atomic_write_json
        with TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            session = workspace.open('managed-text', 'a' * 32, 'text')
            session.view['cursor'] = 1
            workspace.save()
            original = workspace.path.read_bytes()
            changed = original.replace(b'"cursor": 1', b'"cursor": 2')
            self.assertNotEqual(original, changed)
            self.assertEqual(len(original), len(changed))
            revision = workspace._storage_revision()
            workspace.path.write_bytes(changed)
            # Windows can cache unchanged timestamps across a rapid same-size edit.
            with patch.object(workspace, '_storage_revision', return_value=revision), \
                    patch('mobile.workspace.atomic_write_json', wraps=atomic_write_json) as write:
                workspace.save()
                self.assertEqual(write.call_count, 1)
            self.assertEqual(workspace.path.read_bytes(), original)

    def test_independent_view_state_restore_duplicate_open_and_stale_completion(self):
        with TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            a = workspace.open('managed-text', 'a' * 32, 'text', 'Same name')
            b = workspace.open('managed-text', 'b' * 32, 'markdown', 'Same name')
            a.view = dict(cursor=7, scroll_y=18)
            b.view = dict(cursor=23, markdown_mode='preview')
            self.assertIs(workspace.open('managed-text', 'a' * 32, 'text'), a)
            self.assertEqual(len(workspace.sessions), 2)
            workspace.activate(b.id)
            workspace.save()
            recovered = Workspace(Path(directory))
            self.assertEqual(recovered.active, b.id)
            self.assertEqual(recovered.sessions[a.id].view, dict(cursor=7, scroll_y=18))
            self.assertEqual(recovered.sessions[b.id].view['markdown_mode'], 'preview')
            token = workspace.token(a.id)
            self.assertFalse(workspace.close(a.id, guard=lambda session: False))
            self.assertTrue(workspace.accepts(token))
            self.assertTrue(workspace.close(a.id, guard=lambda session: True))
            self.assertFalse(workspace.accepts(token))
            reopened = workspace.open('managed-text', 'a' * 32, 'text')
            self.assertNotEqual(reopened.id, a.id)
            self.assertFalse(workspace.accepts(token))
            self.assertIn(b.id, workspace.sessions)

    def test_private_identity_title_and_view_never_enter_workspace_file(self):
        with TemporaryDirectory() as directory:
            workspace = Workspace(Path(directory))
            ordinary = workspace.open('managed-text', 'a' * 32, 'text')
            private = workspace.open('localcrypt', 'secret/path.txt', 'text', 'Sensitive name', transient=True)
            private.view = dict(cursor=9)
            private.dirty = True
            token = workspace.token(private.id)
            workspace.save()
            raw = workspace.path.read_text()
            for sensitive in ('localcrypt', 'secret', 'Sensitive', private.id):
                self.assertNotIn(sensitive, raw)
            self.assertEqual(json.loads(raw)['active'], ordinary.id)
            self.assertFalse(workspace.forget_private(guard=lambda session: not session.dirty))
            self.assertTrue(workspace.accepts(token))
            self.assertTrue(workspace.forget_private(guard=lambda session: True))
            self.assertFalse(workspace.accepts(token))

    def test_oversized_restore_is_rejected_even_when_size_metadata_is_stale(self):
        from mobile.workspace import MAX_MANIFEST
        with TemporaryDirectory() as directory:
            root = Path(directory)
            initial = Workspace(root)
            initial.open('managed-text', 'a' * 32, 'text')
            initial.save()
            payload = json.loads(initial.path.read_text())
            payload['padding'] = 'x' * MAX_MANIFEST
            initial.path.write_text(json.dumps(payload))
            before = initial.path.read_bytes()
            original_stat = Path.stat
            def stale_stat(candidate, *args, **kwargs):
                info = original_stat(candidate, *args, **kwargs)
                if candidate == initial.path:
                    fields = list(info)
                    fields[6] = 0
                    return os.stat_result(fields)
                return info
            with patch.object(Path, 'stat', stale_stat):
                restored = Workspace(root)
            self.assertEqual(restored.sessions, {})
            self.assertTrue(restored.error)
            with self.assertRaises(ValueError):
                restored.save()
            self.assertEqual(initial.path.read_bytes(), before)

    def test_invalid_manifest_is_preserved_and_session_and_view_bounds_are_enforced(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'workspace.json'
            path.write_text('{ unreadable')
            workspace = Workspace(root)
            self.assertTrue(workspace.error)
            with self.assertRaises(ValueError):
                workspace.save()
            self.assertEqual(path.read_text(), '{ unreadable')
            path.unlink()
            workspace = Workspace(root)
            for index in range(MAX_SESSIONS):
                workspace.open('managed-text', f'{index:032x}', 'text')
            with self.assertRaises(ValueError):
                workspace.open('managed-text', 'f' * 32, 'text')
            workspace.sessions[workspace.active].view = {'text': 'do not persist bytes here'}
            with self.assertRaises(ValueError):
                workspace.save()

