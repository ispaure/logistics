"""Ciphertext mirror, streaming readers/editors, private UI and credential lifetime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from features.rclone import executable
from features.rclone.localcrypt import backend as local_crypt
from features.rclone.localcrypt import mapping as copy_mapping
from features.rclone import session
from tests.local_crypt_fixture import crypt_fixture


from tests.resources.localcrypt_cases import LocalCryptCase
from types import SimpleNamespace
from unittest import TestCase


class LocalCryptConstructionTests(TestCase):
    """Exercise constructor handoffs without a CLI, GUI, or real credentials."""

    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.root = Path(directory)
        self.item = SimpleNamespace(context=self.root / 'account.session', package=self.root / 'account.zip',
                                    remote='Secret', root=self.root / 'ciphertext')
        self.item.data = self.item.root / self.item.remote
        self.item.data.mkdir(parents=True)
        self.binary = self.root / 'synthetic-rclone'
        self.binary.touch()
        self.values = {'Secret': {'type': 'crypt', 'remote': 'Cloud:synthetic', 'password': 'synthetic-old'},
                       'Cloud': {'type': 'local'}}
        self.children, self.caches = [], []
        self.before = set(session.paths())
        self.enterContext(patch.object(local_crypt.configuration, 'get_rclone_config_dir', return_value=self.root))
        self.enterContext(patch('features.rclone.storage.install_local_storage_policy'))
        remember, cache = session.remember, local_crypt.PrivateReadCache
        def track_child(context, values, **options):
            if options.get('private'):
                self.children.append(context)
            return remember(context, values, **options)
        def track_cache(*args, **kwargs):
            result = cache(*args, **kwargs)
            self.caches.append(result)
            return result
        self.enterContext(patch.object(session, 'remember', side_effect=track_child))
        self.enterContext(patch.object(local_crypt, 'PrivateReadCache', side_effect=track_cache))
        self.addCleanup(self.retire)
        self.replace()

    def retire(self):
        for context in (self.item.context, *self.children):
            session.forget(context)
            session.forget_package_path(context)
        for cache in self.caches:
            cache.retire()
        self.assertEqual(set(session.paths()), self.before)

    def replace(self, password='synthetic-old', *, package=None, values=None):
        settings = values if values is not None else {
            **self.values, 'Secret': {**self.values['Secret'], 'password': password}}
        session.remember(self.item.context, settings, package_path=package or self.item.package)

    def construct(self, **kwargs):
        provider = local_crypt.CryptResources(self.item, binary=self.binary, **kwargs)
        self.addCleanup(provider.close)
        return provider

    def assert_retired(self):
        for child in self.children:
            self.assertIsNone(session.credentials(child))
        self.assertTrue(all(cache.closed for cache in self.caches))

    def test_replacement_after_snapshot_rejects_and_retires_child(self):
        with patch.object(local_crypt, 'validate_ciphertext_tree', side_effect=lambda _: self.replace('synthetic-new')):
            with self.assertRaises(ValueError):
                self.construct()
        self.assert_retired()
        self.assertEqual(session.credentials(self.item.context)['Secret']['password'], 'synthetic-new')

    def test_lock_after_snapshot_retires_partial_construction(self):
        with patch.object(local_crypt, 'validate_ciphertext_tree', side_effect=lambda _: session.forget(self.item.context)):
            with self.assertRaises(ValueError):
                self.construct()
        self.assert_retired()

    def test_final_snapshot_follows_completed_unlock(self):
        unlocked = local_crypt.unlock
        first = True
        def replace_after_unlock(*args, **kwargs):
            nonlocal first
            values = unlocked(*args, **kwargs)
            if first:
                first = False
                self.replace('synthetic-new')
            return values
        with patch.object(local_crypt, 'unlock', side_effect=replace_after_unlock):
            provider = self.construct()
        self.assertEqual(session.credentials(provider.context)['view']['password'], 'synthetic-new')

    def test_final_snapshot_revalidates_package_remote_and_password(self):
        from features.rclone.desktop_service import service
        capture = service.credentials.capture
        cases = [('package', self.values, self.root / 'unrelated.zip'),
                 ('remote', {'Secret': {'type': 'local'}}, self.item.package),
                 ('password', {'Secret': {'type': 'crypt', 'remote': 'Cloud:synthetic'},
                               'Cloud': {'type': 'local'}}, self.item.package)]
        for label, values, package in cases:
            with self.subTest(label=label):
                self.replace()
                def changed_before_capture(context):
                    if context == self.item.context:
                        self.replace(values=values, package=package)
                    return capture(context)
                with patch.object(service.credentials, 'capture', side_effect=changed_before_capture):
                    with self.assertRaises(ValueError):
                        self.construct()
                self.assert_retired()

    def test_replacement_after_registration_retires_cache_and_child(self):
        remember = session.remember
        def replace_after_registration(context, values, **options):
            remember(context, values, **options)
            if options.get('private'):
                self.replace('synthetic-new')
        with patch.object(session, 'remember', side_effect=replace_after_registration):
            with self.assertRaises(ValueError):
                self.construct()
        self.assert_retired()
        self.assertEqual(session.credentials(self.item.context)['Secret']['password'], 'synthetic-new')

    def test_failure_after_child_publication_retires_child_and_cache(self):
        with patch.object(local_crypt, 'CryptCommand', side_effect=RuntimeError('synthetic construction failure')):
            with self.assertRaisesRegex(RuntimeError, 'synthetic construction failure'):
                self.construct()
        self.assert_retired()

    def test_unrelated_package_replacement_does_not_revoke_child(self):
        unrelated = self.root / 'other.session'
        self.addCleanup(session.forget_package_path, unrelated)
        self.addCleanup(session.forget, unrelated)
        def replace_other(_):
            for password in ('synthetic-first', 'synthetic-second'):
                session.remember(unrelated, {'Other': {'type': 'local', 'password': password}},
                                 package_path=self.root / 'other.zip')
        with patch.object(local_crypt, 'validate_ciphertext_tree', side_effect=replace_other):
            provider = self.construct()
        provider.credential_grant.check()
        self.assertFalse(provider.closed)
        provider.close()
        self.assert_retired()
        self.assertIsNotNone(session.credentials(unrelated))

    def test_initial_password_unlock_and_failed_password_preserve_ownership(self):
        from commonUtils.archives.zip_access import open_archive
        with open_archive(self.item.package, 'w', password='synthetic-package-password') as archive:
            for name, settings in self.values.items():
                archive.writestr(name + '.txt', '[' + name + ']\n' + '\n'.join(
                    key + '=' + value for key, value in settings.items()))
        session.forget(self.item.context)
        provider = self.construct(password='synthetic-package-password')
        provider.credential_grant.check()
        self.assertEqual(session.package_path(self.item.context), self.item.package)
        self.assertFalse(self.item.context.with_suffix('.conf').exists())
        provider.close()
        self.replace(package=self.root / 'unrelated.zip')
        revoked = session.revocation_check(self.item.context)
        with self.assertRaises(Exception):
            self.construct(password='synthetic-wrong-password')
        self.assertFalse(revoked())
        self.assert_retired()


class LocalCryptLifetimeTests(LocalCryptCase):
    def test_service_open_views_close_independently_and_lock_together(self):
        from features.rclone.desktop_service import service
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f, patch.object(
                executable, 'get_rclone_path', return_value=self.binary):
            first = service.localcrypt.open(f.item)
            second = service.localcrypt.open(f.item)
            self.addCleanup(first.close)
            self.addCleanup(second.close)
            browser_release = first.acquire()
            reader_release = first.acquire()
            browser_release()
            self.assertFalse(first.closed)
            self.assertEqual(first.read_bytes('note.md'), f.original)
            reader_release()
            self.assertTrue(first.closed)
            self.assertEqual(second.read_bytes('note.md'), f.original)
            service.credentials.lock(f.context)
            self.assertTrue(second.closed)
            with self.assertRaisesRegex(ValueError, 'locked'):
                second.read_bytes('note.md')

    def test_revocation_retires_private_window_and_blocks_reshow(self):
        from services.documents.ui.private_views import protect_private_view
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            window = qt.QMainWindow()
            window.setWindowTitle('Secret document sentinel')
            protect_private_view(window, f.provider)
            window.show()
            self.app.processEvents()
            session.forget(f.context)
            self.app.processEvents()
            self.assertFalse(window.isVisible())
            self.assertFalse(window.isEnabled())
            self.assertNotIn('sentinel', window.windowTitle())
            window.show()
            self.app.processEvents()
            self.assertFalse(window.isVisible())
            window.close()

    def test_private_view_guard_follows_save_as_provider(self):
        from types import SimpleNamespace
        from services.documents.ui.private_views import protect_private_view
        with TemporaryDirectory() as directory:
            first = SimpleNamespace(private=True, context=Path(directory) / 'first.session')
            second = SimpleNamespace(private=True, context=Path(directory) / 'second.session')
            for provider in (first, second):
                session.remember(provider.context, {'view': {'type': 'local'}})
                from features.rclone.document_protection import DesktopDocumentProtection
                provider.document_protection = DesktopDocumentProtection(provider)
                self.addCleanup(session.forget, provider.context)
            window = qt.QMainWindow()
            window.choice = SimpleNamespace(provider=first)
            protect_private_view(window, first)
            window.show()
            # ResourceTextWindow releases the old choice before publishing the
            # new choice. Its pending Save As destination owns the displayed draft.
            window.pending_choice = SimpleNamespace(provider=second)
            session.forget(first.context)
            self.app.processEvents()
            self.assertTrue(window.isVisible())
            window.choice, window.pending_choice = window.pending_choice, None
            session.forget(second.context)
            self.app.processEvents()
            self.assertFalse(window.isVisible())
            window.close()

    def test_forgetting_parent_removes_private_keys_and_reunlock_requires_new_provider(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            private_context = f.provider.context
            self.assertIsNotNone(session.credentials(private_context))
            session.forget(f.context)
            self.assertIsNone(session.credentials(private_context))
            copy_mapping.unlock(f.item, 'synthetic-package-password')
            with self.assertRaisesRegex(ValueError, 'Reopen'):
                f.provider.read_bytes('note.md')
            with_provider = local_crypt.CryptResources(f.item, binary=self.binary)
            try:
                self.assertEqual(with_provider.read_bytes('note.md'), f.original)
            finally:
                with_provider.close()

    def test_provider_owners_release_keys_only_after_last_document(self):
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            browser = f.provider.acquire()
            document = f.provider.acquire()
            browser()
            browser()  # Closing plus destruction is safe.
            self.assertEqual(f.provider.read_bytes('note.md'), f.original)
            document()
            self.assertIsNone(session.credentials(f.provider.context))
            self.assertTrue(f.provider.closed)

    def test_cancelled_open_never_presents_a_document(self):
        from threading import Event
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        with self.temporary_directory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            with patch('features.rclone.localcrypt.ui.views.executable.get_rclone_path', return_value=self.binary):
                view = CryptBrowserView(f.item)
                self.wait_until(lambda: not view.file_browser.operation.busy)
                entered, finish = Event(), Event()
                def prepare(provider, path):
                    entered.set()
                    finish.wait(5)
                    return f.original, {}
                with patch('features.rclone.localcrypt.ui.views.prepare_markdown', side_effect=prepare), \
                     patch('features.rclone.localcrypt.ui.views.show_document') as show:
                    view.open_document(f.item.data / 'note.md')
                    self.wait_until(entered.is_set)
                    view.open_operation.request_cancel()
                    finish.set()
                    self.wait_until(lambda: not view.open_operation.busy)
                    show.assert_not_called()
                context = view.provider.context
                # Closing may be deferred while an owned preview/listing worker
                # retires. Exercise that state deliberately instead of racing
                # the machine's completion speed and assuming close succeeded.
                pending, cancelled = Event(), Event()
                pending.set()
                view.file_browser.operations.own(pending, busy=pending.is_set, cancel=cancelled.set)
                try:
                    self.assertFalse(view.close())
                    self.assertTrue(cancelled.is_set())
                    self.assertIsNotNone(session.credentials(context))
                finally:
                    pending.clear()
                self.wait_until(view.close, message='Private browser did not finish cooperative close')
                self.assertIsNone(session.credentials(context))
