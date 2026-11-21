"""Exercise recovery at data, credential, publication and source-version boundaries."""
from hashlib import sha256
import multiprocessing
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from features.rclone.transfers import download_recovery as recovery

TEST_STAGE = TestStage.REGRESSION


class Fixture:
    def __init__(self):
        self.data = bytes(range(251)) * 1401
        self.reads = []
        self.version = 'one'

    def stat(self):
        return dict(size=len(self.data), version=self.version, encoded=False,
                    algorithm='sha256', checksum=sha256(self.data).hexdigest())

    def read(self, version, offset, count):
        self.reads.append((offset, count))
        return self.data[offset:offset + count]


def kill_worker(directory, boundary):
    root = Path(directory)
    target = root / 'output.bin'
    queue = recovery.DownloadQueue(root, 'fixture authority', lambda: None)
    save, rename = queue.save, recovery.rename_exclusive
    def checkpoint(job):
        if boundary == 'creation' and job['state'] == 'copying':
            os._exit(73)
        save(job)
    def publish(stage, destination):
        if destination != target and boundary == 'reservation':
            os._exit(73)
        if destination == target and boundary == 'before rename':
            os._exit(73)
        rename(stage, destination)
        if destination == target and boundary == 'after rename':
            os._exit(73)
    with patch.object(queue, 'save', side_effect=checkpoint), patch.object(recovery, 'rename_exclusive', side_effect=publish):
        recovery.recover(queue, {'path': 'source'}, target, Fixture(), check=lambda: None, progress=lambda *_: None)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.target = self.root / 'output.bin'
        self.source = Fixture()
        self.unlocked = True
        self.queue = recovery.DownloadQueue(self.root, 'fixture authority', self.check)
        self.enterContext(patch.object(recovery, 'CHUNK', 65536))

    def check(self):
        if not self.unlocked:
            raise PermissionError('locked')

    def run_copy(self, stop=None):
        def progress(offset, size):
            if offset == stop:
                raise InterruptedError('interruption')
        return recovery.recover(self.queue, {'path': 'source'}, self.target, lambda: self.source,
                                check=self.check, progress=progress)

    def interrupt(self, at=3*65536):
        with self.assertRaises(InterruptedError):
            self.run_copy(at)
        job, = self.queue.jobs()
        self.assertEqual(job['offset'], at)
        self.assertFalse(self.target.exists())
        return job, recovery.stage_path(self.target, job)

    def test_second_interruption_discards_only_uncommitted_tail(self):
        job, stage = self.interrupt()
        with stage.open('ab') as stream:
            stream.write(b'uncommitted tail')
        self.queue = recovery.DownloadQueue(self.root, 'fixture authority', self.check)
        self.source.reads.clear()
        self.interrupt(at=4*65536)
        self.assertEqual(self.source.reads, [(job['offset'], 65536)])
        self.run_copy()
        self.assertEqual(self.target.read_bytes(), self.source.data)
        self.assertEqual(self.queue.jobs(), [])

    def test_changed_source_partial_and_collision_preserve_user_files(self):
        job, stage = self.interrupt()
        self.source.reads.clear()
        self.source.version = 'replacement'
        with self.assertRaisesRegex(ValueError, 'source version changed'):
            self.run_copy()
        self.source.version = 'one'
        with stage.open('r+b') as stream:
            stream.write(b'X')
        with self.assertRaisesRegex(ValueError, 'contents changed'):
            self.run_copy()
        stage.rename(stage.with_suffix('.moved'))
        stage.write_bytes(b'replacement')
        with self.assertRaisesRegex(ValueError, 'replaced'):
            self.queue.discard(job['id'], self.target)
        self.target.write_bytes(b'user file')
        with self.assertRaises(FileExistsError):
            self.run_copy()
        self.assertEqual(self.target.read_bytes(), b'user file')
        self.assertEqual(stage.read_bytes(), b'replacement')
        self.assertFalse(self.source.reads)

    def test_lock_and_remaining_space_checked_before_read(self):
        job, stage = self.interrupt()
        self.unlocked = False
        with self.assertRaises(PermissionError):
            self.queue.jobs()
        self.unlocked = True
        remaining = len(self.source.data) - job['offset']
        self.source.reads.clear()
        usage = shutil.disk_usage(self.root)
        with patch.object(shutil, 'disk_usage', return_value=usage._replace(free=remaining-1)):
            with self.assertRaisesRegex(OSError, 'free space'):
                self.run_copy()
        self.assertFalse(self.source.reads)
        with patch.object(shutil, 'disk_usage', return_value=usage._replace(free=remaining)):
            self.run_copy()

    def test_crashes_on_both_sides_of_exclusive_publication(self):
        real = recovery.rename_exclusive
        def before_publish(stage, target):
            if target == self.target:
                raise InterruptedError()
            real(stage, target)
        with patch.object(recovery, 'rename_exclusive', side_effect=before_publish):
            with self.assertRaises(InterruptedError):
                self.run_copy()
        self.assertFalse(self.target.exists())
        self.source.reads.clear()
        def published(stage, target):
            real(stage, target)
            raise InterruptedError()
        with patch.object(recovery, 'rename_exclusive', side_effect=published), \
                patch.object(self.source, 'stat', side_effect=FileNotFoundError):
            with self.assertRaises(InterruptedError):
                self.run_copy()
        with patch.object(self.source, 'stat', side_effect=FileNotFoundError):
            self.run_copy()
        self.assertEqual(self.target.read_bytes(), self.source.data)
        self.assertFalse(self.source.reads)
        self.assertEqual(self.queue.jobs(), [])
        self.assertEqual(list(self.root.glob('*.partial')), [])

    def test_interrupted_stage_creation_can_resume_or_discard(self):
        save = self.queue.save
        def before_copy(job):
            if job['state'] == 'copying':
                raise InterruptedError()
            save(job)
        for action in ('discard', 'replace', 'retry'):
            with self.subTest(action=action):
                with patch.object(self.queue, 'save', side_effect=before_copy), self.assertRaises(InterruptedError):
                    self.run_copy()
                job, = self.queue.jobs()
                self.assertEqual((job['state'], job['inode'], job['offset']), ('creating', None, 0))
                self.assertFalse(self.source.reads)
                stage = recovery.stage_path(self.target, job)
                if action == 'retry':
                    self.run_copy()
                    self.assertEqual(self.target.read_bytes(), self.source.data)
                else:
                    if action == 'replace':
                        moved = stage.rename(stage.with_suffix('.moved'))
                        stage.write_bytes(moved.read_bytes())
                        with self.assertRaisesRegex(ValueError, 'replaced'):
                            self.run_copy()
                    self.queue.discard(job['id'], self.target)
                    self.assertEqual(stage.exists(), action == 'replace')
                self.assertFalse(self.queue.jobs())

    def test_content_checksum_blocks_wrong_ranges(self):
        self.source.read = lambda version, offset, count: self.source.data[:count]
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.run_copy()
        self.assertFalse(self.target.exists())

    def test_process_loss_during_creation_and_publication(self):
        for boundary in ('reservation', 'creation', 'before rename', 'after rename'):
            with self.subTest(boundary=boundary):
                process = multiprocessing.get_context('spawn').Process(target=kill_worker, args=(self.root, boundary))
                process.start()
                try:
                    process.join(20)
                    self.assertEqual(process.exitcode, 73)
                finally:
                    if process.is_alive():
                        process.terminate()
                        process.join()
                    process.close()
                self.assertEqual(self.target.exists(), boundary == 'after rename')
                self.source.reads.clear()
                if boundary in ('reservation', 'creation'):
                    self.run_copy()
                else:
                    with patch.object(self.source, 'stat', side_effect=AssertionError('Remote opened during publication')):
                        self.run_copy()
                    self.assertFalse(self.source.reads)
                self.assertEqual(self.target.read_bytes(), self.source.data)
                self.assertFalse(self.queue.jobs())
                self.assertEqual(list(self.root.glob('*.partial')), [])
                self.target.unlink()

    def test_restart_approval_binds_progress_and_serializes_full_copy(self):
        selection = {'path': 'source'}
        job, stage = self.interrupt()
        unsupported = recovery.RestartRequired('Download from byte zero?')
        with patch.object(self.source, 'stat', side_effect=unsupported), self.assertRaisesRegex(
                recovery.RestartRequired, '196,608 verified bytes'):
            self.run_copy()
        def restart(approved, size):
            return self.queue.restart(selection, self.target, approved, size)
        with self.assertRaisesRegex(ValueError, 'Review'), restart(None, len(self.source.data)):
            self.fail('Restart without consent')
        with self.assertRaisesRegex(OSError, 'space'), restart(unsupported.checkpoint, 2**62):
            self.fail('Restart without space')
        self.assertTrue(stage.exists())
        newer, _ = self.interrupt(at=4*65536)
        with self.assertRaisesRegex(ValueError, 'advanced'), restart(unsupported.checkpoint, len(self.source.data)):
            self.fail('Stale restart approval')
        with restart(recovery.RestartRequired().bind(newer).checkpoint, len(self.source.data)):
            self.assertFalse(stage.exists())
            with self.assertRaisesRegex(ValueError, 'Another download'):
                self.run_copy()
        self.assertFalse(self.queue.jobs())

    def test_competing_writer_is_refused_before_fetch(self):
        with self.queue.writer(self.target):
            with self.assertRaisesRegex(ValueError, 'Another download'):
                self.run_copy()
        self.assertFalse(self.source.reads)
