"""Git graph projection and stored preferences remain portable model checks."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from features.git.preferences import Preferences
from features.git.graph import layout_graph
from features.git.models import Commit


class GitPreferencesTests(unittest.TestCase):
    def test_roundtrip_pin_and_subtree_mapping(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'git.json'
            prefs = Preferences(path)
            prefs.remember('/repo')
            prefs.repositories[0]['pinned'] = True
            prefs.subtrees['/repo'] = [{'prefix': 'vendor', 'url': '/upstream', 'branch': 'main'}]
            prefs.save()
            copy = Preferences(path)
            self.assertTrue(copy.repositories[0]['pinned'])
            self.assertEqual(copy.subtrees, prefs.subtrees)

    def test_malformed_settings_preserved(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'git.json'; path.write_text('broken')
            prefs = Preferences(path)
            self.assertTrue(prefs.warning)
            with self.assertRaises(OSError): prefs.save()
            self.assertEqual(path.read_text(), 'broken')

class GitGraphTests(unittest.TestCase):
    def commit(self, oid, *parents): return Commit(oid, parents, '', '', '')

    def test_merge_lanes_converge_on_shared_parent(self):
        rows = layout_graph([self.commit('merge', 'a', 'b'), self.commit('a', 'base'),
                             self.commit('b', 'base'), self.commit('base')])
        self.assertEqual(rows[0].outgoing, ((0, 0), (0, 1)))
        self.assertEqual(rows[2].outgoing, ((0, 0), (1, 0)))
        self.assertEqual(rows[-1].outgoing, ())

    def test_disconnected_histories_and_unloaded_parent(self):
        rows = layout_graph([self.commit('a', 'unloaded'), self.commit('other')])
        self.assertEqual(rows[1].lane, 1)
        self.assertEqual(rows[1].outgoing, ((0, 0),))

    def test_repeated_integration_merges_keep_first_parent_and_other_lanes_straight(self):
        commits = [self.commit('tip', 'm0', 'side')]
        for i in range(6):
            commits.extend([self.commit(f'm{i}', f'm{i + 1}', f'doc{i}'),
                            self.commit(f'doc{i}', 'base')])
        commits.extend([self.commit('m6', 'base'), self.commit('side', 'base'),
                        self.commit('base')])
        rows = layout_graph(commits)
        for commit, row in zip(commits, rows):
            if commit.oid.startswith('m') or commit.oid == 'tip':
                self.assertEqual(row.lane, 0)
                if commit.parents[0] != 'base':
                    self.assertIn((0, 0), row.outgoing)
            # Every diagonal must originate at the actual commit. Unrelated
            # branches must never weave merely because a lane opened/closed.
            for source, target in row.outgoing:
                if source != row.lane:
                    self.assertEqual(source, target)
        self.assertLessEqual(max(row.width for row in rows), 4)

    def test_empty_columns_have_no_phantom_edges_and_are_reused(self):
        rows = layout_graph([self.commit('merge', 'main', 'short', 'side'),
                             self.commit('short'), self.commit('new', 'parent'),
                             self.commit('main'), self.commit('side'),
                             self.commit('parent')])
        self.assertEqual(rows[2].lane, 1)
        self.assertEqual(rows[2].incoming, ((0, 0), (2, 2)))
        self.assertEqual(rows[2].outgoing, ((0, 0), (2, 2), (1, 1)))
        self.assertEqual(rows[4].incoming, ((1, 1), (2, 2)))
        self.assertEqual(rows[4].outgoing, ((1, 1),))

    def test_loading_more_history_preserves_existing_rows(self):
        commits = [self.commit('merge', 'main', 'side'), self.commit('main', 'base'),
                   self.commit('side', 'base'), self.commit('base')]
        rows = layout_graph(commits)
        for count in range(len(commits) + 1):
            self.assertEqual(layout_graph(commits[:count]), rows[:count])
