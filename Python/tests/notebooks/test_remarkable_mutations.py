"""Raw native metadata authority, precise deltas and stale ancestry protection."""
from copy import deepcopy
import json
import unittest

from commonUtils.testing.stages import TestStage
from features.notebooks.remarkable_mutations import plan_metadata_change, verify_metadata_revisions

TEST_STAGE = TestStage.REGRESSION
DOC = '11111111-1111-4111-8111-111111111111'
A = '22222222-2222-4222-8222-222222222222'
B = '33333333-3333-4333-8333-333333333333'
C = '44444444-4444-4444-8444-444444444444'


def record(kind='DocumentType', parent='', **extra):
    return json.dumps(dict(type=kind, parent=parent, visibleName='QA', lastModified='1000',
                           future={'nested': [1, 'preserve', True]}, **extra)).encode()


def records():
    return {DOC: record(parent=A), A: record('CollectionType'),
            B: record('CollectionType', parent=C), C: record('CollectionType')}


class RemarkableMutationTests(unittest.TestCase):
    def plan(self, source, operation, identity=DOC, **options):
        return plan_metadata_change(source, identity, operation, modified_ms=900, **options)

    def test_rename_changes_only_name_and_monotonic_time_without_mutating_source(self):
        source = records(); baseline = deepcopy(source)
        change = self.plan(source, 'rename', title='A new / display name')
        expected = json.loads(source[DOC])
        expected.update(visibleName='A new / display name', lastModified='1001')
        self.assertEqual(json.loads(change.after), expected)
        self.assertEqual(source, baseline)
        self.assertEqual(change.before, source[DOC])
        self.assertTrue(change.changed)
        self.assertEqual({guard.identity for guard in change.guards}, {DOC, A})
        verify_metadata_revisions(change, source)

    def test_move_guards_both_real_ancestries_and_preserves_unknown_fields(self):
        source = records()
        change = self.plan(source, 'move', destination=B)
        expected = json.loads(source[DOC]); expected.update(parent=B, lastModified='1001')
        self.assertEqual(json.loads(change.after), expected)
        self.assertEqual({guard.identity for guard in change.guards}, {DOC, A, B, C})
        for identity in (DOC, A, B, C):
            with self.subTest(identity=identity):
                stale = dict(source); stale[identity] += b' '
                with self.assertRaisesRegex(ValueError, 'changed'):
                    verify_metadata_revisions(change, stale)
                del stale[identity]
                with self.assertRaisesRegex(ValueError, 'changed'):
                    verify_metadata_revisions(change, stale)
        unrelated = dict(source, unrelated=b'not consumed')
        verify_metadata_revisions(change, unrelated)

    def test_display_repairs_never_authorize_invalid_native_ancestry(self):
        for parent in ('unfiled', C, 'trash', DOC):
            source = records(); source[A] = record('CollectionType', parent=parent)
            if parent == C:
                del source[C]
            with self.subTest(parent=parent), self.assertRaises(ValueError):
                self.plan(source, 'rename', title='Changed')
        source = records(); source[A] = record('CollectionType', parent=B); source[C] = record('CollectionType', parent=A)
        with self.assertRaisesRegex(ValueError, 'ancestor'):
            self.plan(source, 'rename', title='Changed')

    def test_folder_move_rejects_self_descendants_and_nonfolder_destinations(self):
        source = records(); source[B] = record('CollectionType', parent=A)
        for destination in (A, B, DOC, 'unfiled', 'trash'):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                self.plan(source, 'move', identity=A, destination=destination)
        source[B] = record('CollectionType', deleted=True)
        with self.assertRaisesRegex(ValueError, 'deleted'):
            self.plan(source, 'move', destination=B)

    def test_trash_and_explicit_restore_preserve_content_metadata_and_native_flags(self):
        source = records()
        trashed = self.plan(source, 'trash')
        expected = json.loads(source[DOC]); expected.update(parent='trash', lastModified='1001')
        self.assertEqual(json.loads(trashed.after), expected)
        self.assertNotIn('deleted', json.loads(trashed.after))
        source[DOC] = trashed.after
        for operation, options in (('rename', {'title': 'New'}), ('move', {'destination': B}), ('trash', {})):
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, 'Restore'):
                self.plan(source, operation, **options)
        restored = self.plan(source, 'restore', destination='')
        expected.update(parent='', lastModified='1002')
        self.assertEqual(json.loads(restored.after), expected)
        source[DOC] = record(parent='trash', deleted=True)
        self.assertFalse(json.loads(self.plan(source, 'restore', destination=B).after)['deleted'])
        source[DOC] = record()
        with self.assertRaisesRegex(ValueError, 'directly in Trash'):
            self.plan(source, 'restore', destination='')

    def test_noop_keeps_exact_bytes_and_does_not_advance_timestamp(self):
        source = records(); source[DOC] += b'\n  '
        for operation, options in (('rename', {'title': 'QA'}), ('move', {'destination': A})):
            with self.subTest(operation=operation):
                change = self.plan(source, operation, **options)
                self.assertFalse(change.changed)
                self.assertEqual(change.after, source[DOC])

    def test_malformed_or_ambiguous_records_fail_before_preparation(self):
        valid = json.loads(record())
        invalid = [b'[]', b'{', b'{"type":"DocumentType","type":"CollectionType"}',
                   record().replace(b'"preserve"', b'NaN'),
                   record().replace(b'"nested":', b'"duplicate":0,"duplicate":1,"nested":')]
        for field, value in [('type', 'Unknown'), ('parent', 'display-only'), ('lastModified', 1000),
                             ('lastModified', 'not a time'), ('deleted', 'false'), ('visibleName', [])]:
            invalid.append(json.dumps({**valid, field: value}).encode())
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.plan({DOC: data}, 'rename', title='New')

    def test_operation_arguments_cannot_smuggle_paths_or_ambiguous_actions(self):
        source = records()
        for title in ('', '   ', 'line\nbreak', 'x' * 513, 4):
            with self.subTest(title=title), self.assertRaises(ValueError):
                self.plan(source, 'rename', title=title)
        for operation, options in [('copy', {}), ('rename', {}), ('rename', {'title': 'QA', 'destination': A}),
                                   ('move', {}), ('trash', {'destination': B}), ('restore', {})]:
            with self.subTest(operation=operation, options=options), self.assertRaises(ValueError):
                self.plan(source, operation, **options)
        with self.assertRaises(ValueError):
            self.plan(source, 'rename', identity='../other', title='New')
        with self.assertRaises(ValueError):
            plan_metadata_change(source, DOC, 'rename', title='New', modified_ms=True)
