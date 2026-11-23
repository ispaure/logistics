"""Verified folder downloads reuse member checkpoints across process restarts."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
import base64
import os
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from features.rclone.mobile.download_recovery import available_jobs, queue_command
from features.rclone.mobile.folder_recovery import FolderQueue, run_folder_download
from features.rclone.transfers.download_recovery import CHUNK, DownloadQueue, RestartRequired

TEST_STAGE = TestStage.REGRESSION


class TestCipher:
    """Use the same read/write contract without live credential packages."""

    def transform(self, data, decode=False):
        return bytes(byte ^ 0xC7 for byte in data)


class Source:
    def __init__(self, files):
        self.files = files
        self.reads = []
        self.interrupt = None
        self.unsupported = set()
        self.remote, self.identity = 'Fixture', 'native authority'
        self.generation = 1
        self.client = SimpleNamespace(request=self.request, generation=self.generation,
            package_records=({'saved': False, 'identities': {self.remote: self.identity}},))

    def check(self):
        pass

    def close(self):
        pass

    def reopen(self):
        return self

    def list(self, path, **kwargs):
        if path == 'fixture':
            return [dict(path='fixture/large', directory=True), dict(path='fixture/empty', directory=True),
                    dict(path='fixture/early.txt', directory=False)]
        if path == 'fixture/large':
            return [dict(path='fixture/large/data.bin', directory=False)]
        assert path == 'fixture/empty'
        return []

    def request(self, action, *, path, **values):
        data = self.files[path]
        digest = sha256(data).hexdigest()
        if action == 'download_stat':
            return dict(size=len(data), version=digest, encoded=False, checksum=digest, algorithm='sha256',
                        supported=path not in self.unsupported)
        self.assert_range(action, digest, **values)
        offset, count = values['offset'], values['count']
        self.reads.append((path, offset))
        if (path, offset) == self.interrupt:
            raise OSError('Connection interrupted')
        return base64.b64encode(data[offset:offset + count])

    @staticmethod
    def assert_range(action, digest, *, expected, **kwargs):
        if action != 'download_range' or expected != digest:
            raise AssertionError('Unexpected native range request.')


class StreamingSource(Source):
    def __init__(self, files):
        super().__init__(files)
        self.client.supports_download_streams = True
        self.client.cancel = lambda: None

    def request(self, action, *, path, **values):
        if action != 'download_stream':
            if action == 'download_range':
                raise AssertionError('Reopened a remote range within one file transfer.')
            return super().request(action, path=path, **values)
        data = self.files[path]
        offset = values['offset']
        if values['expected'] != sha256(data).hexdigest():
            raise ValueError('Source changed')
        self.reads.append((path, offset))
        with os.fdopen(os.dup(values['fd']), 'wb') as pipe:
            if self.interrupt and self.interrupt[0] == path:
                pipe.write(data[offset:self.interrupt[1]])
                raise OSError('Connection interrupted')
            pipe.write(data[offset:])
        return len(data) - offset


class FolderDownloadRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.source = Source({'fixture/early.txt': b'finished',
                              'fixture/large/data.bin': b'x' * CHUNK + b'end'})
        destination = self.root / 'destination'
        destination.mkdir()
        self.destination = LocalFiles(destination)
        self.records = self.root / 'private'
        self.records.mkdir()
        self.queue = FolderQueue(self.new_queue())
        self.enterContext(patch('features.rclone.mobile.folder_recovery.mobile_queue',
                                side_effect=lambda root, source: self.new_queue()))
        self.progress = []

    def new_queue(self):
        return DownloadQueue(self.records, ['fixture'], self.source.check, TestCipher())

    def download(self, key=None):
        return run_folder_download(self.records, self.source, 'fixture', self.destination, 'Saved Folder',
                                   lambda: False, lambda **values: self.progress.append(values), None, key)

    def interrupt(self):
        self.source.interrupt = ('fixture/large/data.bin', CHUNK)
        with self.assertRaisesRegex(OSError, 'interrupted'):
            self.download()
        self.source.interrupt = None
        job, = self.queue.jobs()
        self.assertEqual(job['offset'], len(self.source.files['fixture/early.txt']) + CHUNK)
        self.assertFalse((self.destination.root / 'Saved Folder').exists())
        self.assertNotIn(b'fixture/large', self.queue._path(job['id']).read_bytes())
        return job

    def test_resumes_partial_member_and_preserves_already_downloaded_members(self):
        job = self.interrupt()
        self.source = Source(self.source.files.copy())
        self.assertTrue(self.download(job['id']))
        self.assertEqual(self.source.reads, [('fixture/large/data.bin', CHUNK)])
        final = self.destination.root / 'Saved Folder'
        self.assertEqual((final / 'early.txt').read_bytes(), b'finished')
        self.assertEqual((final / 'large/data.bin').read_bytes(), self.source.files['fixture/large/data.bin'])
        self.assertTrue((final / 'empty').is_dir())
        self.assertEqual(self.queue.jobs(), [])
        self.assertEqual([path.name for path in self.destination.root.iterdir()], ['Saved Folder'])

    def test_one_stream_per_member_keeps_four_mib_checkpoints_on_disconnect(self):
        self.source = StreamingSource(self.source.files)
        job = self.interrupt()
        self.assertEqual(self.source.reads, [('fixture/early.txt', 0), ('fixture/large/data.bin', 0)])
        self.source = StreamingSource(self.source.files)
        self.assertTrue(self.download(job['id']))
        self.assertEqual(self.source.reads, [('fixture/large/data.bin', CHUNK)])
        result = self.destination.root / 'Saved Folder' / 'large' / 'data.bin'
        self.assertEqual(result.read_bytes(), self.source.files['fixture/large/data.bin'])
        self.assertFalse(self.queue.jobs())

    def test_complete_folder_checkpoint_reuses_saved_bytes_after_failed_publish(self):
        from features.rclone.transfers import download_recovery as file_recovery

        with patch('features.rclone.mobile.folder_recovery.rename_exclusive',
                   side_effect=OSError('Interrupted before directory publish')), patch.object(
                       file_recovery, '_verify_bytes', wraps=file_recovery._verify_bytes) as verified:
            with self.assertRaisesRegex(OSError, 'before directory publish'):
                self.download()
        self.assertEqual(verified.call_count, len(self.source.files))
        job, = self.queue.jobs()
        self.assertEqual(job['state'], 'publishing')
        self.assertEqual(job['offset'], job['source']['size'])
        checks = [event['verified_bytes'] for event in self.progress if 'verified_bytes' in event]
        self.assertEqual(checks[-1], job['offset'])
        self.source.reads.clear()
        self.progress.clear()
        self.assertTrue(self.download(job['id']))
        self.assertFalse(self.source.reads)
        self.assertFalse(self.queue.jobs())
        final = self.destination.root / 'Saved Folder'
        self.assertEqual((final / 'large/data.bin').read_bytes(), self.source.files['fixture/large/data.bin'])

    def test_mismatched_saved_member_cannot_publish(self):
        job = self.interrupt()
        final = self.destination.root / 'Saved Folder'
        stage = self.queue.staged(final, job)
        (stage / 'early.txt').write_bytes(b'corrupt!')
        self.source.reads.clear()
        with self.assertRaisesRegex(ValueError, 'saved folder contents differ'):
            self.download(job['id'])
        self.assertFalse(final.exists())
        self.assertFalse(self.source.reads)
        self.assertEqual(self.queue.load(job['id'])['offset'], job['offset'])

    def test_changes_after_file_verification_are_rejected_at_folder_publication(self):
        from features.rclone.mobile import folder_recovery

        def change_after_check(folder, entries, check):
            result = tree(folder, entries, check)
            (folder / 'early.txt').write_bytes(b'changed!')
            return result

        tree = folder_recovery._check_tree
        with patch.object(folder_recovery, '_check_tree', side_effect=change_after_check):
            with self.assertRaisesRegex(ValueError, 'staged folder changed before publication'):
                self.download()
        self.assertFalse((self.destination.root / 'Saved Folder').exists())
        job, = self.queue.jobs()
        self.assertEqual(job['offset'], job['source']['size'])

    def test_recovers_publication_after_the_folder_was_renamed(self):
        with patch.object(FolderQueue, 'remove', side_effect=OSError('Exit before checkpoint cleanup')):
            with self.assertRaisesRegex(OSError, 'checkpoint cleanup'):
                self.download()
        final = self.destination.root / 'Saved Folder'
        self.assertTrue(final.is_dir())
        job, = self.queue.jobs()
        self.assertEqual(job['state'], 'publishing')
        self.source.reads.clear()
        self.assertTrue(self.download(job['id']))
        self.assertEqual(self.source.reads, [])
        self.assertEqual(self.queue.jobs(), [])
        self.assertEqual((final / 'large/data.bin').read_bytes(), self.source.files['fixture/large/data.bin'])

    def test_transfers_reopens_folder_job_only_for_original_unlocked_connection(self):
        job = self.interrupt()
        self.source = Source(self.source.files.copy())
        refresh = AsyncMock()
        surface = SimpleNamespace(closed=False, model={}, update=Mock())

        async def run_mirror_work(work, operation, **kwargs):
            self.assertEqual(operation, 'download')
            self.assertEqual(kwargs['source'], 'Fixture:fixture')
            self.assertEqual(kwargs['destination'], 'Local / Saved Folder')
            result = await asyncio.to_thread(work, self.source.client, lambda: False, lambda **values: None)
            return result.status == 'complete'

        app = SimpleNamespace(cloud_client=self.source.client, private_root=self.records,
            ordinary_file_roots=lambda: {'Local': self.destination}, transfer_options=lambda: None,
            run_mirror_work=run_mirror_work)
        controller = SimpleNamespace(app=app, _progress_surface=surface, transfer_busy=False,
                                     rclone_ui=SimpleNamespace(refresh_download_directory=refresh))
        native = SimpleNamespace(remotes=SimpleNamespace(open=Mock(return_value=self.source)))
        with patch('features.rclone.mobile.download_recovery.mobile_queue', return_value=self.new_queue()), \
                patch('features.rclone.mobile.service.native_service', return_value=native):
            records = app.cloud_client.package_records
            app.cloud_client.package_records = ()
            self.assertEqual(available_jobs(app), [])
            asyncio.run(queue_command(controller, 'resume-download', {'id': job['id']}, lambda: True))
            native.remotes.open.assert_not_called()
            app.cloud_client.package_records = records
            origin, listed = available_jobs(app)[0]
            self.assertEqual((origin.remote, listed['kind'], listed['selection']['name']),
                             ('Fixture', 'folder', 'Saved Folder'))
            asyncio.run(queue_command(controller, 'resume-download', {'id': job['id']}, lambda: True))
            refresh.assert_awaited_once_with(self.destination, 'Saved Folder')
            surface.update.assert_not_called()
            self.assertEqual(available_jobs(app), [])
        self.assertEqual(self.source.reads, [('fixture/large/data.bin', CHUNK)])

    def test_reopens_cloud_crypt_job_after_destination_root_moves(self):
        self.source.remote = 'Cloud Crypt'
        self.source.client.package_records = ({'saved': False, 'identities': {'Cloud Crypt': self.source.identity}},)
        job = self.interrupt()
        self.source.reads.clear()
        moved = self.root / 'relocated storage'
        self.destination.root.rename(moved)
        self.destination = LocalFiles(moved)

        async def run_mirror_work(work, operation, **kwargs):
            self.assertEqual(kwargs['source'], 'Cloud Crypt:fixture')
            result = await asyncio.to_thread(work, self.source.client, lambda: False, lambda **values: None)
            return result.status == 'complete'

        app = SimpleNamespace(cloud_client=self.source.client, private_root=self.records,
            ordinary_file_roots=lambda: {'On My Phone': self.destination}, transfer_options=lambda: None,
            run_mirror_work=run_mirror_work)
        surface = SimpleNamespace(closed=False)
        refresh = AsyncMock()
        controller = SimpleNamespace(app=app, _progress_surface=surface, transfer_busy=False,
                                     rclone_ui=SimpleNamespace(refresh_download_directory=refresh))
        native = SimpleNamespace(remotes=SimpleNamespace(open=Mock(return_value=self.source)))
        with patch('features.rclone.mobile.download_recovery.mobile_queue', return_value=self.new_queue()), \
                patch('features.rclone.mobile.service.native_service', return_value=native):
            asyncio.run(queue_command(controller, 'resume-download', {'id': job['id']}, lambda: True))
        self.assertEqual(self.source.reads, [('fixture/large/data.bin', CHUNK)])
        self.assertEqual((moved / 'Saved Folder' / 'large' / 'data.bin').read_bytes(),
                         self.source.files['fixture/large/data.bin'])
        self.assertFalse(self.queue.jobs())
        refresh.assert_awaited_once_with(self.destination, 'Saved Folder')

    def test_discard_unavailable_folder_retires_only_the_queue_entry(self):
        job = self.interrupt()
        old = self.destination.root
        moved = self.root / 'detached storage'
        old.rename(moved)
        # A replacement directory at the same path must not be touched.
        old.mkdir()
        replacement = self.queue.staged(old / 'Saved Folder', job)
        replacement.mkdir()
        (replacement / 'Do not delete').write_bytes(b'Unrelated bytes')
        dialog = AsyncMock(side_effect=[False, True])
        app = SimpleNamespace(cloud_client=self.source.client, private_root=self.records,
            ordinary_file_roots=lambda: {'On My Phone': self.destination},
            main_window=SimpleNamespace(dialog=dialog))
        controller = SimpleNamespace(app=app, _progress_surface=SimpleNamespace(closed=False), transfer_busy=False)
        native = SimpleNamespace(remotes=SimpleNamespace(open=Mock(return_value=self.source)))
        with patch('features.rclone.mobile.download_recovery.mobile_queue', return_value=self.new_queue()), \
                patch('features.rclone.mobile.service.native_service', return_value=native):
            asyncio.run(queue_command(controller, 'discard-download', {'id': job['id']}, lambda: True))
            self.assertEqual(self.queue.jobs(), [job])
            asyncio.run(queue_command(controller, 'discard-download', {'id': job['id']}, lambda: True))
        self.assertFalse(self.queue.jobs())
        self.assertEqual((replacement / 'Do not delete').read_bytes(), b'Unrelated bytes')
        original = moved / replacement.name
        self.assertTrue((original / 'early.txt').is_file())
        self.assertEqual(dialog.await_count, 2)

    def test_browser_keeps_dotfiles_but_hides_checkpoint_subtrees(self):
        from services.documents.locations import visible_transfer_rows
        stage = '.logistics-' + 'a' * 32 + '.00000000.partial'
        rows = [dict(path=stage), dict(path='subfolder/' + stage + '/unpublished.txt'),
                dict(path='.keep'), dict(path='.download-4b9b')]
        self.assertEqual(list(visible_transfer_rows(self.destination, rows)), rows[2:])
        self.assertEqual(list(visible_transfer_rows(SimpleNamespace(remote_storage=True), rows)), rows)

    def test_changed_source_requires_review_and_discard_leaves_existing_folder(self):
        job = self.interrupt()
        self.source.files['fixture/early.txt'] = b'replaced'
        with self.assertRaisesRegex(ValueError, 'remote folder changed'):
            self.download(job['id'])
        final = self.destination.root / 'Saved Folder'
        final.mkdir()
        (final / 'note').write_bytes(b'user data')
        self.queue.discard(job['id'], final, expected=(job['id'], job['offset'], job['digest']))
        self.assertEqual((final / 'note').read_bytes(), b'user data')
        self.assertFalse(self.queue.staged(final, job).exists())
        self.assertEqual(self.queue.jobs(), [])

    def test_unsupported_source_requests_one_shot_before_creating_checkpoint(self):
        self.source.unsupported = {'fixture/large/data.bin'}
        with self.assertRaisesRegex(RestartRequired, 'without resume'):
            self.download()
        self.assertFalse(list(self.destination.root.iterdir()))
        self.assertEqual(self.queue.jobs(), [])
