"""Shared review cancellation, stale results and actual CLI dry-run behavior."""
from pathlib import Path
import os
from tempfile import TemporaryDirectory
from threading import Event
import unittest

from features.rclone.transfers.review import ReviewRequest, ReviewScan, unchanged
from features.rclone.transfers.review_cli import scanner
from features.rclone.session import NULL_CONFIG


class ReviewTests(unittest.TestCase):
    def test_large_reviews_complete_for_emitted_and_replaced_snapshots(self):
        rows = [('add', f'folder/{index}.txt') for index in range(10001)]
        rows += [('cleanup', f'generated/{index}/.DS_Store') for index in range(10001)]
        for replace in (False, True):
            with self.subTest(replace=replace):
                def scanner(emit, cancelled):
                    if replace:
                        emit.replace(rows)
                    else:
                        for kind, path in rows:
                            emit(kind, path)
                    return 'large-review-revision'
                result = self.finish(ReviewScan(scanner))
                self.assertTrue(result.complete)
                self.assertEqual(set(result.changes), set(rows))

    def test_cli_retry_discards_failed_attempt_and_retains_cleanup(self):
        import json
        from unittest.mock import patch
        from features.rclone.transfers import review_cli
        def lines(arguments, environment, cancelled, consume):
            if arguments[1] == 'sync':
                for message in ('Sync Logger: source: - stale.txt',
                                'Attempt 1/3 failed with 1 errors and: temporary listing failure',
                                'Sync Logger: source: + current.txt'):
                    consume(json.dumps({'msg': message}).encode())
            else:
                consume(b'[]')
        with patch.object(review_cli, '_lines', side_effect=lines), patch.object(
                review_cli.session, 'launch', return_value=None):
            result = self.finish(ReviewScan(scanner('rclone', 'Src:', 'Dst:', NULL_CONFIG,
                cleanup_plan=lambda cancelled: {'junk': ('generated junk', 'version')})))
        self.assertTrue(result.complete)
        self.assertEqual(set(result.changes), {('add', 'current.txt'), ('cleanup', 'generated junk')})

    def test_invalid_replacement_is_atomic_and_failed_scan_is_incomplete(self):
        from features.rclone.transfers.review import replace_changes
        def scan(emit, cancelled):
            emit('add', 'valid.txt')
            replace_changes(emit, [('delete', 'other.txt'), ('invalid', 'bad.txt')])
            return 'never approved'
        scan = ReviewScan(scan)
        self.assertTrue(scan.retired.wait(2))
        result = scan.snapshot()
        self.assertFalse(result.complete)
        self.assertTrue(result.error)
        self.assertEqual(result.changes, (('add', 'valid.txt'),))

    def test_directory_membership_type_conflicts_and_stable_revisions(self):
        from features.rclone.executable import get_rclone_path
        binary = get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is not installed')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            src, dst = root / 'source', root / 'destination'
            (src / 'New' / 'Nested').mkdir(parents=True)
            (dst / 'Gone').mkdir(parents=True)
            (src / 'Shared').mkdir()
            (dst / 'Shared').mkdir()
            (src / 'Conflict').mkdir()
            (dst / 'Conflict').write_text('destination file')
            compare = scanner(binary, src, dst, NULL_CONFIG)
            first = self.finish(ReviewScan(compare))
            self.assertIn(('add', 'New/Nested/'), first.changes)
            self.assertIn(('delete', 'Gone/'), first.changes)
            self.assertIn(('add', 'Conflict/'), first.changes)
            os.utime(src / 'Shared', (100, 100))
            os.utime(dst / 'Shared', (200, 200))
            self.assertTrue(unchanged(first, self.finish(ReviewScan(compare))))
            (src / 'New' / 'Nested').rmdir()
            self.assertFalse(unchanged(first, self.finish(ReviewScan(compare))))

    def test_plex_gui_actions_review_both_directions(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from features.plex import actions
        remote = SimpleNamespace(name='Movies-PMSDATA')
        local = SimpleNamespace(name='Movies-PMSDATA', path=Path('/local/Movies-PMSDATA'))
        with patch.object(actions, 'get_remote_cls_pmsdata', return_value=remote), patch.object(
                actions, 'get_local_cls_pmsdata', return_value=local), patch.object(
                actions.config, 'LogisticsConfig', return_value=SimpleNamespace(path_remote_local=Path('/local'))), patch.object(
                actions, 'reviewed_sync', return_value=False) as transfer:
            actions.pull_pms(object(), '/credentials')
            transfer.assert_called_with('Movies-PMSDATA:', local.path, config_path='/credentials', operation='Pull')
            actions.push_pms(object(), '/credentials')
            transfer.assert_called_with(local.path, 'Movies-PMSDATA:', config_path='/credentials', operation='Push')

    def finish(self, scan):
        self.assertTrue(scan.retired.wait(10))
        snapshot = scan.snapshot()
        self.assertFalse(snapshot.error, snapshot.error)
        return snapshot

    def test_real_sync_preserves_empty_folders_for_push_and_pull(self):
        import subprocess
        from features.rclone.executable import get_rclone_path
        from features.rclone.transfers.sync import build_sync_arguments
        binary = get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is not installed')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            local, remote = root / 'local', root / 'remote'
            (local / 'Empty' / 'Nested').mkdir(parents=True)
            remote.mkdir()
            (local / 'note.txt').write_text('fixture')
            config = root / 'empty.conf'
            config.write_text('')
            for source, destination in ((local, remote), (remote, root / 'pulled')):
                proposed = self.finish(ReviewScan(scanner(binary, source, destination, config)))
                self.assertTrue(proposed.complete)
                self.assertIn(('add', 'Empty/'), proposed.changes)
                self.assertIn(('add', 'Empty/Nested/'), proposed.changes)
                result = subprocess.run(build_sync_arguments(binary, source, destination,
                    config_path=config), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((destination / 'Empty' / 'Nested').is_dir())
                self.assertEqual((destination / 'note.txt').read_text(), 'fixture')

    def test_partial_scan_cancel_is_not_a_completed_approval(self):
        started = Event()
        def slow(emit, cancelled):
            emit('delete', 'destination-only.txt')
            started.set()
            while not cancelled():
                Event().wait(.01)
            return 'partial'
        scan = ReviewScan(slow)
        self.assertTrue(started.wait(1))
        self.assertIn('incomplete', scan.snapshot().text())
        scan.stop()
        snapshot = self.finish(scan)
        self.assertFalse(snapshot.complete)
        self.assertFalse(unchanged(snapshot, snapshot))
        request = ReviewRequest('Pull', 'Remote:', '/local', 'account')
        self.assertIn('Additional replacements and deletions', request.confirmation(incomplete=True))

    def test_cli_review_is_read_only_and_detects_changed_source(self):
        from features.rclone.executable import get_rclone_path
        binary = get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is not installed')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            src, dst = root / 'source', root / 'destination'
            src.mkdir(); dst.mkdir()
            name = 'new␊file.txt' if os.name == 'nt' else 'new\nfile.txt'
            (src / name).write_text('new')
            (src / 'replace.txt').write_text('new longer content')
            (dst / 'replace.txt').write_text('old')
            (dst / 'delete.txt').write_text('old')
            compare = scanner(binary, src, dst, NULL_CONFIG)
            first = self.finish(ReviewScan(compare))
            self.assertTrue(first.complete)
            # rclone renders control characters visibly in its JSON logger.
            self.assertEqual(set(first.changes), {('add', 'new␊file.txt'), ('replace', 'replace.txt'), ('delete', 'delete.txt')})
            self.assertEqual((dst / 'replace.txt').read_text(), 'old')
            self.assertTrue((dst / 'delete.txt').exists())
            self.assertTrue(unchanged(first, self.finish(ReviewScan(compare))))
            (src / 'replace.txt').write_text('a later version')
            self.assertFalse(unchanged(first, self.finish(ReviewScan(compare))))
            proposed = root / 'new-local-copy'
            snapshot = self.finish(ReviewScan(scanner(binary, src, proposed, NULL_CONFIG)))
            self.assertTrue(snapshot.complete)
            self.assertFalse(proposed.exists())

    def test_excluded_files_do_not_appear_or_invalidate_a_completed_review(self):
        from features.rclone.executable import get_rclone_path
        from features.rclone.transfers.transfer_options import TransferOptions
        binary = get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is not installed')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            src, dst = root / 'source', root / 'destination'
            src.mkdir(); dst.mkdir()
            (src / 'ignored.skip').write_text('excluded source')
            (dst / 'retained.skip').write_text('excluded destination')
            compare = scanner(binary, src, dst, NULL_CONFIG, TransferOptions(excludes=('*.skip',)))
            first = self.finish(ReviewScan(compare))
            self.assertEqual(first.changes, ())
            (src / 'ignored.skip').write_text('a later excluded source version')
            self.assertTrue(unchanged(first, self.finish(ReviewScan(compare))))


from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt


class ReviewDialogTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def approve_prepared(self, prepared):
        review = prepared.review
        self.assertTrue(review.approve(incomplete=True))
        self.assertTrue(review.scan.retired.wait(15))
        self.assertTrue(review.approved)
        return prepared

    def test_crypt_directory_review_decodes_each_supported_name_mode(self):
        from unittest.mock import patch
        from features.rclone import executable
        from features.rclone.localcrypt import backend as local_crypt
        from features.rclone import session
        from features.rclone.transfers import workflow
        from tests.local_crypt_fixture import crypt_fixture
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is not installed')
        for settings in ({}, {'filename_encryption': 'off'},
                         {'directory_name_encryption': 'false'}, {'filename_encryption': 'obfuscate'}):
            with self.subTest(settings=settings), self.temporary_directory() as directory, crypt_fixture(
                    directory, binary, crypt_settings=settings) as f:
                f.provider.mkdir('New empty')
                f.provider.mkdir('New empty/Nested')
                def confirm(prepared):
                    request, compare, valid = prepared.request, prepared.review.scanner, prepared.review.valid
                    first = self.finish_scan(compare)
                    self.assertIn(('add', 'New empty/'), first.changes)
                    self.assertIn(('add', 'New empty/Nested/'), first.changes)
                    self.assertTrue(unchanged(first, self.finish_scan(compare)))
                    self.assertTrue(valid())
                    return False
                with patch.object(executable, 'ensure_rclone', return_value=binary), patch(
                        'features.rclone.transfers.ui.review.confirm_review', side_effect=confirm):
                    self.assertFalse(workflow.reviewed_sync(f.item.data,
                        local_crypt.backing_target(session.credentials(f.context), 'Secret'),
                        operation='Push', config_path=f.context, copy_links=False))
                self.assertEqual(list(f.item.data.rglob('.logistics-review-directory*')), [])

    def test_early_proceed_retires_scan_and_requires_confirmation(self):
        from unittest.mock import patch
        from features.rclone.transfers.ui.review import ReviewDialog
        retired = Event()
        def slow(emit, cancelled):
            emit('delete', 'existing.txt')
            while not cancelled():
                retired.wait(.01)
            retired.set()
            return ''
        dialog = ReviewDialog(ReviewRequest('Pull', 'Remote:', '/local', 'account'), slow, lambda: True)
        qt.QTimer.singleShot(20, lambda: dialog.approve(True))
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes) as confirm:
            self.assertEqual(dialog.exec(), qt.QDialog.DialogCode.Accepted)
        self.assertTrue(retired.is_set())
        self.assertIn('incomplete', confirm.call_args.args[2])
        dialog.deleteLater()

    def test_early_review_approval_cannot_bypass_crypt_integrity(self):
        from unittest.mock import patch
        from features.rclone import executable
        from features.rclone.localcrypt import backend as local_crypt
        from features.rclone.transfers import sync
        from features.rclone.transfers import workflow
        from tests.local_crypt_fixture import crypt_fixture
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is not installed')
        actual_sync = sync.rclone_sync
        def execute(source, destination, **options):
            options['wait_for_output'] = True
            return actual_sync(source, destination, **options)
        with self.temporary_directory() as directory, crypt_fixture(directory, binary) as f:
            (f.item.data / 'rogue.txt').write_bytes(b'plaintext must never push')
            with patch.object(executable, 'ensure_rclone', return_value=binary), patch(
                    'features.rclone.transfers.ui.review.confirm_review', side_effect=self.approve_prepared), patch.object(
                    sync, 'rclone_sync', side_effect=execute), patch.object(sync, '_run_sync') as run:
                with self.assertRaisesRegex(ValueError, 'push refused'):
                    workflow.reviewed_sync(f.item.data, local_crypt.backing_target(local_crypt.unlock(f.item), 'Secret'),
                        operation='Push', config_path=f.context, copy_links=False)
                run.assert_not_called()

    def test_identical_credential_reload_invalidates_prepared_transfer(self):
        from unittest.mock import patch
        from features.rclone import executable, session
        from features.rclone.transfers import workflow, sync
        from tests.local_crypt_fixture import crypt_fixture
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is not installed')
        with self.temporary_directory() as directory, crypt_fixture(directory, binary) as f:
            def confirm(prepared):
                self.approve_prepared(prepared)
                values = session.credentials(f.context)
                session.remember(f.context, values, package_path=f.package)
                return prepared
            with patch.object(executable, 'ensure_rclone', return_value=binary), patch(
                    'features.rclone.transfers.ui.review.confirm_review', side_effect=confirm), patch.object(
                    sync, 'rclone_sync') as run:
                with self.assertRaisesRegex(ValueError, 'Connection or review changed'):
                    workflow.reviewed_sync(f.plain, 'Secret:', operation='Push', config_path=f.context)
                run.assert_not_called()

    def test_crypt_push_review_includes_cleanup_and_its_remote_deletion(self):
        from io import BytesIO
        from unittest.mock import patch
        from features.rclone import executable
        from features.rclone.localcrypt import backend as local_crypt
        from features.rclone import session
        from features.rclone.transfers import workflow
        from tests.local_crypt_fixture import crypt_fixture
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is not installed')
        with self.temporary_directory() as directory, crypt_fixture(directory, binary) as f:
            f.provider.create_file('.DS_Store', BytesIO(b'synthetic generated junk'))
            raw = f.provider._physical('.DS_Store', False)
            (f.cloud / raw.name).write_bytes(raw.read_bytes())
            def confirm(prepared):
                request, compare, valid = prepared.request, prepared.review.scanner, prepared.review.valid
                snapshot = self.finish_scan(compare)
                self.assertIn(('cleanup', '.DS_Store'), snapshot.changes)
                self.assertIn(('delete', '.DS_Store'), snapshot.changes)
                self.assertNotIn(('match', '.DS_Store'), snapshot.changes)
                self.assertTrue(raw.exists(), 'review must not clean local files')
                self.assertTrue((f.cloud / raw.name).exists())
                return False
            with patch.object(executable, 'ensure_rclone', return_value=binary), patch(
                    'features.rclone.transfers.ui.review.confirm_review', side_effect=confirm):
                self.assertFalse(workflow.reviewed_sync(f.item.data,
                    local_crypt.backing_target(session.credentials(f.context), 'Secret'),
                    operation='Push', config_path=f.context, copy_links=False))
            self.assertTrue(raw.exists())

    def test_competing_local_account_claim_blocks_pull_before_execution(self):
        from unittest.mock import patch
        from features.rclone import actions
        from features.rclone import executable
        from features.rclone.localcrypt import connections as local_connections
        from features.rclone.transfers import sync
        from tests.local_crypt_fixture import crypt_fixture
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is not installed')
        with self.temporary_directory() as directory, crypt_fixture(directory, binary) as f:
            root = Path(directory) / 'Server/Local'
            def confirm(prepared):
                local_connections.LocalConnection(Path(directory) / 'Other.zip', 'Cloud', root).publish()
                return self.approve_prepared(prepared)
            with patch('features.rclone.localcrypt.ui.views.ensure_session', return_value=True), patch.object(
                    executable, 'ensure_rclone', return_value=binary), patch(
                    'features.rclone.transfers.ui.review.confirm_review', side_effect=confirm), patch.object(sync, '_run_sync') as run:
                with self.assertRaisesRegex(ValueError, 'belongs to another credential package'):
                    actions.pull_remote('Cloud', f.context, review=True)
                run.assert_not_called()

    def finish_scan(self, scanner):
        scan = ReviewScan(scanner)
        self.assertTrue(scan.retired.wait(15))
        result = scan.snapshot()
        self.assertFalse(result.error, result.error)
        return result

    def test_new_crypt_pull_reviews_without_creating_its_local_folder(self):
        import shutil
        from unittest.mock import patch
        from features.rclone import executable
        from features.rclone.localcrypt import backend as local_crypt
        from features.rclone.transfers import sync
        from features.rclone.transfers import workflow
        from tests.local_crypt_fixture import crypt_fixture
        binary = executable.get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone is not installed')
        actual_sync = sync.rclone_sync
        def execute(source, destination, **options):
            options['wait_for_output'] = True
            return actual_sync(source, destination, **options)
        with self.temporary_directory() as directory, crypt_fixture(directory, binary) as f:
            f.provider.close()
            shutil.rmtree(f.item.data)
            def confirm(prepared):
                request, scan, valid = prepared.request, prepared.review.scanner, prepared.review.valid
                changes = []
                self.assertTrue(scan(lambda kind, path: changes.append((kind, path)), lambda: False))
                self.assertIn(('add', 'note.md'), changes)
                self.assertFalse(f.item.data.exists())
                self.assertTrue(valid())
                return self.approve_prepared(prepared)
            with patch.object(executable, 'ensure_rclone', return_value=binary), patch(
                    'features.rclone.transfers.ui.review.confirm_review', side_effect=confirm), patch.object(
                    sync, 'rclone_sync', side_effect=execute):
                self.assertTrue(workflow.reviewed_sync(
                    local_crypt.backing_target(local_crypt.unlock(f.item), 'Secret'), f.item.data,
                    operation='Pull', config_path=f.context, crypt_item=f.item,
                    before_start=f.item.publish, copy_links=False))
            self.assertTrue(f.item.data.is_dir())
            self.assertTrue(any(f.item.data.iterdir()))

    def test_changed_review_does_not_execute_without_another_confirmation(self):
        from unittest.mock import patch
        from features.rclone.transfers.ui.review import ReviewDialog
        count = 0
        def changing(emit, cancelled):
            nonlocal count
            count += 1
            emit('replace', 'note.txt')
            return str(count)
        dialog = ReviewDialog(ReviewRequest('Push', '/local', 'Remote:', 'account'), changing, lambda: True)
        timer = qt.QTimer()
        def drive():
            if count == 1 and dialog.session.scan.snapshot().complete:
                dialog.approve(False)
            elif count == 2 and dialog.session.expected is None:
                self.assertIn('Files changed', dialog.notice.text())
                timer.stop()
                dialog.reject()
        timer.timeout.connect(drive)
        timer.start(20)
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Yes):
            self.assertEqual(dialog.exec(), qt.QDialog.DialogCode.Rejected)
        self.assertEqual(count, 2)
        dialog.deleteLater()

    def test_revocation_clears_displayed_paths(self):
        from features.rclone.transfers.ui.review import ReviewDialog
        active = [True]
        def scan(emit, cancelled):
            emit('replace', 'private-name.md')
            return 'revision'
        dialog = ReviewDialog(ReviewRequest('Push', '/private-name', 'Remote:', 'account'), scan, lambda: active[0])
        def revoke():
            active[0] = False
            dialog.refresh()
        qt.QTimer.singleShot(30, revoke)
        self.assertEqual(dialog.exec(), qt.QDialog.DialogCode.Rejected)
        self.assertEqual(dialog.details.toPlainText(), '')
        self.assertNotIn('private-name', dialog.paths.toPlainText())
        dialog.deleteLater()
