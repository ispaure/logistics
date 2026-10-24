"""Desktop credential ZIP import, explicit unlock choices and empty-list recovery."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.rclone import credentials, configuration, session
from features.rclone.ui.page import RclonePage
from features.rclone.ui.credential_unlock import CredentialUnlockDialog, choose_credential_retention


class CredentialImportTests(QtTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.packages = self.root / 'Credentials/rclone'
        self.configs = self.root / 'configs'
        settings = SimpleNamespace(path_logistics_remote_cred=self.packages)
        self.enterContext(patch.object(credentials.config, 'LogisticsConfig', return_value=settings))
        self.enterContext(patch.object(credentials, 'get_credential_package_directories', return_value=(self.packages,)))
        self.enterContext(patch.object(configuration, 'get_rclone_config_dir', return_value=self.configs))
        self.addCleanup(lambda: [session.forget(path) for path in session.paths()])

    def make_zip(self, name='Account.zip', content='encrypted fixture is validated on unlock'):
        path = self.root / name
        with ZipFile(path, 'w') as archive:
            archive.writestr('Fixture.txt', content)
        return path

    def page(self):
        page = RclonePage()
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.close)
        return page

    def test_import_copies_zip_without_unlocking_and_selects_it_from_empty_list(self):
        source = self.make_zip('Account.ZIP')
        original = source.read_bytes()
        page = self.page()
        self.assertFalse(page.empty_notice.isHidden())
        self.assertFalse(page.load_button.isEnabled())
        self.assertTrue(page.management_group.isHidden())
        self.assertIs(page.status_label.parentWidget(), page)
        with patch.object(qt.QFileDialog, 'getOpenFileName', return_value=(str(source), '')) as picker:
            page.import_button.click()
        self.wait_until(lambda: not page.load_operation.busy)
        self.assertIn('*.zip', picker.call_args.args[3])
        self.assertNotIn('All files', picker.call_args.args[3])
        self.assertEqual((self.packages / 'Account.zip').read_bytes(), original)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(page._get_selected_package().path, self.packages / 'Account.zip')
        self.assertTrue(page.empty_notice.isHidden())
        self.assertTrue(page.load_button.isEnabled())
        self.assertIn('imported', page.status_label.text())
        self.assertEqual(session.paths(), [])
        self.assertFalse(self.configs.exists())
        self.assertEqual(list(self.packages.iterdir()), [self.packages / 'Account.zip'])
        # Reimporting the same archive is idempotent, including from its destination.
        self.assertEqual(credentials.import_credential_package(source), self.packages / 'Account.zip')
        self.assertEqual(credentials.import_credential_package(self.packages / 'Account.zip'), self.packages / 'Account.zip')

    def test_collision_invalid_file_and_cancel_preserve_existing_files(self):
        source = self.make_zip()
        target = credentials.import_credential_package(source)
        original = target.read_bytes()
        self.make_zip(content='different package')
        with self.assertRaises(FileExistsError):
            credentials.import_credential_package(source)
        self.assertEqual(target.read_bytes(), original)
        for name, content in (('invalid.zip', b'not a zip'), ('invalid.txt', b'not a zip'),
                              ('large.zip', b'x' * (1024 * 1024 + 1))):
            source = self.root / name
            source.write_bytes(content)
            with self.subTest(name=name), self.assertRaises(ValueError):
                credentials.import_credential_package(source)
        from commonUtils.runtime.operations import OperationCancelled
        with self.assertRaises(OperationCancelled):
            credentials.import_credential_package(self.make_zip('Cancelled.zip'), cancelled=lambda: True)
        self.assertEqual(list(self.packages.iterdir()), [target])
        page = self.page()
        with patch.object(qt.QFileDialog, 'getOpenFileName', return_value=('', '')):
            page.import_button.click()
        self.assertFalse(page.load_operation.busy)
        self.assertEqual(page.credential_list.count(), 1)

    def test_refresh_discovers_external_package_and_import_failure_stays_retryable(self):
        page = self.page()
        self.packages.mkdir(parents=True)
        source = self.make_zip()
        (self.packages / 'Account.zip').write_bytes(source.read_bytes())
        page.refresh_button.click()
        self.assertEqual(page.credential_list.count(), 1)
        bad = self.root / 'bad.zip'
        bad.write_bytes(b'invalid')
        with patch.object(qt.QFileDialog, 'getOpenFileName', return_value=(str(bad), '')):
            page.import_button.click()
        self.wait_until(lambda: not page.load_operation.busy)
        self.assertIn('valid ZIP', page.status_label.text())
        self.assertTrue(page.import_button.isEnabled())
        self.assertTrue(page.refresh_button.isEnabled())
        self.assertEqual(page.credential_list.count(), 1)

    def test_unlock_popup_routes_both_modes_and_cancel_without_loading(self):
        credentials.import_credential_package(self.make_zip())
        page = self.page()
        for remember in (False, True, None):
            page.password_input.setText('fixture-password')
            with self.subTest(remember=remember), patch(
                    'features.rclone.ui.credential_unlock.choose_credential_retention', return_value=remember), \
                    patch.object(page, '_load_selected_credentials') as load:
                page.load_button.click()
                if remember is None:
                    load.assert_not_called()
                else:
                    load.assert_called_once_with(remember=remember)
        with patch('features.rclone.ui.credential_unlock.choose_credential_retention') as choose:
            page.password_input.clear()
            page.load_button.click()
            choose.assert_not_called()
            self.assertIn('Enter', page.status_label.text())

    def test_import_then_unlock_keeps_the_encrypted_zip_and_honors_each_retention_mode(self):
        from commonUtils.archives.zip_access import open_archive
        source = self.root / 'Protected.zip'
        with open_archive(source, 'w', password='fixture-password') as archive:
            archive.writestr('Fixture.txt', '[Fixture]\ntype=local\n')
        page = self.page()
        with patch.object(qt.QFileDialog, 'getOpenFileName', return_value=(str(source), '')):
            page.import_button.click()
        self.wait_until(lambda: not page.load_operation.busy)
        for remember in (False, True):
            page.password_input.setText('fixture-password')
            with patch('features.rclone.ui.credential_unlock.choose_credential_retention', return_value=remember):
                page.load_button.click()
            self.wait_until(lambda: not page.load_operation.busy)
            self.assertEqual(page.loaded_status.text(), 'Saved' if remember else 'Session only')
            self.assertEqual((self.configs / 'Protected.conf').exists(), remember)
            self.assertEqual(page.remote_list.item(0).text(), 'Fixture')
            self.assertEqual((self.packages / 'Protected.zip').read_bytes(), source.read_bytes())
            self.assertEqual(page.password_input.text(), '')
            self.assertIn('Workspaces', page.status_label.text())
            self.assertFalse(page.manage_button.isHidden())
            self.assertTrue(page.management_group.isHidden())

    def test_import_publication_does_not_replace_a_racing_package(self):
        from commonUtils.persistence import atomic_write_bytes
        source = self.make_zip()
        def racing_write(path, content, **kwargs):
            path.write_bytes(b'existing package wins')
            return atomic_write_bytes(path, content, **kwargs)
        with patch('commonUtils.persistence.atomic_write_bytes', side_effect=racing_write):
            with self.assertRaises(FileExistsError):
                credentials.import_credential_package(source)
        self.assertEqual((self.packages / 'Account.zip').read_bytes(), b'existing package wins')

    def test_locked_package_details_and_management_are_collapsed_and_forget_removes_names(self):
        from features.rclone import desktop_catalog
        copied = credentials.import_credential_package(self.make_zip())
        context = self.configs / 'Account.session'
        desktop_catalog.remember(context, copied, ['Books'])
        page = self.page()
        self.assertEqual(page.loaded_status.text(), 'Locked')
        self.assertEqual(page.remote_list.item(0).text(), 'Books')
        self.assertTrue(page.package_details.isHidden())
        self.assertTrue(page.management_group.isHidden())
        page.details_button.click()
        self.assertFalse(page.package_details.isHidden())
        page.manage_button.click()
        self.assertFalse(page.management_group.isHidden())
        self.assertTrue(page.remove_button.isEnabled())
        with patch('features.rclone.ui.page.ui.display_msg_box_ok_cancel', return_value=True):
            page.remove_button.click()
        self.assertFalse(desktop_catalog.record_path(context).exists())
        self.assertTrue(copied.exists())
        self.assertTrue(page.management_group.isHidden())

    def test_retention_popup_presents_parallel_choices_and_saved_config_caveat(self):
        package = self.root / 'Account.zip'
        config = self.root / 'Account.conf'
        config.write_text('[fixture]')
        for remember in (False, True, None):
            def choose():
                dialog = qt.QApplication.activeModalWidget()
                self.assertIsInstance(dialog, CredentialUnlockDialog)
                captions = ' '.join(label.text() for label in dialog.findChildren(qt.QLabel))
                self.assertIn('in memory', captions)
                self.assertIn('not protected by the ZIP password', captions)
                self.assertIn('Session only does not delete it', captions)
                self.assertEqual(dialog.session_button.parentWidget().parentWidget(), dialog)
                if remember is None:
                    dialog.reject()
                else:
                    (dialog.saved_button if remember else dialog.session_button).click()
            qt.QTimer.singleShot(0, choose)
            self.assertIs(choose_credential_retention(package, config), remember)
