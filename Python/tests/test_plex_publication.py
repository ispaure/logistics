"""Interrupted multi-file promotion preserves complete old Plex generations."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from features.plex.package_publication import PackagePublication
import features.plex.package_publication as publication


class PlexPublicationTests(unittest.TestCase):
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
        for fail_at in range(1, 8):
            with self.subTest(fail_at=fail_at), TemporaryDirectory() as directory:
                destination, staging = self.fixture(Path(directory))
                original = {p.name: p.read_bytes() for p in destination.iterdir()}
                transaction = PackagePublication(destination, sorted(staging.iterdir()), [destination / 'archive.002'])
                count = 0
                real_replace = publication.os.replace
                def replace(source, target):
                    nonlocal count
                    count += 1
                    if count == fail_at:
                        raise OSError('synthetic promotion failure')
                    return real_replace(source, target)
                with patch.object(publication.os, 'replace', side_effect=replace):
                    with self.assertRaises(OSError):
                        transaction.publish()
                self.assertEqual({p.name: p.read_bytes() for p in destination.iterdir()}, original)

    def test_failed_rollback_keeps_originals_and_journal_for_explicit_recovery(self):
        with TemporaryDirectory() as directory:
            destination, staging = self.fixture(Path(directory))
            original = {p.name: p.read_bytes() for p in destination.iterdir()}
            transaction = PackagePublication(destination, sorted(staging.iterdir()), [destination / 'archive.002'])
            real_replace = publication.os.replace
            def replace(source, target):
                if Path(source).parent == staging or Path(source).parent == transaction.recovery and Path(source).name in original:
                    raise OSError('synthetic blocked promotion/rollback')
                return real_replace(source, target)
            with patch.object(publication.os, 'replace', side_effect=replace), self.assertRaisesRegex(RuntimeError, 'needs recovery'):
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
