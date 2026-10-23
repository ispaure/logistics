"""Session imports never extract TXT/config files or put secrets in argv."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.archives.zip_access import open_archive
from commonUtils.integrations.wrappers.cmdShellWrapper import CommandResult
from features.rclone import configuration
from features.rclone import credentials
from features.rclone import session
from features.rclone.transfers import sync


class RcloneSessionTests(unittest.TestCase):
    def tearDown(self):
        for path in session.paths():
            session.forget(path)

    def test_zip_stays_in_memory_and_selected_package_reaches_cli_without_secrets_in_argv(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package, config_path = root / 'Accounts.zip', root / 'Accounts.conf'
            with open_archive(package, 'w', password='synthetic-zip-password') as archive:
                archive.writestr('remote.txt', '[Dépôt.alpha+user@example]\ntype=local\n')
                archive.writestr('private.txt', '[Synthetic]\ntype=webdav\nurl=https://example.invalid\npass=synthetic-secret\n')
            with patch.object(configuration, 'get_credential_config_path', return_value=config_path), \
                 patch.object(credentials.zipUtils, 'unzip_file', side_effect=AssertionError('Session must not extract')):
                self.assertTrue(credentials.load_remote_from_zip_to_config(package, 'synthetic-zip-password', remember=False))
            context = config_path.with_suffix('.session')
            self.assertEqual(configuration.get_rclone_remote_names(context), ['Dépôt.alpha+user@example', 'Synthetic'])
            self.assertEqual(list(root.iterdir()), [package])
            with patch.object(sync.cmdShellWrapper, 'run_command', return_value=CommandResult(0)) as run:
                self.assertTrue(sync.rclone_sync('Synthetic:folder', root / 'local', config_path=context,
                                                wait_for_output=True, executable_path='fixture-rclone'))
            arguments = run.call_args.args[0]
            environment = run.call_args.kwargs['environment']
            self.assertNotIn('synthetic-secret', str(arguments))
            self.assertIn('synthetic-secret', environment.values())
            self.assertIn(session.NULL_CONFIG, arguments)
            self.assertNotIn('RCLONE_CONFIG_SYNTHETIC_PASS', os.environ)
            self.assertTrue(configuration.delete_config_file(context))
            with self.assertRaisesRegex(ValueError, 'session has ended'):
                sync.rclone_sync('Synthetic:', root / 'local', config_path=context, executable_path='fixture-rclone')

    def test_real_cli_session_transfer_when_pinned_rclone_is_installed(self):
        from features.rclone.executable import get_rclone_path
        binary = get_rclone_path()
        if not binary.is_file():
            self.skipTest('Pinned rclone executable not installed')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            (source / 'fixture.txt').write_text('Synthetic session transfer')
            context = root / 'Fixture.session'
            session.remember(context, {'Unicode.dépôt': {'type': 'local'}})
            self.assertTrue(sync.rclone_sync('Unicode.dépôt:' + str(source), root / 'destination', config_path=context,
                                            wait_for_output=True, executable_path=binary))
            self.assertEqual((root / 'destination/fixture.txt').read_text(), 'Synthetic session transfer')
            self.assertFalse(context.exists())

    def test_failed_import_preserves_session_and_existing_saved_config(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package, config_path = root / 'Accounts.zip', root / 'Accounts.conf'
            config_path.write_text('saved config remains')
            with open_archive(package, 'w', password='synthetic-password') as archive:
                archive.writestr('remote.txt', '[Fixture]\ntype=local\n')
            with patch.object(configuration, 'get_credential_config_path', return_value=config_path), \
                 patch.object(credentials.ui, 'display_msg_box_ok'):
                self.assertTrue(credentials.load_remote_from_zip_to_config(package, 'synthetic-password', remember=False))
                self.assertFalse(credentials.load_remote_from_zip_to_config(package, 'wrong', remember=False))
            self.assertEqual(session.names(config_path.with_suffix('.session')), ['Fixture'])
            self.assertEqual(config_path.read_text(), 'saved config remains')


class RcloneCredentialScreenTests(unittest.TestCase):
    def _wait_for_load(self, page, app):
        from time import monotonic
        from commonUtils.ui import pyside as qt
        deadline = monotonic() + 5
        while page.load_operation.busy and monotonic() < deadline:
            app.processEvents()
            qt.QThread.msleep(1)
        self.assertFalse(page.load_operation.busy)

    def test_slow_decode_keeps_event_loop_live_and_cancel_preserves_credentials(self):
        import threading
        from commonUtils.ui import pyside as qt
        from commonUtils.filesystem.files import File
        from features.rclone.ui.page import RclonePage
        app = qt.QApplication.instance() or qt.QApplication([])
        started, release = threading.Event(), threading.Event()
        gui_thread = threading.get_ident()
        worker_threads = []
        def slow_read(*args):
            worker_threads.append(threading.get_ident())
            started.set()
            if not release.wait(3):
                raise RuntimeError('test decode timed out')
            return {'New': {'type': 'local'}}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'Accounts.zip'
            package.touch()
            saved = root / 'Accounts.conf'
            saved.write_text('[Existing]\ntype=local\n')
            with patch.object(credentials, 'get_logistics_remote_credentials_zip_lst', return_value=[File(package)]), \
                 patch.object(configuration, 'get_rclone_config_dir', return_value=root), \
                 patch.object(session, 'read_package', side_effect=slow_read), \
                 patch.object(credentials.ui, 'display_msg_box_ok') as popup:
                page = RclonePage()
                try:
                    page.password_input.setText('synthetic-password')
                    page.load_button.click()
                    self.assertTrue(started.wait(1))
                    self.assertNotEqual(worker_threads, [gui_thread])
                    self.assertTrue(page.load_operation.busy)
                    self.assertFalse(page.load_button.isEnabled())
                    self.assertEqual(page.password_input.text(), '')
                    pulse = []
                    qt.QTimer.singleShot(0, lambda: pulse.append(True))
                    app.processEvents()
                    self.assertEqual(pulse, [True])
                    self.assertFalse(page.can_close())
                    release.set()
                    self._wait_for_load(page, app)
                    self.assertEqual(saved.read_text(), '[Existing]\ntype=local\n')
                    self.assertIsNone(session.names(root / 'Accounts.session'))
                    self.assertTrue(page.load_button.isEnabled())
                    popup.assert_not_called()
                    with patch.object(session, 'read_package', side_effect=ValueError('synthetic decode failure')):
                        page.password_input.setText('wrong-password')
                        page.load_session_button.click()
                        self._wait_for_load(page, app)
                    self.assertIn('failed', page.status_label.text())
                    self.assertTrue(page.load_button.isEnabled())
                    self.assertEqual(saved.read_text(), '[Existing]\n' 'type=local\n')
                    popup.assert_not_called()
                finally:
                    release.set()
                    self._wait_for_load(page, app)
                    page.close()
                    app.processEvents()

    def test_session_choice_labels_and_forgets_the_package_without_files(self):
        from types import SimpleNamespace
        from commonUtils.ui import pyside as qt
        from commonUtils.filesystem.files import File
        from features.rclone.ui.page import RclonePage
        app = qt.QApplication.instance() or qt.QApplication([])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'Accounts.zip'
            with open_archive(package, 'w', password='synthetic-password') as archive:
                archive.writestr('Fixture.txt', '[Fixture]\ntype=local\n')
            with patch.object(credentials, 'get_logistics_remote_credentials_zip_lst', return_value=[File(package)]), \
                 patch.object(credentials.config, 'LogisticsConfig', return_value=SimpleNamespace(temp_path=root / 'work')), \
                 patch.object(configuration, 'get_rclone_config_dir', return_value=root):
                page = RclonePage()
                try:
                    page.password_input.setText('synthetic-password')
                    page.load_session_button.click()
                    self._wait_for_load(page, app)
                    self.assertEqual(page.loaded_status.text(), 'Session only')
                    self.assertEqual(page.remote_list.item(0).text(), 'Fixture')
                    self.assertIn('Accounts.zip', page.status_label.text())
                    self.assertEqual(page.password_input.text(), '')
                    self.assertEqual(list(root.iterdir()), [package])
                    page.password_input.setText('synthetic-password')
                    page.load_button.click()
                    self._wait_for_load(page, app)
                    self.assertEqual(page.loaded_status.text(), 'Saved')
                    self.assertTrue((root / 'Accounts.conf').is_file())
                    self.assertEqual(session.names(root / 'Accounts.session'), ['Fixture'])
                    layout = page.remove_button.parentWidget().layout()
                    self.assertLess(layout.indexOf(page.clear_all_button), layout.indexOf(page.remove_button))
                    self.assertLess(layout.indexOf(page.remove_button), layout.indexOf(page.clear_sessions_button))
                    with patch('features.rclone.ui.page.ui.display_msg_box_ok_cancel', return_value=True):
                        page.remove_button.click()
                    self.assertEqual(session.paths(), [])
                    self.assertFalse((root / 'Accounts.conf').exists())
                    self.assertTrue(package.is_file())
                finally:
                    page.close()
                    for path in session.paths():
                        session.forget(path)
                    app.processEvents()
