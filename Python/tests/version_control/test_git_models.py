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
