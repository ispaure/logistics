"""Desktop concealment, stale verification and explicit replay authorization."""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt


class AppState(qt.QObject):
    applicationStateChanged = qt.Signal(object)
    state = qt.Qt.ApplicationState.ApplicationActive

    def applicationState(self):
        return self.state


class DesktopVideoPrivacyTests(QtTestCase):
    def guard(self, package=None):
        from features.video.ui.privacy import VideoResumeGuard

        window = qt.QMainWindow()
        window.setCentralWidget(qt.QWidget())
        window.setWindowTitle("private.mp4")
        window.content = SimpleNamespace(provider=Mock(), check_access=Mock())
        window.player = Mock(position=lambda: 1234)
        window.audio = Mock()
        window.transport = Mock(url="http://127.0.0.1/test")
        window.caption = Mock()
        window.resume_at = 0
        app = AppState()
        with (
            patch("features.video.ui.privacy.credential_package", return_value=package),
            patch(
                "features.video.ui.privacy.qt.QApplication.instance", return_value=app
            ),
        ):
            guard = VideoResumeGuard(window)
        self.addCleanup(window.deleteLater)
        self.addCleanup(guard.dispose)
        return window, app, guard

    def test_unencrypted_or_missing_package_requires_temporary_password_before_content(
        self,
    ):
        window, app, guard = self.guard()
        self.assertTrue(guard.blocked)
        self.assertEqual(guard.stack.currentIndex(), 1)
        window.transport.suspend.assert_called_once()
        window.audio.setMuted.assert_called_with(True)
        guard.secret.setText("test-password")
        guard.confirmation.setText("wrong-confirmation")
        guard.unlock()
        self.assertFalse(guard.busy)
        self.assertTrue(guard.blocked)
        guard.secret.setText("test-password")
        guard.confirmation.setText("test-password")
        guard.unlock()
        self.wait_until(lambda: not guard.busy)
        self.assertFalse(guard.blocked)
        window.player.play.assert_not_called()
        guard.application_state(qt.Qt.ApplicationState.ApplicationInactive)
        self.assertTrue(guard.blocked)
        self.assertEqual(guard.stack.currentIndex(), 1)
        self.assertEqual(window.windowTitle(), "Session video locked")
        window.player.setSource.assert_called_with(qt.QUrl())
        guard.secret.setText("wrong-password")
        guard.unlock()
        self.wait_until(lambda: not guard.busy)
        self.assertTrue(guard.blocked)
        guard.secret.setText("test-password")
        guard.unlock()
        self.wait_until(lambda: not guard.busy)
        self.assertFalse(guard.blocked)
        window.player.play.assert_not_called()

    def test_rebackground_or_revocation_cannot_accept_stale_password_success(self):
        window, app, guard = self.guard()
        revision = guard.revision
        guard.lock()
        guard.finish(True, revision)
        self.assertTrue(guard.blocked)
        window.content.check_access.side_effect = PermissionError("revoked")
        guard.finish(True, guard.revision)
        self.assertTrue(guard.blocked)
        window.transport.resume.assert_not_called()

    def test_package_resolution_uses_the_video_owner(self):
        from features.video.ui.privacy import credential_package

        owner = SimpleNamespace(connection=SimpleNamespace(package=Path("/owner.zip")))
        with patch("services.documents.video_authorization.document_sources", return_value=[owner]):
            self.assertEqual(credential_package(object()), Path("/owner.zip"))

    def test_encrypted_owner_password_and_replaced_package_fail_closed(self):
        import pyzipper

        with TemporaryDirectory() as directory:
            package = Path(directory) / "Owner.zip"

            def write():
                with pyzipper.AESZipFile(
                    package, "w", encryption=pyzipper.WZ_AES
                ) as archive:
                    archive.setpassword(b"owner-secret")
                    archive.writestr("Secret.txt", "[Secret]\ntype = local\n")

            write()
            window, app, guard = self.guard(package)
            self.assertFalse(guard.blocked)
            guard.lock()
            guard.secret.setText("wrong-secret")
            guard.unlock()
            self.wait_until(lambda: not guard.busy)
            self.assertTrue(guard.blocked)
            guard.secret.setText("owner-secret")
            guard.unlock()
            self.wait_until(lambda: not guard.busy)
            self.assertFalse(guard.blocked)
            window.player.play.assert_not_called()
            guard.lock()
            write()  # Same password and settings, different ciphertext identity.
            guard.secret.setText("owner-secret")
            guard.unlock()
            self.wait_until(lambda: not guard.busy)
            self.assertTrue(guard.blocked)
