"""Credential revocation stops live processes and rejects late successful output."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import time
from unittest.mock import patch
from zipfile import ZipFile

from commonUtils.archives.zip_access import open_archive
from commonUtils.integrations.wrappers.cmdShellWrapper import CommandResult
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.runtime.resources.lifetime import WorkerCancellation
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.rclone import credentials, session
from features.rclone.localcrypt.backend import CryptResources
from features.rclone.transfers import sync, review_cli


class CredentialRevocationTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.context = Path('/synthetic/audit.session')
        self.values = {'Fixture': {'type': 'local'}}
        session.remember(self.context, self.values)
        self.addCleanup(session.forget, self.context)

    def replace(self):
        session.forget(self.context)
        session.remember(self.context, self.values)

    def provider(self):
        provider = CryptResources.__new__(CryptResources)
        provider.context, provider.binary, provider.closed = self.context, Path('synthetic-rclone'), False
        provider.root = Path('/synthetic/ciphertext')
        provider._cancellation = WorkerCancellation()
        provider._encoded_paths = {}
        return provider

    def test_unencrypted_and_mixed_packages_preserve_existing_credentials_in_both_modes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'Accounts.conf'
            context = config.with_suffix('.session')
            config.write_text('existing saved credentials')
            session.remember(context, self.values)
            self.addCleanup(session.forget, context)
            for mixed in (False, True):
                package = root / 'Accounts.zip'
                if mixed:
                    with open_archive(package, 'w', password='synthetic-password') as archive:
                        archive.writestr('encrypted.txt', '[Encrypted]\ntype=local\n')
                with ZipFile(package, 'a' if mixed else 'w') as archive:
                    archive.writestr('plain.txt', '[Plain]\ntype=local\n')
                for remember in (False, True):
                    with self.subTest(mixed=mixed, remember=remember), \
                         patch.object(credentials.configuration, 'get_credential_config_path', return_value=config), \
                         patch.object(credentials.ui, 'display_msg_box_ok'), \
                         patch.object(credentials.zipUtils, 'unzip_file') as extract:
                        before = package.read_bytes()
                        self.assertFalse(credentials.load_remote_from_zip_to_config(
                            package, 'synthetic-password', remember=remember))
                        extract.assert_not_called()
                        self.assertEqual(session.credentials(context), self.values)
                        self.assertEqual(config.read_text(), 'existing saved credentials')
                        self.assertEqual(package.read_bytes(), before)

    def test_late_success_does_not_survive_session_replacement(self):
        def finish(*args, **kwargs):
            self.replace()
            self.assertTrue(kwargs['cancelled']())
            return CommandResult(0)
        for query, wait in ((False, True), (False, False), (True, False)):
            with self.subTest(query=query, wait=wait), \
                 patch.object(sync.cmdShellWrapper, 'run_command', side_effect=finish), \
                 patch.object(sync, 'log'):
                options = dict(config_path=self.context, executable_path='synthetic-rclone',
                               integrated=False, wait_for_output=wait, query=query)
                if query:
                    with self.assertRaisesRegex(RuntimeError, 'Cancelled'):
                        sync._run_sync('Fixture:a', 'Fixture:b', **options)
                else:
                    self.assertFalse(sync._run_sync('Fixture:a', 'Fixture:b', **options))

    def test_transfer_and_localcrypt_processes_stop_after_revoke_and_immediate_reload(self):
        from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
        for localcrypt in (False, True):
            with self.subTest(localcrypt=localcrypt), TemporaryDirectory() as directory:
                ready, finished = Path(directory) / 'ready', Path(directory) / 'finished'
                script = 'from pathlib import Path; import sys,time; Path(sys.argv[1]).touch(); time.sleep(30); Path(sys.argv[2]).touch()'
                arguments = [sys.executable, '-u', '-c', script, str(ready), str(finished)]
                def revoke():
                    deadline = time.monotonic() + 5
                    while not ready.exists() and time.monotonic() < deadline:
                        time.sleep(.01)
                    self.replace()
                worker = threading.Thread(target=revoke)
                worker.start()
                try:
                    started = time.monotonic()
                    if localcrypt:
                        def run(_arguments, **kwargs):
                            return run_bytes(arguments, **kwargs)
                        with patch('features.rclone.localcrypt.backend.run_bytes', side_effect=run):
                            with self.assertRaises(OperationCancelled):
                                self.provider().command('cat', 'note.md')
                    else:
                        with patch.object(sync, 'build_sync_arguments', return_value=arguments), patch.object(sync, 'log'):
                            self.assertFalse(sync._run_sync('Fixture:a', 'Fixture:b', config_path=self.context,
                                executable_path=sys.executable, integrated=False, wait_for_output=True))
                    self.assertLess(time.monotonic() - started, 10)
                    self.assertTrue(ready.exists())
                    self.assertFalse(finished.exists())
                finally:
                    worker.join(timeout=6)

    def test_gui_transfer_cancels_on_worker_thread_revocation_and_subscription_race(self):
        from commonUtils.ui.tasks.process_progress import open_process
        for race in (False, True):
            with self.subTest(subscription_race=race), TemporaryDirectory() as directory:
                ready = Path(directory) / 'ready'
                script = 'from pathlib import Path; import sys,time; Path(sys.argv[1]).touch(); time.sleep(30)'
                arguments = [sys.executable, '-u', '-c', script, str(ready)]
                windows = []
                def opened(*args, **kwargs):
                    window = open_process(*args, **kwargs)
                    windows.append(window)
                    if race:
                        self.replace()
                    return window
                with patch.object(sync, 'build_sync_arguments', return_value=arguments), \
                     patch('commonUtils.ui.tasks.process_progress.open_process', side_effect=opened):
                    self.assertTrue(sync._run_sync('Fixture:a', 'Fixture:b', config_path=self.context,
                                                  executable_path=sys.executable))
                window = windows[0]
                try:
                    if not race:
                        self.wait_until(ready.exists)
                        worker = threading.Thread(target=self.replace)
                        worker.start()
                        worker.join(timeout=5)
                    self.wait_until(lambda: not window.busy)
                    self.assertEqual(window.result.state, 'cancelled')
                finally:
                    window.runner.cancel()
                    self.wait_until(lambda: not window.busy)
                    window.close()
                    self.app.processEvents()

    def test_localcrypt_commands_poll_revocation_and_discard_late_plaintext(self):
        # Exercise the subprocess boundary without requiring a crypt installation.
        provider = self.provider()
        for encode in (False, True):
            for late in (False, True):
                with self.subTest(encode=encode, late=late):
                    session.remember(self.context, self.values)
                    def run(*args, **kwargs):
                        self.assertFalse(kwargs['cancelled']())
                        self.replace()
                        self.assertTrue(kwargs['cancelled']())
                        if not late:
                            raise OperationCancelled('Operation cancelled')
                        return b'["encoded"]' if encode else b'synthetic plaintext'
                    with patch('features.rclone.localcrypt.backend.run_bytes', side_effect=run):
                        with self.assertRaises(OperationCancelled):
                            if encode:
                                provider.encrypted_path('note.md')
                            else:
                                provider.command('cat', 'note.md')
                    self.assertFalse(provider._encoded_paths)

    def test_review_stops_without_publishing_results_after_replacement(self):
        def lines(arguments, environment, cancelled, consume):
            self.replace()
            self.assertTrue(cancelled())
        with patch.object(review_cli, '_lines', side_effect=lines) as run:
            changes = []
            scan = review_cli.scanner('synthetic-rclone', 'Fixture:a', 'Fixture:b', self.context)
            self.assertEqual(scan(lambda *row: changes.append(row), lambda: False), '')
            self.assertFalse(changes)
            self.assertEqual(run.call_count, 1)
