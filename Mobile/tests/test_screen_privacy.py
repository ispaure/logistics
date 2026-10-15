"""Native privacy policy, including Rubicon's callable custom getters."""
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from logisticsmobile.screen_privacy import ScreenPrivacy
from features.rclone.mobile.session_privacy import ResumePassword


class ScreenPrivacyTests(unittest.TestCase):
    def setUp(self):
        from features.rclone.mobile.cloud import CloudClient
        self.addCleanup(setattr, CloudClient, '_session_privacy', CloudClient._session_privacy)
        CloudClient._session_privacy = None

    def privacy(self, app, backend):
        privacy = object.__new__(ScreenPrivacy)
        privacy.app, privacy.backend = app, backend
        privacy.inactive, privacy.disposed, privacy.shield = False, False, None
        privacy.lock_view = privacy.saved_content = None
        privacy.sync_lock_view = Mock()
        return privacy

    def test_ios_background_recording_and_foreground_recovery(self):
        class Shield:
            @classmethod
            def alloc(cls):
                return cls()
            def initWithFrame(self, frame):
                self.parent = None
                return self
            def removeFromSuperview(self):
                self.parent = None

        class Window:
            captured, scene_capture, activation = False, 0, 0
            bounds = object()
            def __init__(self):
                self.screen = SimpleNamespace(isCaptured=lambda: self.captured)
                self.traitCollection = SimpleNamespace(respondsToSelector=lambda name: True,
                    sceneCaptureState=lambda: self.scene_capture)
                self.windowScene = SimpleNamespace(activationState=lambda: self.activation)
            def endEditing(self, force):
                pass
            def addSubview(self, view):
                view.parent = self

        window = Window()
        gate = ResumePassword('session-password')
        app = SimpleNamespace(main_window=SimpleNamespace(_impl=SimpleNamespace(native=window)),
            retire_private_comic_batch=Mock(),
            private_sessions=SimpleNamespace(controllers={'private': SimpleNamespace(privacy_gate=gate)}))
        privacy = self.privacy(app, 'toga_iOS.app')
        classes = {'UIView': Shield, 'UIColor': SimpleNamespace(blackColor=lambda: 'black')}
        with patch.dict(sys.modules, {'rubicon.objc': SimpleNamespace(ObjCClass=classes.__getitem__)}):
            privacy.refresh()
            self.assertIsNone(privacy.shield)
            privacy.conceal()
            privacy.app.retire_private_comic_batch.assert_called_once_with()
            self.assertIs(privacy.shield.parent, window)
            privacy.shield.parent = None
            privacy.refresh()
            self.assertIs(privacy.shield.parent, window)
            privacy.reveal()
            self.assertIsNone(privacy.shield)
            self.assertTrue(gate.locked)
            for signal in ('captured', 'scene_capture', 'activation'):
                setattr(window, signal, 1)
                privacy.refresh()
                self.assertIs(privacy.shield.parent, window)
                setattr(window, signal, 0)
                privacy.refresh()
                self.assertIsNone(privacy.shield)

            # Clearing the last private view must remove an existing shield,
            # even while inactive or captured.
            window.activation = 1
            privacy.conceal()
            shield = privacy.shield
            app.private_sessions.controllers.clear()
            privacy.refresh()
            self.assertIsNone(privacy.shield)
            self.assertIsNone(shield.parent)
            privacy.reveal()

            # Fresh launch, saved credentials and a pending import have no
            # session gate. None of UIKit's lifecycle/capture states may cover
            # that ordinary UI, including an unattached startup scene.
            app.cloud_client = SimpleNamespace(package_name='Saved.zip', session_privacy=None)
            app.cloud_pending_zip = object()
            for activation in (-1, 0, 1, 2):
                for captured in (False, True):
                    for scene_capture in (-1, 0, 1):
                        with self.subTest(activation=activation, captured=captured,
                                          scene_capture=scene_capture):
                            window.activation = activation
                            window.captured = captured
                            window.scene_capture = scene_capture
                            privacy.refresh()
                            self.assertIsNone(privacy.shield)
                            privacy.conceal()
                            self.assertIsNone(privacy.shield)
                            privacy.reveal()
                            self.assertIsNone(privacy.shield)

    def test_android_secure_window_follows_private_sessions(self):
        class Window:
            flags = 0
            def addFlags(self, flags):
                self.flags |= flags
            def clearFlags(self, flags):
                self.flags &= ~flags
        window = Window()
        gate = ResumePassword('session-password')
        app = SimpleNamespace(_impl=SimpleNamespace(native=SimpleNamespace(getWindow=lambda: window)),
            cloud_client=SimpleNamespace(session_privacy=gate),
            private_sessions=SimpleNamespace(controllers={'private': SimpleNamespace(privacy_gate=gate)}))
        privacy = self.privacy(app, 'toga_android.app')
        privacy.refresh()
        self.assertTrue(window.flags & 0x2000)
        app.cloud_client.session_privacy = None
        privacy.refresh()
        self.assertTrue(window.flags & 0x2000)
        privacy.app.private_sessions.controllers.clear()
        privacy.refresh()
        self.assertFalse(window.flags & 0x2000)

    def test_saved_crypt_and_selected_zip_do_not_enable_privacy(self):
        app = SimpleNamespace(cloud_client=SimpleNamespace(package_name='Saved.zip', session_privacy=None),
                              cloud_pending_zip=object())
        privacy = self.privacy(app, 'dummy')
        self.assertFalse(privacy.sensitive())

    def test_scene_without_client_observes_process_session_credentials(self):
        from features.rclone.mobile.cloud import CloudClient
        privacy = self.privacy(SimpleNamespace(), 'dummy')
        self.assertFalse(privacy.sensitive())
        CloudClient._session_privacy = ResumePassword('other-scene-password')
        self.assertTrue(privacy.sensitive())

    def test_only_application_scenes_can_open_workspaces(self):
        from logisticsmobile.window_scenes import is_workspace_scene
        self.assertTrue(is_workspace_scene('UIWindowSceneSessionRoleApplication'))
        for role in ('UIWindowSceneSessionRoleExternalDisplay',
                     'UIWindowSceneSessionRoleExternalDisplayNonInteractive', ''):
            self.assertFalse(is_workspace_scene(role))


class ResumeLockTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from logisticsmobile.app import LogisticsMobile
        from features.rclone.mobile.cloud import CloudClient
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        LogisticsMobile.storage_root = Path(directory.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.addCleanup(setattr, CloudClient, '_session_privacy', CloudClient._session_privacy)
        CloudClient._session_privacy = None
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.privacy = self.app.screen_privacy
        self.addCleanup(self.privacy.dispose)
        self.app.on_exit = lambda app, **kw: True
        self.gate = ResumePassword('session-password')
        self.app.cloud_client = SimpleNamespace(session_privacy=self.gate)
        self.original = self.app.main_window.content

    def unlock(self, password):
        self.privacy.lock_password.value = password
        self.app.loop.run_until_complete(self.privacy.unlock())

    def test_ios_lock_root_tracks_safe_area_and_restores_navigation_layout(self):
        impl = self.app.main_window._impl
        insets = SimpleNamespace(top=62, bottom=34, left=0, right=0)
        def navigation_layout(container):
            container.top_inset = container.bottom_inset = 0
            container.left_inset = container.right_inset = 0
        container = SimpleNamespace(native=SimpleNamespace(safeAreaInsets=insets),
                                    content=SimpleNamespace(interface=Mock()),
                                    on_native_layout=navigation_layout)
        with patch.object(impl, 'container', container, create=True), \
                patch.object(impl, 'notify_resize', create=True) as resize:
            self.privacy.backend = 'toga_iOS.app'
            self.gate.lock()
            self.privacy.sync_lock_view((self.gate,))
            self.assertEqual((container.top_inset, container.bottom_inset), (62, 34))
            self.assertIs(self.app.main_window.content, self.privacy.lock_view)
            # Rotation can move the notch to either side of the form.
            insets.top, insets.bottom, insets.left, insets.right = 0, 21, 62, 62
            container.on_native_layout(container)
            self.assertEqual((container.top_inset, container.bottom_inset,
                              container.left_inset, container.right_inset), (0, 21, 62, 62))
            resize.assert_called_with(container)
            self.gate.locked = False
            self.privacy.sync_lock_view((self.gate,))
            self.assertIs(container.on_native_layout, navigation_layout)
            self.assertEqual((container.top_inset, container.bottom_inset,
                              container.left_inset, container.right_inset), (0, 0, 0, 0))
            self.assertIs(self.app.main_window.content, self.original)
            self.privacy.backend = 'toga_dummy.app'

    def test_resume_never_restores_navigation_until_password_verified(self):
        self.privacy.conceal()
        self.assertIs(self.app.main_window.content, self.privacy.lock_view)
        self.privacy.reveal()
        self.app.show_settings()
        self.assertIs(self.app.main_window.content, self.privacy.lock_view)
        self.unlock('wrong')
        self.assertTrue(self.gate.locked)
        self.assertIs(self.app.main_window.content, self.privacy.lock_view)
        self.assertEqual(self.privacy.lock_password.value, '')
        self.unlock('session-password')
        self.assertFalse(self.gate.locked)
        self.assertIs(self.app.main_window.content, self.original)
        self.assertTrue(self.privacy.sensitive())
        self.privacy.conceal()
        self.privacy.reveal()
        self.assertTrue(self.gate.locked)

    def test_passwordless_session_requires_nonempty_confirmed_lock_password(self):
        self.app.cloud_client.session_privacy = gate = ResumePassword()
        self.privacy.refresh()
        self.assertIs(self.app.main_window.content, self.privacy.lock_view)
        self.unlock('')
        self.assertTrue(gate.locked)
        self.unlock('new-password')
        self.assertTrue(gate.locked)
        self.privacy.lock_confirmation.value = 'new-password'
        self.unlock('new-password')
        self.assertFalse(gate.locked)
        self.privacy.conceal()
        self.privacy.reveal()
        self.unlock('wrong')
        self.assertTrue(gate.locked)
        self.unlock('new-password')
        self.assertFalse(gate.locked)

    def test_rebackground_during_verification_keeps_session_locked(self):
        self.privacy.conceal()
        self.privacy.reveal()
        original = self.gate.verify
        def interrupted(password):
            result = original(password)
            self.gate.lock()  # lifecycle interruption while the worker verifies
            return result
        with patch.object(self.gate, 'verify', side_effect=interrupted):
            self.unlock('session-password')
        self.assertTrue(self.gate.locked)
        self.assertIs(self.app.main_window.content, self.privacy.lock_view)

    def test_credential_replacement_during_verification_cannot_reveal_navigation(self):
        self.privacy.conceal()
        self.privacy.reveal()
        replacement = ResumePassword('replacement-password')
        original = self.gate.verify
        def replace(password):
            result = original(password)
            self.app.cloud_client.session_privacy = replacement
            return result
        with patch.object(self.gate, 'verify', side_effect=replace):
            self.unlock('session-password')
        self.assertTrue(replacement.locked)
        self.assertIs(self.app.main_window.content, self.privacy.lock_view)

    def test_late_session_load_cannot_replace_a_locked_screen_with_unlocked_content(self):
        self.privacy.conceal()
        self.privacy.reveal()
        replacement = ResumePassword('new-password')
        self.app.cloud_client.session_privacy = replacement
        self.privacy.refresh()
        self.assertTrue(replacement.locked)
        self.assertIs(self.app.main_window.content, self.privacy.lock_view)
        self.unlock('new-password')
        self.assertIs(self.app.main_window.content, self.original)

    def test_private_view_holds_protection_after_credentials_cleared(self):
        other = ResumePassword('other-password')
        self.app.private_sessions = SimpleNamespace(controllers={
            'retained-draft': SimpleNamespace(privacy_gate=other)})
        self.privacy.conceal()
        self.privacy.reveal()
        self.unlock('session-password')
        self.assertFalse(self.gate.locked)
        self.assertTrue(other.locked)
        self.assertIs(self.app.main_window.content, self.privacy.lock_view)
        self.unlock('other-password')
        self.assertIs(self.app.main_window.content, self.original)
        self.app.cloud_client.session_privacy = None
        self.assertTrue(self.privacy.sensitive())
        self.app.private_sessions.controllers.clear()
        self.privacy.refresh()
        self.assertFalse(self.privacy.sensitive())
