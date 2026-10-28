"""Native privacy policy, including Rubicon's callable custom getters."""
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mobile.screen_privacy import ScreenPrivacy
from features.rclone.mobile.session_privacy import ResumePassword


class ScreenPrivacyTests(unittest.TestCase):
    def setUp(self):
        from features.rclone.mobile.cloud import CloudClient
        self.addCleanup(setattr, CloudClient.credential_state, 'session_privacy', CloudClient.credential_state.session_privacy)
        CloudClient.credential_state.session_privacy = None

    def privacy(self, app, backend):
        privacy = object.__new__(ScreenPrivacy)
        privacy.app, privacy.backend = app, backend
        privacy.inactive, privacy.disposed, privacy.shield = False, False, None
        privacy.lock_view = privacy.saved_content = None
        privacy.sync_lock_view = Mock()
        return privacy

    def test_android_configuration_callback_refreshes_only_its_activity(self):
        application = SimpleNamespace(registerActivityLifecycleCallbacks=Mock())
        activity = SimpleNamespace(getApplication=lambda: application)
        privacy = self.privacy(SimpleNamespace(_impl=SimpleNamespace(native=activity)), 'toga_android.app')
        privacy.refresh = Mock()
        with patch.dict(sys.modules, {
            'android.app': SimpleNamespace(Application=SimpleNamespace(ActivityLifecycleCallbacks=object)),
            'java': SimpleNamespace(dynamic_proxy=lambda interface: object),
        }):
            privacy.install_android_lifecycle()
        listener = application.registerActivityLifecycleCallbacks.call_args.args[0]
        listener.onActivityConfigurationChanged(object())
        privacy.refresh.assert_not_called()
        listener.onActivityConfigurationChanged(activity)
        privacy.refresh.assert_called_once_with()

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
        CloudClient.credential_state.session_privacy = ResumePassword('other-scene-password')
        self.assertTrue(privacy.sensitive())

    def test_only_application_scenes_can_open_workspaces(self):
        from mobile.window_scenes import is_workspace_scene
        self.assertTrue(is_workspace_scene('UIWindowSceneSessionRoleApplication'))
        for role in ('UIWindowSceneSessionRoleExternalDisplay',
                     'UIWindowSceneSessionRoleExternalDisplayNonInteractive', ''):
            self.assertFalse(is_workspace_scene(role))


class ResumeLockTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from mobile.app import LogisticsMobile
        from features.rclone.mobile.cloud import CloudClient
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        LogisticsMobile.storage_root = Path(directory.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.addCleanup(setattr, CloudClient.credential_state, 'session_privacy', CloudClient.credential_state.session_privacy)
        CloudClient.credential_state.session_privacy = None
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

    def test_lock_names_credential_files_and_updates_remaining_password_prompt(self):
        self.gate.credential_name = 'Personal.zip'
        other = ResumePassword('work-password', credential_name='Work.zip')
        self.app.private_sessions = SimpleNamespace(controllers={
            'other': SimpleNamespace(privacy_gate=other)})
        self.privacy.conceal()
        self.privacy.reveal()
        self.assertEqual(self.privacy.lock_credential.text, 'Personal.zip\nWork.zip')
        self.assertEqual(self.privacy.lock_icon.text, '🔒')
        self.assertEqual(self.privacy.lock_button.action_role, 'primary')
        self.unlock('wrong')
        self.assertEqual(self.privacy.lock_credential.text, 'Personal.zip\nWork.zip')
        self.unlock('session-password')
        self.assertEqual(self.privacy.lock_credential.text, 'Work.zip')
        self.assertEqual(self.privacy.lock_hint.text, 'Enter the password for this credential file.')
        self.assertIs(self.app.main_window.content, self.privacy.lock_view)
        self.unlock('work-password')
        self.assertIs(self.app.main_window.content, self.original)

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

    def test_browser_snapshot_and_selection_survive_repeated_password_resume(self):
        from pathlib import Path
        from mobile.browser_ui import FileBrowser
        browser = FileBrowser()
        self.addCleanup(lambda: self.app.loop.run_until_complete(browser.close()))
        provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
        rows = [dict(name=name, path=name, directory=True) for name in ('Books', 'Documents', 'Photos')]
        browser.set_entries(provider, '', rows)
        browser.sort.value = 'Name Z–A'
        self.app.loop.run_until_complete(browser.select(browser.entries[1]))
        snapshot, selected, epoch = browser.native_list.data, browser.native_list.selection, browser.epoch
        self.app.main_window.content = browser.widget
        for _ in range(3):
            self.privacy.conceal()
            self.privacy.reveal()
            self.unlock('wrong')
            self.assertIs(self.app.main_window.content, self.privacy.lock_view)
            self.unlock('session-password')
            self.assertIs(self.app.main_window.content, browser.widget)
            self.assertIs(browser.native_list.data, snapshot)
            self.assertIs(browser.native_list.selection, selected)
            self.assertEqual(browser.epoch, epoch)
            self.assertEqual([row.title for row in browser.native_list.data], ['Photos', 'Documents', 'Books'])

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

    def test_trusted_wifi_skips_only_credential_resume_and_preserves_manual_lock(self):
        self.app.preferences.save(session_trusted_wifi='true', trusted_wifi_networks='["Home", "Cottage"]')
        with patch('mobile.trusted_wifi.current_ssid', return_value='Home'):
            self.privacy.conceal()
            self.assertTrue(self.gate.locked)
            self.assertIs(self.app.main_window.content, self.privacy.lock_view)
            self.privacy.reveal()
            self.assertFalse(self.gate.locked)
            self.assertIs(self.app.main_window.content, self.original)
        with patch('mobile.trusted_wifi.current_ssid', return_value='Cottage'):
            self.privacy.conceal()
            self.privacy.reveal()
            self.assertFalse(self.gate.locked)
        with patch('mobile.trusted_wifi.current_ssid', return_value='Public'):
            self.privacy.conceal()
            self.privacy.reveal()
            self.assertTrue(self.gate.locked)
        # Returning to a trusted network cannot bypass the outstanding challenge.
        with patch('mobile.trusted_wifi.current_ssid', return_value='Home'):
            self.privacy.conceal()
            self.privacy.reveal()
            self.assertTrue(self.gate.locked)
            self.unlock('session-password')
            self.privacy.conceal()
            self.privacy.reveal()
            self.assertFalse(self.gate.locked)
            self.gate.lock()  # A lock outside the lifecycle must remain locked.
            self.privacy.conceal()
            self.privacy.reveal()
            self.assertTrue(self.gate.locked)

    def test_wifi_is_not_read_when_setting_is_off(self):
        with patch('mobile.trusted_wifi.current_ssid') as read:
            self.privacy.conceal()
            self.privacy.reveal()
            read.assert_not_called()
            self.assertTrue(self.gate.locked)

    def test_stale_ios_wifi_result_cannot_reveal_after_another_background_transition(self):
        import asyncio
        self.app.preferences.save(session_trusted_wifi='true', trusted_wifi_networks='["Home"]')
        self.privacy.conceal()
        revision = self.privacy.wifi_revision
        ready = self.app.loop.create_future()
        async def read(app):
            return await ready
        with patch('mobile.trusted_wifi.read_ssid', side_effect=read):
            task = self.app.loop.create_task(self.privacy.resume_on_wifi(revision))
            self.app.loop.run_until_complete(asyncio.sleep(0))
            self.privacy.conceal()
            ready.set_result('Home')
            self.app.loop.run_until_complete(task)
        self.assertTrue(self.gate.locked)
        self.assertTrue(self.privacy.inactive)
        self.assertIs(self.app.main_window.content, self.privacy.lock_view)

    def test_duplicate_background_notifications_preserve_wifi_resume(self):
        self.app.preferences.save(session_trusted_wifi='true', trusted_wifi_networks='["Home"]')
        with patch('mobile.trusted_wifi.current_ssid', return_value='Home'):
            self.privacy.conceal()  # app notification
            self.privacy.conceal()  # scene notification for the same backgrounding
            self.assertTrue(self.gate.locked)
            self.privacy.reveal()
            self.assertFalse(self.gate.locked)
            self.assertIs(self.app.main_window.content, self.original)

    def test_ios_document_stays_hidden_until_wifi_verification_finishes(self):
        import asyncio
        self.app.preferences.save(session_trusted_wifi='true', trusted_wifi_networks='["Home"]')
        original_refresh = self.privacy.refresh
        def refresh_without_uikit():
            # Exercise the real lock-root policy on the dummy host while the
            # iOS resume path waits on its asynchronous native SSID result.
            self.privacy.backend = 'toga_dummy.app'
            try:
                original_refresh()
            finally:
                self.privacy.backend = 'toga_iOS.app'
        for ssid in ('Home', 'Public', None):
            with self.subTest(ssid=ssid):
                self.privacy.backend = 'toga_dummy.app'
                self.gate.locked = False  # Already authenticated before leaving.
                self.privacy.refresh()
                self.privacy.conceal()
                self.privacy.backend = 'toga_iOS.app'
                ready = self.app.loop.create_future()
                async def read(app):
                    return await ready
                with patch('mobile.trusted_wifi.read_ssid', side_effect=read), \
                        patch.object(self.privacy, 'refresh', side_effect=refresh_without_uikit), \
                        patch.object(self.privacy, 'resume_reader') as resume_reader:
                    self.privacy.reveal()
                    self.app.loop.run_until_complete(asyncio.sleep(0))
                    self.assertTrue(self.privacy.inactive)
                    self.assertTrue(self.gate.locked)
                    self.assertIs(self.app.main_window.content, self.privacy.lock_view)
                    resume_reader.assert_not_called()
                    ready.set_result(ssid)
                    pending = [task for task in asyncio.all_tasks(self.app.loop)
                               if task.get_coro().__name__ == 'resume_on_wifi']
                    self.app.loop.run_until_complete(asyncio.gather(*pending))
                    self.assertFalse(self.privacy.inactive)
                    if ssid == 'Home':
                        self.assertFalse(self.gate.locked)
                        self.assertIs(self.app.main_window.content, self.original)
                    else:
                        self.assertTrue(self.gate.locked)
                        self.assertIs(self.app.main_window.content, self.privacy.lock_view)
                self.privacy.backend = 'toga_dummy.app'
