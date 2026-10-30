"""Document protection works with provider capabilities, without backend identity."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace
from unittest.mock import Mock
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from services.documents.protection import document_protections
from services.documents.ui.private_views import protect_private_view, prepare_credential_lock
from services.documents.video_authorization import resume_authorization


class Protection:
    def __init__(self):
        self.revoked = False
        self.callbacks = []

    def check(self):
        if self.revoked:
            raise ValueError('Fixture revoked')

    def on_revoke(self, callback):
        self.callbacks.append(callback)
        return lambda: self.callbacks.remove(callback)

    def affected_by(self, keys):
        return 'fixture-source' in keys

    def revoke(self):
        self.revoked = True
        for callback in tuple(self.callbacks):
            callback()


class DocumentProtectionTests(QtTestCase):
    def window(self, provider):
        window = qt.QMainWindow()
        self.addCleanup(window.deleteLater)
        protect_private_view(window, provider)
        return window

    def test_non_rclone_provider_revokes_through_wrappers_and_prompts_only_its_source(self):
        protection = Protection()
        provider = SimpleNamespace(document_protection=protection)
        wrapper = SimpleNamespace(provider=provider)
        window = self.window(wrapper)
        window.prepare_credential_lock = Mock(return_value=False)
        self.assertTrue(prepare_credential_lock(['another-source']))
        window.prepare_credential_lock.assert_not_called()
        self.assertFalse(prepare_credential_lock(['fixture-source']))
        protection.revoke()
        self.assertTrue(window._private_view_guard.locked)
        self.assertFalse(window.isEnabled())
        window._private_view_guard.unsubscribe()
        self.assertEqual(protection.callbacks, [])

    def test_retarget_unsubscribes_old_source_and_immediately_checks_new_source(self):
        first, second = Protection(), Protection()
        provider = SimpleNamespace(document_protection=first)
        window = self.window(provider)
        window.resource_provider = lambda: SimpleNamespace(document_protection=second)
        second.revoked = True
        window._private_view_guard.check_revocation()
        self.assertEqual(first.callbacks, [])
        self.assertTrue(window._private_view_guard.locked)

    def test_wrapped_authorizations_all_apply_and_repeated_protection_is_deduplicated(self):
        first = SimpleNamespace(password_gate=None, verify=Mock(return_value=True))
        second = SimpleNamespace(password_gate=None, verify=Mock(return_value=False))
        outer = SimpleNamespace(resume_authorization=lambda: first)
        inner = SimpleNamespace(resume_authorization=lambda: second)
        provider = SimpleNamespace(document_protection=outer,
            provider=SimpleNamespace(document_protection=inner))
        proof = resume_authorization(provider)
        self.assertFalse(proof.verify('fixture'))
        first.verify.assert_called_once_with('fixture')
        second.verify.assert_called_once_with('fixture')
        provider.provider.document_protection = outer
        self.assertEqual(tuple(document_protections(provider)), (outer,))

    def test_missing_provider_proof_requires_a_temporary_password(self):
        proof = resume_authorization(SimpleNamespace())
        self.assertIsNotNone(proof.password_gate)
        self.assertFalse(proof.verify(''))
        self.assertTrue(proof.verify('temporary'))
        self.assertFalse(proof.verify('different'))
        self.assertTrue(proof.verify('temporary'))

    def test_rejected_wrapped_credential_does_not_configure_temporary_password(self):
        from services.documents.protection import TemporaryResumeAuthorization
        from services.documents.video_authorization import CombinedResumeAuthorization
        temporary = TemporaryResumeAuthorization()
        credential = SimpleNamespace(password_gate=None, verify=lambda secret: secret == 'correct')
        proof = CombinedResumeAuthorization((temporary, credential))
        self.assertFalse(proof.verify('incorrect'))
        self.assertIsNone(temporary.password_gate.proof)
        self.assertTrue(proof.verify('correct'))
        self.assertFalse(proof.verify('incorrect'))

    def test_destroying_window_unsubscribes_provider_revocation(self):
        from shiboken6 import delete, isValid
        protection = Protection()
        window = qt.QMainWindow()
        try:
            protect_private_view(window, SimpleNamespace(document_protection=protection))
            self.assertEqual(len(protection.callbacks), 1)
            delete(window)
            self.assertEqual(protection.callbacks, [])
        finally:
            if isValid(window):
                delete(window)

    def test_wrapped_setup_exposes_an_unconfigured_gate_for_confirmation(self):
        from services.documents.protection import TemporaryResumeAuthorization
        from services.documents.video_authorization import CombinedResumeAuthorization
        established, pending = TemporaryResumeAuthorization(), TemporaryResumeAuthorization()
        established.verify('correct')
        proof = CombinedResumeAuthorization((established, pending))
        self.assertIs(proof.password_gate, pending.password_gate)
        self.assertIsNone(proof.password_gate.proof)
        self.assertFalse(proof.verify('incorrect'))
        self.assertIsNone(pending.password_gate.proof)
        self.assertTrue(proof.verify('correct'))

    def test_failed_content_retirement_still_disables_and_redacts_the_window(self):
        window = self.window(SimpleNamespace())
        window.setWindowTitle('Sensitive filename')
        window.retire_private_content = Mock(side_effect=RuntimeError('fixture cleanup failed'))
        with self.assertRaisesRegex(RuntimeError, 'fixture cleanup failed'):
            window._private_view_guard.retire()
        self.assertTrue(window._private_view_guard.locked)
        self.assertFalse(window.isEnabled())
        self.assertEqual(window.windowTitle(), 'Private session locked')
        window.retire_private_content = Mock()
        window._private_view_guard.retire()
        window._private_view_guard.retire()
        window.retire_private_content.assert_called_once()

    def test_reentrant_content_retirement_is_not_run_twice(self):
        window = self.window(SimpleNamespace())
        calls = []
        def retire():
            calls.append('retired')
            if len(calls) == 1:
                window._private_view_guard.retire()
        window.retire_private_content = retire
        window._private_view_guard.retire()
        self.assertEqual(calls, ['retired'])

    def test_unsubscribe_attempts_all_sources_and_keeps_failed_cleanup_for_retry(self):
        first, second = Protection(), Protection()
        original = first.on_revoke
        fail = [True]
        def subscribe(callback):
            release = original(callback)
            def unsubscribe():
                if fail[0]:
                    raise ValueError('fixture unsubscribe failed')
                release()
            return unsubscribe
        first.on_revoke = subscribe
        provider = SimpleNamespace(document_protection=first,
            provider=SimpleNamespace(document_protection=second))
        window = self.window(provider)
        with self.assertRaisesRegex(ValueError, 'fixture unsubscribe failed'):
            window._private_view_guard.unsubscribe()
        self.assertEqual(second.callbacks, [])
        fail[0] = False
        window._private_view_guard.unsubscribe()
        self.assertEqual(first.callbacks, [])

    def test_failed_provider_handoff_locks_the_display_before_reporting_error(self):
        first, second = Protection(), Protection()
        window = self.window(SimpleNamespace(document_protection=first))
        guard = window._private_view_guard
        release = guard.subscriptions[0]
        def fail():
            raise RuntimeError('fixture handoff failed')
        guard.subscriptions[0] = fail
        window.setWindowTitle('Sensitive destination')
        window.resource_provider = lambda: SimpleNamespace(document_protection=second)
        with self.assertRaisesRegex(RuntimeError, 'fixture handoff failed'):
            guard.check_revocation()
        self.assertTrue(guard.locked)
        self.assertFalse(window.isEnabled())
        self.assertEqual(window.windowTitle(), 'Private session locked')
        guard.subscriptions[0] = release
        guard.unsubscribe()

    def test_missing_ordinary_source_does_not_retire_the_retained_dirty_document(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.storage import DocumentResource
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'draft.txt'
            path.write_bytes(b'Original')
            with DocumentResource(LocalFiles(folder), 'draft.txt', max_bytes=100) as resource:
                resource.read()
                window = self.window(resource)
                window.editor = qt.QPlainTextEdit(window)
                window.editor.setPlainText('Unsaved edits')
                window.retire_private_content = Mock()
                path.unlink()
                window._private_view_guard.check_revocation()
                self.assertFalse(window._private_view_guard.locked)
                self.assertTrue(window.isEnabled())
                self.assertEqual(window.editor.toPlainText(), 'Unsaved edits')
                window.retire_private_content.assert_not_called()

    def test_failed_provider_resolution_conceals_the_window_and_reports_the_error(self):
        window = self.window(SimpleNamespace())
        window.setWindowTitle('Sensitive source')
        window.resource_provider = Mock(side_effect=RuntimeError('fixture source unavailable'))
        with self.assertRaisesRegex(RuntimeError, 'fixture source unavailable'):
            window._private_view_guard.check_revocation()
        self.assertTrue(window._private_view_guard.locked)
        self.assertFalse(window.isEnabled())
        self.assertEqual(window.windowTitle(), 'Private session locked')
