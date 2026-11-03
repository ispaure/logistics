"""Review fixes preserve nested ownership and surface incomplete maintenance."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from build_manager.retention import delete_owned, durable_hold, owned_entries
from logistics_build import build_retention as policy, storage_extras as extras


class StorageReviewTests(unittest.TestCase):
    def test_scratch_honors_nested_keep_and_workflow_hold(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with policy.scratch(root) as pinned:
                (pinned / 'evidence').mkdir()
                (pinned / 'evidence/.keep').touch()
            self.assertTrue((pinned / 'evidence/.keep').is_file())
            with policy.scratch(root) as held:
                durable_hold(held, 'paused-fixture')
            self.assertTrue(held.is_dir())
            with policy.scratch(root) as parent:
                child = parent / 'child'; child.mkdir()
                durable_hold(child, 'unknown-child-workflow')
            self.assertTrue(child.is_dir())


    def test_adopted_same_name_folders_are_distinct_and_nested_holds_win(self):
        with TemporaryDirectory() as directory:
            parent = Path(directory).resolve(); root = parent / 'project'; temporary = parent / 'tmp'
            first = root / 'test-results/probe'; first.mkdir(parents=True)
            second = temporary / 'probe'; second.mkdir(parents=True)
            with patch.object(extras.tempfile, 'gettempdir', return_value=str(temporary)), \
                    patch.object(extras.subprocess, 'check_output', return_value=''):
                for path in (first, second):
                    extras.enroll(root, 'directory', str(path))
                groups = dict(extras.directory_groups(root))
                self.assertEqual(len(groups), 2)
                child = first / 'work'; child.mkdir()
                durable_hold(child, 'unknown-outcome')
                spec = next(spec for spec in groups.values() if spec['root'] == first.parent)
                rows = owned_entries(**spec)
                self.assertIn('retained workflow', rows[0]['protected'])
                result = delete_owned(**spec, names=['probe'])
                self.assertFalse(result['removed'])
                self.assertTrue(child.is_dir())

    def test_adopted_build_manager_writer_is_not_considered_idle(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(); probe = root / 'test-results/probe'; probe.mkdir(parents=True)
            extras.enroll(root, 'directory', str(probe))
            _, spec = next(extras.directory_groups(root))
            with patch.object(extras.subprocess, 'check_output', return_value='python -m build_manager.cli run ' + str(probe / 'plan.json')):
                self.assertFalse(spec['eligible'](probe))

    def test_linked_markers_do_not_enroll_snapshots_or_scratch(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(); target = root / 'foreign'; target.write_text('{}')
            snapshot = root / ('a' * 64); snapshot.mkdir()
            (snapshot / '.manager-source.json').symlink_to(target)
            scratch = root / 'scratch'; scratch.mkdir()
            (scratch / '.manager-scratch').symlink_to(target)
            self.assertFalse(policy.owned_snapshot(snapshot))
            self.assertFalse(policy.owned_scratch(scratch))
            self.assertEqual(target.read_text(), '{}')

    def test_xcode_inventory_failure_is_reported_as_incomplete(self):
        with TemporaryDirectory() as directory:
            with patch.object(policy.sys, 'platform', 'darwin'), \
                    patch('logistics_build.xcode_storage.storage_group', side_effect=PermissionError('fixture denied')):
                result = policy.storage_maintenance(Path(directory).resolve())
            self.assertEqual(result['status'], 'incomplete')
            self.assertIn('Xcode', result['warnings'][0])
