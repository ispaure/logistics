"""Native IDs, malformed ancestry and duplicate labels in a read-only snapshot."""
import unittest

from commonUtils.runtime.operations import OperationCancelled
from commonUtils.testing.stages import TestStage
from features.notebooks.remarkable_store import ROOT, UNFILED, TabletSnapshot

TEST_STAGE = TestStage.REGRESSION


def identity(number):
    return f'10000000-0000-4000-8000-{number:012d}'


def entry(name, parent='', *, folder=False, **values):
    return dict(type='CollectionType' if folder else 'DocumentType', visibleName=name, parent=parent, **values)


class TabletSnapshotTests(unittest.TestCase):
    def test_empty_folders_duplicate_names_and_nested_documents_keep_ids(self):
        snapshot = TabletSnapshot.from_metadata({identity(1): entry('Same', folder=True),
            identity(2): entry('Same', folder=True), identity(3): entry('Empty', identity(1), folder=True),
            identity(4): entry('Notebook', identity(1)), identity(5): entry('Notebook', identity(2)),
            identity(6): entry('Root')})
        self.assertEqual(snapshot.children[ROOT], (identity(1), identity(2), identity(6)))
        self.assertEqual(snapshot.children[identity(3)], ())
        self.assertEqual(snapshot.ancestry(identity(4)), (ROOT, identity(1), identity(4)))
        self.assertEqual(snapshot.entries[identity(4)].title, snapshot.entries[identity(5)].title)

    def test_deleted_and_trashed_ancestors_omit_entire_subtrees(self):
        snapshot = TabletSnapshot.from_metadata({identity(1): entry('Deleted', folder=True, deleted=True),
            identity(2): entry('Child', identity(1)), identity(3): entry('Trash folder', 'trash', folder=True),
            identity(4): entry('Child', identity(3)), identity(5): entry('Visible')})
        self.assertEqual(set(snapshot.entries), {ROOT, identity(5)})

    def test_invalid_ancestry_keeps_items_in_display_only_group(self):
        snapshot = TabletSnapshot.from_metadata({identity(1): entry('Orphan', identity(99)),
            identity(2): entry('Invalid', []), identity(3): entry('Document'),
            identity(4): entry('Not a folder', identity(3))})
        self.assertEqual(set(snapshot.children[UNFILED]), {identity(1), identity(2), identity(4)})
        self.assertTrue(snapshot.entries[UNFILED].directory)
        self.assertIn('Display-only', snapshot.entries[UNFILED].issue)

    def test_cycles_break_deterministically_without_changing_metadata(self):
        metadata = {identity(1): entry('A', identity(2), folder=True),
                    identity(2): entry('B', identity(1), folder=True),
                    identity(3): entry('Child', identity(2)), identity(4): entry('Self', identity(4), folder=True)}
        forward = TabletSnapshot.from_metadata(metadata)
        reverse = TabletSnapshot.from_metadata(dict(reversed(list(metadata.items()))))
        self.assertEqual(forward.entries, reverse.entries)
        self.assertEqual(forward.ancestry(identity(3)), (ROOT, UNFILED, identity(1), identity(2), identity(3)))
        self.assertEqual(forward.entries[identity(4)].parent, UNFILED)
        self.assertEqual(metadata[identity(1)]['parent'], identity(2))

    def test_filter_retains_ancestors_and_matching_folder_contents(self):
        snapshot = TabletSnapshot.from_metadata({identity(1): entry('Projects', folder=True),
            identity(2): entry('Nested', identity(1), folder=True), identity(3): entry('Journal', identity(2)),
            identity(4): entry('Elsewhere'), identity(5): entry('Other', identity(1))})
        self.assertEqual(snapshot.visible('journal'), {ROOT, identity(1), identity(2), identity(3)})
        self.assertEqual(snapshot.visible('PROJECTS'), {ROOT, identity(1), identity(2), identity(3), identity(5)})
        self.assertEqual(snapshot.visible('Elsewhere', identity(1)), {ROOT, identity(1)})
        self.assertIsNone(snapshot.visible(''))

    def test_deep_hierarchy_is_iterative_and_cancelled_listing_aborts(self):
        metadata = {identity(i): entry(str(i), identity(i - 1) if i > 1 else '', folder=True) for i in range(1, 1501)}
        snapshot = TabletSnapshot.from_metadata(metadata)
        self.assertEqual(len(snapshot.ancestry(identity(1500))), 1501)
        with self.assertRaises(OperationCancelled):
            TabletSnapshot.from_metadata(metadata, cancelled=lambda: True)

    def test_snapshot_does_not_accept_unknown_types_or_mutable_metadata(self):
        metadata = {identity(1): entry('Original'), identity(2): dict(type='Unknown'), 'unsafe': entry('Bad ID')}
        snapshot = TabletSnapshot.from_metadata(metadata)
        metadata[identity(1)]['visibleName'] = 'Changed'
        self.assertEqual(set(snapshot.entries), {ROOT, identity(1)})
        self.assertEqual(snapshot.entries[identity(1)].title, 'Original')
        with self.assertRaises(TypeError):
            snapshot.entries[identity(1)] = None
