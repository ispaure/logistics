"""Interrupted multi-file promotion preserves complete old Plex generations."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from contextlib import contextmanager
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from features.plex.package_publication import PackagePublication
import features.plex.package_publication as publication


class PlexPublicationTests(unittest.TestCase):
    @contextmanager
    def interrupt_moves(self, failure):
        replace, rename = os.replace, publication.rename_exclusive
        def journal_move(source, target):
            failure(source, target)
            return replace(source, target)
        def member_move(source, target):
            failure(source, target)
            return rename(source, target)
        with patch.object(os, 'replace', side_effect=journal_move), \
                patch.object(publication, 'rename_exclusive', side_effect=member_move):
            yield

    def fixture(self, root):
        destination, staging = root / 'packages', root / 'stage'
        destination.mkdir()
        staging.mkdir()
        for name in ('archive.001', 'archive.002', 'settings'):
            (destination / name).write_bytes(('old ' + name).encode())
        for name in ('archive.001', 'settings'):
            (staging / name).write_bytes(('new ' + name).encode())
        return destination, staging

    def test_success_removes_obsolete_only_after_whole_generation_is_promoted(self):
        with TemporaryDirectory() as directory:
            destination, staging = self.fixture(Path(directory))
            PackagePublication(destination, sorted(staging.iterdir()), [destination / 'archive.002']).publish()
            self.assertEqual(sorted(p.name for p in destination.iterdir()), ['archive.001', 'settings'])
            self.assertEqual((destination / 'settings').read_bytes(), b'new settings')

    def test_each_promotion_or_journal_failure_restores_old_generation(self):
        for fail_at in range(1, 11):
            with self.subTest(fail_at=fail_at), TemporaryDirectory() as directory:
                destination, staging = self.fixture(Path(directory))
                original = {p.name: p.read_bytes() for p in destination.iterdir()}
                transaction = PackagePublication(destination, sorted(staging.iterdir()), [destination / 'archive.002'])
                count = 0
                def replace(source, target):
                    nonlocal count
                    count += 1
                    if count == fail_at:
                        raise OSError('synthetic promotion failure')
                with self.interrupt_moves(replace):
                    with self.assertRaises(OSError):
                        transaction.publish()
                self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, original)

    def test_failed_rollback_keeps_originals_and_journal_for_explicit_recovery(self):
        with TemporaryDirectory() as directory:
            destination, staging = self.fixture(Path(directory))
            original = {p.name: p.read_bytes() for p in destination.iterdir()}
            transaction = PackagePublication(destination, sorted(staging.iterdir()), [destination / 'archive.002'])
            def replace(source, target):
                if Path(source).parent == staging or Path(source).parent == transaction.recovery and Path(source).name in original:
                    raise OSError('synthetic blocked promotion/rollback')
            with self.interrupt_moves(replace), self.assertRaisesRegex(RuntimeError, 'needs recovery'):
                transaction.publish()
            self.assertTrue((transaction.recovery / 'journal.json').is_file())
            PackagePublication.recover(transaction.recovery)
            self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, original)

    def test_recovery_rejects_malformed_journals_without_touching_members(self):
        import json
        for state in ([], dict(schema=1, phase='prepared', originals='../escape', published={}),
                      dict(schema=1, phase='publishing', originals=[], published={'settings': [1]})):
            with self.subTest(state=state), TemporaryDirectory() as directory:
                recovery = Path(directory) / 'recovery'
                recovery.mkdir()
                (recovery / 'journal.json').write_text(json.dumps(state))
                (recovery / 'settings').write_bytes(b'preserve')
                with self.assertRaises(ValueError):
                    PackagePublication.recover(recovery)
                self.assertEqual((recovery / 'settings').read_bytes(), b'preserve')

    def test_recovery_refuses_linked_backup(self):
        import json
        with TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / 'outside'
            outside.write_bytes(b'preserve')
            recovery = root / 'recovery'
            recovery.mkdir()
            (recovery / 'settings').symlink_to(outside)
            (recovery / 'journal.json').write_text(json.dumps(dict(
                schema=1, phase='prepared', originals=['settings'], published={})))
            with self.assertRaisesRegex(RuntimeError, 'not a regular file'):
                PackagePublication.recover(recovery)
            self.assertEqual(outside.read_bytes(), b'preserve')
            self.assertFalse((root / 'settings').exists())

    def test_recovery_resumes_after_some_originals_were_restored(self):
        with TemporaryDirectory() as directory:
            destination, staging = self.fixture(Path(directory))
            original = {p.name: p.read_bytes() for p in destination.iterdir()}
            transaction = PackagePublication(destination, sorted(staging.iterdir()), [destination / 'archive.002'])
            def replace(source, target):
                source = Path(source)
                if source == staging / 'settings' or source == transaction.recovery / 'archive.002':
                    raise OSError('interrupted promotion and partial rollback')
            with self.interrupt_moves(replace), self.assertRaisesRegex(RuntimeError, 'needs recovery'):
                transaction.publish()
            self.assertEqual((destination / 'archive.001').read_bytes(), original['archive.001'])
            PackagePublication.recover(transaction.recovery)
            self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, original)

    def test_recovery_conflict_does_not_remove_other_published_members(self):
        with TemporaryDirectory() as directory:
            destination, staging = self.fixture(Path(directory))
            transaction = PackagePublication(destination, ())
            transaction.recovery.mkdir()
            names = ['archive.001', 'settings']
            for name in names:
                os.replace(destination / name, transaction.recovery / name)
                os.replace(staging / name, destination / name)
            transaction.state = dict(schema=1, phase='publishing', originals=names,
                published={name: publication._signature(destination / name) for name in names})
            transaction._save()
            (destination / 'settings').write_bytes(b'external edit')
            with self.assertRaisesRegex(RuntimeError, 'changed during recovery'):
                PackagePublication.recover(transaction.recovery)
            self.assertEqual((destination / 'settings').read_bytes(), b'external edit')
            self.assertEqual((destination / 'archive.001').read_bytes(), b'new archive.001')
            self.assertTrue(all((transaction.recovery / name).is_file() for name in names))

    def test_recovery_can_retry_failed_removal_checkpoints(self):
        for fail_at in (1, 2):
            with self.subTest(fail_at=fail_at), TemporaryDirectory() as directory:
                destination, staging = self.fixture(Path(directory))
                original = {p.name: p.read_bytes() for p in destination.iterdir()}
                transaction = PackagePublication(destination, ())
                transaction.recovery.mkdir()
                names = ['archive.001', 'settings']
                for name in names:
                    os.replace(destination / name, transaction.recovery / name)
                    os.replace(staging / name, destination / name)
                transaction.state = dict(schema=1, phase='publishing', originals=names,
                    published={name: publication._signature(destination / name) for name in names})
                transaction._save()
                real_write = publication.atomic_write_json
                count = 0
                def save(*args, **kwargs):
                    nonlocal count
                    count += 1
                    if count == fail_at:
                        raise OSError('checkpoint unavailable')
                    return real_write(*args, **kwargs)
                with patch.object(publication, 'atomic_write_json', side_effect=save), self.assertRaises(OSError):
                    PackagePublication.recover(transaction.recovery)
                PackagePublication.recover(transaction.recovery)
                self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, original)

    def test_missing_original_keeps_published_file_and_recovery_journal(self):
        with TemporaryDirectory() as directory:
            destination, staging = self.fixture(Path(directory))
            transaction = PackagePublication(destination, ())
            transaction.recovery.mkdir()
            os.replace(staging / 'settings', destination / 'settings')
            transaction.state = dict(schema=1, phase='publishing', originals=['settings'],
                published={'settings': publication._signature(destination / 'settings')})
            transaction._save()
            with self.assertRaisesRegex(RuntimeError, 'original is missing'):
                PackagePublication.recover(transaction.recovery)
            self.assertEqual((destination / 'settings').read_bytes(), b'new settings')
            self.assertTrue((transaction.recovery / 'journal.json').is_file())

    def test_failed_final_commit_checkpoint_and_partial_rollback_can_resume(self):
        import json
        with TemporaryDirectory() as directory:
            destination, staging = self.fixture(Path(directory))
            original = {p.name: p.read_bytes() for p in destination.iterdir()}
            transaction = PackagePublication(destination, sorted(staging.iterdir()), [destination / 'archive.002'])
            final_failed = False
            def replace(source, target):
                nonlocal final_failed
                source, target = Path(source), Path(target)
                if not final_failed and target == transaction.recovery / 'journal.json' and json.loads(source.read_text())['phase'] == 'committed':
                    final_failed = True
                    raise OSError('final journal publication failed')
                if source == transaction.recovery / 'archive.002':
                    raise OSError('restoration interrupted')
            with self.interrupt_moves(replace), self.assertRaisesRegex(RuntimeError, 'needs recovery'):
                transaction.publish()
            PackagePublication.recover(transaction.recovery)
            self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, original)

    def test_file_created_at_promotion_is_preserved_with_original_backups(self):
        with TemporaryDirectory() as directory:
            destination, staging = self.fixture(Path(directory))
            original = {p.name: p.read_bytes() for p in destination.iterdir()}
            transaction = PackagePublication(destination, sorted(staging.iterdir()), [destination / 'archive.002'])
            def race(source, target):
                if Path(source) == staging / 'settings':
                    Path(target).write_bytes(b'external file')
            with self.interrupt_moves(race), self.assertRaisesRegex(RuntimeError, 'needs recovery'):
                transaction.publish()
            self.assertEqual((destination / 'settings').read_bytes(), b'external file')
            self.assertEqual((destination / 'archive.001').read_bytes(), b'new archive.001')
            self.assertTrue(all((transaction.recovery / name).read_bytes() == data for name, data in original.items()))
            (destination / 'settings').unlink()
            PackagePublication.recover(transaction.recovery)
            self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, original)

    def test_file_created_at_restore_is_preserved_with_original_backup(self):
        with TemporaryDirectory() as directory:
            destination, staging = self.fixture(Path(directory))
            original = {p.name: p.read_bytes() for p in destination.iterdir()}
            transaction = PackagePublication(destination, sorted(staging.iterdir()), [destination / 'archive.002'])
            def race(source, target):
                if Path(source) == staging / 'settings':
                    raise OSError('interrupt publication')
                if Path(source) == transaction.recovery / 'archive.001':
                    Path(target).write_bytes(b'external file')
            with self.interrupt_moves(race), self.assertRaisesRegex(RuntimeError, 'needs recovery'):
                transaction.publish()
            self.assertEqual((destination / 'archive.001').read_bytes(), b'external file')
            self.assertEqual((transaction.recovery / 'archive.001').read_bytes(), original['archive.001'])
            (destination / 'archive.001').unlink()
            PackagePublication.recover(transaction.recovery)
            self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, original)

    def test_committed_cleanup_failure_keeps_valid_generation_and_cannot_roll_back(self):
        import json
        with TemporaryDirectory() as directory:
            destination, staging = self.fixture(Path(directory))
            transaction = PackagePublication(destination, sorted(staging.iterdir()), [destination / 'archive.002'])
            with patch.object(publication.shutil, 'rmtree', side_effect=OSError('cleanup unavailable')):
                with self.assertRaisesRegex(RuntimeError, 'published; recovery cleanup remains'):
                    transaction.publish()
            self.assertEqual((destination / 'archive.001').read_bytes(), b'new archive.001')
            self.assertEqual((destination / 'settings').read_bytes(), b'new settings')
            self.assertFalse((destination / 'archive.002').exists())
            self.assertEqual(json.loads((transaction.recovery / 'journal.json').read_text())['phase'], 'committed')
            with self.assertRaisesRegex(ValueError, 'uncommitted'):
                PackagePublication.recover(transaction.recovery)
