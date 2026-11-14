"""Native privacy policy, including Rubicon's callable custom getters."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, call, patch

from mobile.screen_privacy import ScreenPrivacy
from services.session_auth import ResumePassword


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
        privacy.lock_gates = ()
        privacy.sync_lock_view = Mock()
        from mobile.protection import for_app
        scope = for_app(app)
        self.addCleanup(scope.dispose)
        scope.register(app, lambda: tuple(getattr(owner, 'privacy_gate', None)
            for owner in getattr(getattr(app, 'private_sessions', None), 'controllers', {}).values()))
        return privacy

    def fake_ios(self, center):
        window = SimpleNamespace(respondsToSelector=Mock(return_value=False))
        impl = type('Impl', (), {'__module__': 'toga_iOS.app'})()
        app = SimpleNamespace(_impl=impl, main_window=SimpleNamespace(_impl=SimpleNamespace(native=window)))
        objc = SimpleNamespace(ObjCClass=lambda name: SimpleNamespace(defaultCenter=center),
                               Block=lambda callback, *signature: callback, objc_id=object())
        return app, patch.dict(sys.modules, {'rubicon.objc': objc})

    def assert_constructor_rollback(self, app, native, failure, refresh_error=None):
        from features.rclone.mobile.cloud import CloudClient
        from mobile.protection import for_credentials

        credentials = CloudClient.credential_state
        process = for_credentials(credentials)
        observers, listeners = set(credentials.observers), set(process.listeners)
        windows = set(process.windows)
        with native, patch.object(ScreenPrivacy, 'refresh', side_effect=refresh_error):
            with self.assertRaises(RuntimeError) as raised:
                app.screen_privacy = ScreenPrivacy(app)
        self.assertIs(raised.exception, failure)
        self.assertFalse(hasattr(app, 'screen_privacy'))
        self.assertEqual(set(credentials.observers), observers)
        self.assertEqual(set(process.listeners), listeners)
        self.assertEqual(set(process.windows), windows)
        self.assertFalse(app._layout_participants.entries)

    def test_ordinary_reader_interruption_clears_guidance_and_repeat(self):
        import asyncio
        from mobile.comic_feedback import boundary, clear

        class Host:
            pass

        app, owner = Host(), Host()
        app.loop = asyncio.new_event_loop()
        app._impl, app.active_host = SimpleNamespace(), True
        owner.app, owner.session = app, SimpleNamespace(id='ordinary-comic')
        owner.resume_suspended_page = Mock()
        app.readers = SimpleNamespace(active=owner)
        app.visible_reader = lambda: owner.session.id
        self.addCleanup(close_loop, app.loop)
        self.addCleanup(clear, app)
        privacy = app.screen_privacy = self.privacy(app, 'toga_dummy.app')
        self.assertFalse(privacy.sensitive())
        adjacent, native = AsyncMock(), Mock()
        with patch('mobile.comic_guidance.present', side_effect=[native, Mock()]) as present, \
                patch.object(privacy, 'conceal') as conceal:
            app.loop.run_until_complete(boundary(owner, 1, right_to_left=False,
                available=True, adjacent=adjacent))
            feedback = app._comic_boundary_feedback
            subscription, timer = feedback.subscription, feedback.timer
            self.assertTrue(feedback.armed)
            self.assertIn(subscription.key, subscription.participants.entries)

            privacy.interrupt()

            conceal.assert_not_called()
            self.assertFalse(privacy.inactive)
            native.close.assert_called_once()
            self.assertTrue(timer.cancelled())
            self.assertNotIn(subscription.key, subscription.participants.entries)
            self.assertIsNone(feedback.native)
            self.assertIsNone(feedback.timer)
            self.assertIsNone(feedback.owner)
            self.assertFalse(feedback.message)
            self.assertFalse(feedback.armed)
            privacy.reveal()
            self.assertIs(app.readers.active, owner)
            owner.resume_suspended_page.assert_called_once()
            self.assertEqual(present.call_count, 1)

            # Returning to this reader starts a fresh deliberate-repeat gesture.
            app.loop.run_until_complete(boundary(owner, 1, right_to_left=False,
                available=True, adjacent=adjacent))
            adjacent.assert_not_awaited()
            self.assertTrue(feedback.armed)
            self.assertIn('next volume', feedback.message)

    def test_partial_ios_registration_is_rolled_back(self):
        stages = (*range(6), 'trait setup', 'trait registration', 'refresh')
        for stage in stages:
            with self.subTest(stage=stage):
                failure = RuntimeError('setup failed')
                tokens = [object() for _ in range(6)]
                # A failed registration supplies no token to unregister.
                expected = tokens[:stage] if isinstance(stage, int) else tokens
                registrations = [*expected, failure] if isinstance(stage, int) else tokens
                center = SimpleNamespace(addObserverForName=Mock(side_effect=registrations), removeObserver=Mock())
                app, native = self.fake_ios(center)
                window = app.main_window._impl.native
                window.respondsToSelector.return_value = True
                trait = object()
                window.registerForTraitChanges = Mock(return_value=trait)
                window.unregisterForTraitChanges = Mock()
                if stage == 'trait setup':
                    window.respondsToSelector.side_effect = failure
                elif stage == 'trait registration':
                    window.registerForTraitChanges.side_effect = failure
                self.assert_constructor_rollback(
                    app, native, failure, refresh_error=failure if stage == 'refresh' else None)
                self.assertEqual([call.args[0] for call in center.removeObserver.call_args_list], expected)
                if stage == 'refresh':
                    window.unregisterForTraitChanges.assert_called_once_with(trait)
                else:
                    window.unregisterForTraitChanges.assert_not_called()

    def test_partial_android_registration_is_rolled_back(self):
        for stage in ('get application', 'register listener', 'refresh'):
            with self.subTest(stage=stage):
                failure = RuntimeError('setup failed')
                application = SimpleNamespace(registerActivityLifecycleCallbacks=Mock(),
                                              unregisterActivityLifecycleCallbacks=Mock())
                activity = SimpleNamespace(getApplication=Mock(return_value=application))
                impl = type('Impl', (), {'__module__': 'toga_android.app', 'native': activity})()
                app = SimpleNamespace(_impl=impl)
                if stage == 'get application':
                    activity.getApplication.side_effect = failure
                elif stage == 'register listener':
                    application.registerActivityLifecycleCallbacks.side_effect = failure
                native = patch.dict(sys.modules, {
                    'android.app': SimpleNamespace(Application=SimpleNamespace(ActivityLifecycleCallbacks=object)),
                    'java': SimpleNamespace(dynamic_proxy=lambda interface: object),
                })
                self.assert_constructor_rollback(
                    app, native, failure, refresh_error=failure if stage == 'refresh' else None)
                if stage == 'get application':
                    application.registerActivityLifecycleCallbacks.assert_not_called()
                    application.unregisterActivityLifecycleCallbacks.assert_not_called()
                else:
                    listener = application.registerActivityLifecycleCallbacks.call_args.args[0]
                    application.unregisterActivityLifecycleCallbacks.assert_called_once_with(listener)
                    with patch.object(ScreenPrivacy, 'reveal') as reveal:
                        listener.onActivityResumed(activity)
                    reveal.assert_not_called()

    def test_disposal_retries_failed_observer_and_blocks_queued_delivery(self):
        from features.rclone.mobile.cloud import CloudClient
        tokens = [object() for _ in range(6)]
        center = SimpleNamespace(addObserverForName=Mock(side_effect=tokens),
                                 removeObserver=Mock(side_effect=[RuntimeError('removal failed')] + [None] * 6))
        app, native = self.fake_ios(center)
        with native, patch.object(ScreenPrivacy, 'refresh'):
            privacy = ScreenPrivacy(app)
        with self.assertRaisesRegex(RuntimeError, 'removal failed'):
            privacy.dispose()
        self.assertFalse(app._layout_participants.entries)
        self.assertNotIn(privacy, app._protection.process.listeners)
        self.assertNotIn(privacy, CloudClient.credential_state.observers)
        for call in center.addObserverForName.call_args_list:
            call.kwargs['usingBlock'](None)
        self.assertFalse(privacy.inactive)
        self.assertFalse(privacy.interrupted)
        privacy.dispose()
        privacy.dispose()
        self.assertEqual([call.args[0] for call in center.removeObserver.call_args_list],
                         tokens + tokens[:1])

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
            private_sessions=SimpleNamespace(flush_visible_progress=Mock(), controllers={'private': SimpleNamespace(privacy_gate=gate)}))
        privacy = self.privacy(app, 'toga_iOS.app')
        classes = {'UIView': Shield, 'UIColor': SimpleNamespace(blackColor=lambda: 'black')}
        with patch.dict(sys.modules, {'rubicon.objc': SimpleNamespace(ObjCClass=classes.__getitem__)}):
            privacy.refresh()
            self.assertIsNone(privacy.shield)
            app.video_player = SimpleNamespace(conceal=Mock(), reveal=Mock(), retire_changed_policy=Mock())
            privacy.interrupt()
            self.assertIs(privacy.shield.parent, window)
            self.assertTrue(gate.locked)
            self.assertTrue(privacy.inactive)
            privacy.refresh()  # A progress/credential refresh while Control Center is up.
            self.assertTrue(gate.locked)
            app.video_player.conceal.assert_called()
            privacy.reveal()
            self.assertIsNone(privacy.shield)
            self.assertTrue(gate.locked)  # Returning without backgrounding still needs a password.
            self.assertFalse(privacy.inactive)
            self.assertTrue(gate.verify('session-password'))
            self.assertTrue(gate.authorize(gate.revision))
            privacy.app.retire_private_comic_batch.reset_mock()
            privacy.interrupt()
            privacy.conceal()
            self.assertTrue(gate.locked)
            app.video_player.conceal.assert_called()
            self.assertEqual(privacy.app.retire_private_comic_batch.call_count, 2)
            self.assertIs(privacy.shield.parent, window)
            privacy.shield.parent = None
            privacy.refresh()
            self.assertIs(privacy.shield.parent, window)
            privacy.reveal()
            self.assertIsNone(privacy.shield)
            self.assertTrue(gate.locked)
            # A broken native pause cannot prevent the synchronous capture shield.
            window.captured = True
            app.video_player = SimpleNamespace(conceal=Mock(side_effect=RuntimeError('pause failed')),
                                              reveal=Mock(), retire_changed_policy=Mock())
            with self.assertRaisesRegex(RuntimeError, 'pause failed'):
                privacy.refresh()
            self.assertIs(privacy.shield.parent, window)
            del app.video_player
            window.captured = False
            privacy.refresh()
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
            app.video_player = SimpleNamespace(conceal=Mock(), reveal=Mock(), retire_changed_policy=Mock())
            window.activation = 1
            privacy.interrupt()
            privacy.refresh()
            self.assertIsNone(privacy.shield)
            self.assertFalse(privacy.inactive)
            self.assertFalse(privacy.resume_locked)
            app.video_player.conceal.assert_not_called()
            window.activation = 0
            privacy.reveal()
            self.assertIsNone(privacy.shield)
            app.video_player.conceal.assert_not_called()
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
            private_sessions=SimpleNamespace(flush_visible_progress=Mock(), controllers={'private': SimpleNamespace(privacy_gate=gate)}))
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
        self.addCleanup(close_loop, self.app.loop)
        self.addCleanup(self.app.main_window.close)
        self.privacy = self.app.screen_privacy
        self.addCleanup(self.privacy.dispose)
        self.app.on_exit = lambda app, **kw: True
        self.gate = ResumePassword('session-password')
        self.app.cloud_client = SimpleNamespace(session_privacy=self.gate)
        from mobile.protection import for_app
        scope = for_app(self.app)
        self.addCleanup(scope.process.register_credentials(self, lambda: tuple(gate for gate in
            (getattr(self.app.cloud_client, 'session_privacy', None),) if gate is not None)))
        # These tests replace real managers with small retained-draft fixtures.
        scope.register(self, lambda: tuple(getattr(owner, 'privacy_gate', None)
            for owner in getattr(getattr(self.app, 'private_sessions', None), 'controllers', {}).values()))
        self.original = self.app.main_window.content
        import asyncio
        self.app.loop.run_until_complete(asyncio.sleep(0))

    def unlock(self, password):
        self.privacy.lock_password.value = password
        self.app.loop.run_until_complete(self.privacy.unlock())

    def test_android_keyboard_fit_ignores_the_previous_root_minimum_height(self):
        self.privacy.conceal()
        self.privacy.reveal()
        self.privacy.fit_lock_view(360, 724)
        self.assertEqual(self.privacy.lock_card.style.height, 520)
        self.privacy.backend = 'toga_android.app'
        try:
            with patch.object(self.privacy, 'android_lock_viewport', return_value=(360, 449)):
                self.privacy.fit_lock_view()
            self.assertLessEqual(self.privacy.lock_card.style.height + 40, 449)
            with patch.object(self.privacy, 'android_lock_viewport', return_value=(800, 140)):
                self.privacy.fit_lock_view()
            self.assertLessEqual(self.privacy.lock_card.style.height + 40, 140)
            self.assertEqual(self.privacy.lock_card.style.width, 560)
            with patch.object(self.privacy, 'android_lock_viewport', return_value=(800, 96)):
                self.privacy.fit_lock_view()
            self.assertLessEqual(self.privacy.lock_card.style.height + 2 * self.privacy.lock_body.style.margin_top, 96)
            self.assertGreaterEqual(self.privacy.lock_card.style.height - 24, 48)
        finally:
            self.privacy.backend = 'toga_dummy.app'

    def test_lock_card_keeps_corners_inside_viewport_and_scrolls_wrapped_form(self):
        import toga
        self.gate.credential_name = 'Very long credential name ' * 20 + '.zip'
        self.privacy.conceal()
        self.privacy.reveal()
        scroll = self.privacy.lock_scroll
        self.assertIsInstance(scroll, toga.ScrollContainer)
        self.assertEqual(scroll._MIN_HEIGHT, 0)
        self.assertIs(scroll.content, self.privacy.lock_layout)
        self.assertEqual(self.privacy.lock_card.children, [scroll])
        self.assertEqual(self.privacy.lock_view.children, [self.privacy.lock_body])
        self.assertEqual(scroll.style.flex, 1)
        self.assertGreater(self.privacy.lock_body.style.margin_left, 0)
        self.assertGreater(self.privacy.lock_body.style.margin_top, 0)
        self.assertEqual(self.privacy.lock_card.style.margin_top, 0)
        self.assertIn('\n', self.privacy.lock_credential.text)
        for width, height in ((320, 568), (844, 390), (844, 170), (1200, 900)):
            self.privacy.fit_lock_view(width, height)
            fields, icon = self.privacy.lock_fields, self.privacy.lock_icon
            self.assertEqual(self.privacy.lock_layout.children,
                             [icon, fields] if width < 540 else [fields, icon])
            self.assertLessEqual(self.privacy.lock_card.style.width, width - 40)
            self.assertLessEqual(self.privacy.lock_card.style.width, 560)
            self.assertLessEqual(self.privacy.lock_card.style.height, height - 40)
            self.assertLessEqual(self.privacy.lock_card.style.height, 520)
        self.unlock('session-password')
        self.assertIs(self.app.main_window.content, self.original)

    def test_lock_names_credential_files_and_updates_remaining_password_prompt(self):
        self.gate.credential_name = 'Personal.zip'
        other = ResumePassword('work-password', credential_name='Work.zip')
        self.app.private_sessions = SimpleNamespace(flush_visible_progress=Mock(), controllers={
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
        self.assertEqual(self.privacy.lock_hint.text.replace('\n', ' '), 'Enter the password for this credential file.')
        self.assertIs(self.app.main_window.content, self.privacy.lock_view)
        self.unlock('work-password')
        self.assertIs(self.app.main_window.content, self.original)

    def test_ios_lock_root_tracks_safe_area_and_restores_navigation_layout(self):
        impl = self.app.main_window._impl
        insets = SimpleNamespace(top=62, bottom=34, left=0, right=0)
        def navigation_layout(container):
            container.top_inset = container.bottom_inset = 0
            container.left_inset = container.right_inset = 0
        container = SimpleNamespace(native=SimpleNamespace(safeAreaInsets=insets,
                                    bounds=SimpleNamespace(size=SimpleNamespace(height=self.app.main_window.size.height))),
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
        for leave in (self.privacy.interrupt, self.privacy.conceal, self.privacy.interrupt):
            leave()
            self.privacy.reveal()
            self.unlock('wrong')
            self.assertIs(self.app.main_window.content, self.privacy.lock_view)
            self.unlock('session-password')
            self.assertIs(self.app.main_window.content, browser.widget)
            self.assertIs(browser.native_list.data, snapshot)
            self.assertIs(browser.native_list.selection, selected)
            self.assertEqual(browser.epoch, epoch)
            self.assertEqual([row.title for row in browser.native_list.data], ['Photos', 'Documents', 'Books'])

    def test_directory_index_resumes_only_after_authentication_and_scene_activation(self):
        lease = self.app._directory_index_host
        self.addCleanup(lease.close)
        with patch.object(lease, 'set_active', wraps=lease.set_active) as set_active:
            self.app.scene_active = False
            self.privacy.interrupt()
            self.privacy.reveal()
            self.unlock('wrong')
            self.unlock('session-password')
            self.assertFalse(self.gate.locked)
            set_active.assert_called_with(False)
            self.assertNotIn(call(True), set_active.call_args_list)

            self.app.scene_active = True
            self.privacy.reveal()
            set_active.assert_called_with(True)
            set_active.reset_mock()

            self.privacy.conceal()
            self.privacy.reveal()
            self.assertTrue(self.gate.locked)
            self.assertNotIn(call(True), set_active.call_args_list)
            self.unlock('session-password')
            set_active.assert_called_with(True)

    def test_queued_browser_search_result_is_fenced_across_lock_and_unlock(self):
        import asyncio
        from pathlib import Path
        from commonUtils.search.providers import SearchResult
        from mobile.browser_ui import FileBrowser

        browser = FileBrowser()
        self.addCleanup(lambda: self.app.loop.run_until_complete(browser.close()))
        self.app.body = browser.widget
        self.app.main_window.content = browser.widget
        provider = SimpleNamespace(root=Path('/virtual'), relative=lambda value: value, list=lambda *_: [])
        browser.set_entries(provider, '', [])
        browser.open_search()
        scans = []
        pending_progress = self.app.loop.create_future()

        def capture(progress, result):
            self.privacy.conceal()
            pending_progress.set_result((progress, result))

        def search(provider, folder, query, *, cancelled, progress):
            scans.append(cancelled)
            name = 'match-stale.md' if len(scans) == 1 else 'match-current.md'
            result = SearchResult([dict(path=name, name=name, directory=False)], 1, True, [])
            if len(scans) == 1:
                self.app.loop.call_soon_threadsafe(capture, progress, result)
            return result

        async def check():
            browser.search.value = 'match'
            progress, stale = await asyncio.wait_for(pending_progress, 5)
            self.assertEqual(browser.search.value, 'match')
            self.assertFalse(browser.native_list.data)
            self.privacy.reveal()
            self.assertTrue(self.gate.locked)
            revision = self.gate.revision
            self.assertTrue(self.gate.authorize(revision))
            self.privacy.refresh()
            progress(stale)
            await asyncio.sleep(0)
            self.assertTrue(scans[0]())
            self.assertFalse(browser.native_list.data)
            while tasks := tuple(task for task in browser.tasks if not task.done()):
                await asyncio.wait_for(asyncio.gather(*tasks), 5)
            self.assertEqual([row.entry.payload['path'] for row in browser.native_list.data], ['match-current.md'])

        with patch.object(browser, 'resource_search', side_effect=search):
            self.app.loop.run_until_complete(check())

    def test_notes_drawers_are_detached_before_password_resume(self):
        import toga
        from features.notes_library.mobile.drawers import NotesDrawers
        from mobile.composition.presentation import notes_drawer_host
        for side in ('files', 'links'):
            with self.subTest(side=side):
                drawer = NotesDrawers(toga.Box(), toga.Box(), toga.Box(), host=notes_drawer_host(self.app))
                drawer.show(side)
                overlay = drawer.overlay
                self.assertIsNotNone(overlay)
                popup, native = Mock(), Mock()
                overlay.popup = popup
                overlay.container = SimpleNamespace(native=native, content=object())
                self.privacy.conceal()
                popup.dismiss.assert_called_once()
                native.removeFromSuperview.assert_called_once()
                self.assertIsNone(drawer.overlay)
                self.assertIsNone(drawer.side)
                self.assertIsNone(overlay.panel.overlay)
                self.assertIs(self.app.main_window.content, self.privacy.lock_view)
                self.privacy.reveal()
                drawer.show(side)
                self.assertIsNone(drawer.overlay)
                self.unlock('wrong')
                drawer.show(side)
                self.assertIsNone(drawer.overlay)
                self.unlock('session-password')
                drawer.show(side)
                self.assertIsNotNone(drawer.overlay)
                drawer.dispose()

    def test_lock_removes_a_panel_already_animating_closed(self):
        import toga
        from features.notes_library.mobile.drawers import NotesDrawers
        from mobile.composition.presentation import notes_drawer_host
        drawer = NotesDrawers(toga.Box(), toga.Box(), toga.Box(), host=notes_drawer_host(self.app))
        drawer.show_links()
        overlay = drawer.overlay
        popup = Mock()
        overlay.popup = popup
        with patch('features.notes_library.mobile.drawer_motion.slide_out', return_value=60):
            drawer.show_detail()
        self.assertEqual(len(drawer.retiring), 1)
        popup.dismiss.assert_not_called()
        self.gate.lock()
        self.privacy.refresh()
        popup.dismiss.assert_called_once()
        self.assertIsNone(overlay.popup)
        self.assertIs(self.app.main_window.content, self.privacy.lock_view)
        drawer.dispose()
        self.assertEqual(drawer.retiring, [])

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

    def test_session_loaded_during_ordinary_interruption_requires_password(self):
        for refresh_before_return in (True, False):
            with self.subTest(refresh_before_return=refresh_before_return):
                self.app.cloud_client.session_privacy = None
                self.privacy.refresh()
                self.privacy.interrupt()
                self.assertFalse(self.privacy.inactive)
                self.app.cloud_client.session_privacy = ResumePassword('new-password')
                if refresh_before_return:
                    self.privacy.refresh()
                    self.assertTrue(self.app.cloud_client.session_privacy.locked)
                self.privacy.reveal()
                self.assertTrue(self.app.cloud_client.session_privacy.locked)
                self.assertIs(self.app.main_window.content, self.privacy.lock_view)
                self.unlock('new-password')
                self.assertIs(self.app.main_window.content, self.original)

    def test_interruption_and_return_during_password_check_rejects_old_result(self):
        self.privacy.interrupt()
        self.privacy.reveal()
        async def verify_then_interrupt(function, *args):
            result = function(*args)
            self.privacy.interrupt()
            self.privacy.reveal()
            return result
        with patch('asyncio.to_thread', side_effect=verify_then_interrupt):
            self.unlock('session-password')
        self.assertTrue(self.gate.locked)
        self.assertIs(self.app.main_window.content, self.privacy.lock_view)
        self.unlock('session-password')
        self.assertIs(self.app.main_window.content, self.original)

    def test_private_view_holds_protection_after_credentials_cleared(self):
        other = ResumePassword('other-password')
        self.app.private_sessions = SimpleNamespace(flush_visible_progress=Mock(), controllers={
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

    def test_failed_interruption_invalidates_pending_wifi_resume(self):
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
            with patch.object(self.privacy, 'prepare_native_protection', side_effect=RuntimeError('native failure')):
                with self.assertRaisesRegex(RuntimeError, 'native failure'):
                    self.privacy.interrupt()
            ready.set_result('Home')
            self.app.loop.run_until_complete(task)
        self.assertTrue(self.gate.locked)
        self.assertTrue(self.privacy.inactive)
        self.assertTrue(self.privacy.interrupted)
        self.assertIs(self.app.main_window.content, self.privacy.lock_view)

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

    def test_network_settings_change_during_lookup_rejects_waiver(self):
        import asyncio
        self.app.preferences.save(session_trusted_wifi='true', trusted_wifi_networks='["Home"]')
        self.privacy.wifi_revision = 10
        ready = self.app.loop.create_future()
        async def read(app):
            return await ready
        with patch('mobile.trusted_wifi.read_ssid', side_effect=read), \
                patch.object(self.privacy, 'finish_reveal') as finish:
            task = self.app.loop.create_task(self.privacy.resume_on_wifi(10))
            self.app.loop.run_until_complete(asyncio.sleep(0))
            self.app.preferences.save(trusted_wifi_networks='["Home", "Other"]')
            ready.set_result('Home')
            self.app.loop.run_until_complete(task)
            finish.assert_called_once_with(None)
