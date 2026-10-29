"""Trusted-network resume never stores secrets or authorizes unrelated gates."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch, AsyncMock

from services.session_auth import ResumePassword
from mobile.trusted_wifi import WifiResume, network_names, trusted, current_ssid
from mobile.preferences import Preferences


class WifiResumeTests(unittest.TestCase):
    def setUp(self):
        self.app = NS(preferences=NS(values={'session_trusted_wifi': 'true',
                      'trusted_wifi_networks': '["Home", "Other home"]'}))
        self.gate = ResumePassword('secret')
        self.resume = WifiResume()

    def background(self, gates=None, credentials=None):
        gates = gates or (self.gate,)
        self.resume.capture(gates, credentials or (self.gate,))
        for gate in gates:
            gate.lock(reason='lifecycle')

    def test_trusted_networks_allow_moving_between_listed_networks(self):
        for name in ('Home', 'Other home'):
            self.background()
            self.resume.resume(self.app, (self.gate,), (self.gate,), name)
            self.assertFalse(self.gate.locked)

    def test_public_unknown_and_disabled_always_challenge(self):
        for ssid in (None, '', '<unknown ssid>', 'Public', 'home'):
            self.gate.locked = False
            self.background()
            self.resume.resume(self.app, (self.gate,), (self.gate,), ssid)
            self.assertTrue(self.gate.locked)
        self.gate.locked = False
        self.background()
        self.app.preferences.values['session_trusted_wifi'] = 'false'
        self.resume.resume(self.app, (self.gate,), (self.gate,), 'Home')
        self.assertTrue(self.gate.locked)

    def test_cannot_unlock_previously_locked_private_or_replaced_gates(self):
        private = ResumePassword('private')
        self.background((self.gate, private))
        self.resume.resume(self.app, (self.gate, private), (self.gate,), 'Home')
        self.assertFalse(self.gate.locked)
        self.assertTrue(private.locked)
        self.gate.lock()
        self.background()
        self.resume.resume(self.app, (self.gate,), (self.gate,), 'Home')
        self.assertTrue(self.gate.locked)
        self.gate.locked = False
        self.background()
        self.gate.lock()  # Explicit revocation during the transition.
        self.resume.resume(self.app, (self.gate,), (self.gate,), 'Home')
        self.assertTrue(self.gate.locked)
        replacement = ResumePassword('new')
        replacement.lock()
        self.resume.resume(self.app, (replacement,), (replacement,), 'Home')
        self.assertTrue(replacement.locked)

    def test_duplicate_notification_does_not_preserve_an_explicit_revocation(self):
        self.background()
        self.gate.lock()  # Manual revocation between lifecycle notifications.
        self.background()
        self.resume.resume(self.app, (self.gate,), (self.gate,), 'Home')
        self.assertTrue(self.gate.locked)

    def test_multiple_windows_share_only_known_lifecycle_locks(self):
        other = WifiResume()
        self.background()
        other.capture((self.gate,), (self.gate,))
        self.gate.lock(reason='lifecycle')
        self.resume.resume(self.app, (self.gate,), (self.gate,), 'Home')
        self.assertFalse(self.gate.locked)
        other.resume(self.app, (self.gate,), (self.gate,), 'Home')
        self.assertFalse(self.gate.locked)

    def test_other_window_cannot_bypass_a_failed_network_check(self):
        other = WifiResume()
        self.background()
        other.capture((self.gate,), (self.gate,))
        self.gate.lock(reason='lifecycle')
        self.resume.resume(self.app, (self.gate,), (self.gate,), 'Public')
        other.resume(self.app, (self.gate,), (self.gate,), 'Home')
        self.assertTrue(self.gate.locked)

    def test_failed_resume_is_consumed_and_clear_revokes_eligibility(self):
        self.background()
        self.resume.resume(self.app, (self.gate,), (self.gate,), 'Public')
        self.resume.resume(self.app, (self.gate,), (self.gate,), 'Home')
        self.assertTrue(self.gate.locked)
        self.gate.locked = False
        self.background()
        self.resume.resume(self.app, (self.gate,), (), 'Home')
        self.assertTrue(self.gate.locked)

    def test_preferences_roundtrip_defaults_and_exact_names(self):
        with TemporaryDirectory() as directory:
            preferences = Preferences(Path(directory))
            self.assertEqual(preferences.values['session_trusted_wifi'], 'false')
            preferences.save(session_trusted_wifi='true', trusted_wifi_networks='[" Home ", "Café"]')
            loaded = Preferences(Path(directory))
            self.assertEqual(loaded.error, '')
            self.assertEqual(network_names(loaded.values['trusted_wifi_networks']), [' Home ', 'Café'])
            self.assertTrue(trusted(NS(preferences=loaded), ' Home '))
            self.assertFalse(trusted(NS(preferences=loaded), 'Home'))
        for value in ('{}', '[""]', '["A", "A"]', '["a\\nb"]', json.dumps(['é' * 17])):
            with self.assertRaises(ValueError):
                network_names(value)

    def test_unavailable_native_backend_cannot_grant_access(self):
        self.assertIsNone(current_ssid(NS(_impl=object())))


class WifiSettingsTests(unittest.TestCase):
    def test_setting_and_network_list_persist_without_passwords(self):
        from mobile.app import LogisticsMobile
        from mobile.settings.categories import SettingsCategories
        from mobile.settings.trusted_wifi import controls, show
        import toga
        with TemporaryDirectory() as directory:
            with patch.object(LogisticsMobile, 'storage_root', Path(directory)):
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            box = SettingsCategories(app).category('Workspaces')
            choice, manage = controls(app, box)
            self.assertFalse(choice.value)
            self.assertIsNone(manage.parent)
            choice.value = True
            self.assertIsNotNone(manage.parent)
            with patch('mobile.settings.trusted_wifi.read_ssid', new=AsyncMock(return_value='Home')), \
                    patch('mobile.settings.trusted_wifi.access_state', return_value='granted'), \
                    patch('mobile.settings.trusted_wifi.request_access', new=AsyncMock(return_value=True)), \
                    patch.object(app, 'show_view') as present:
                show(app)
                import asyncio
                app.loop.run_until_complete(asyncio.sleep(.01))
                content = present.call_args.args[0].content
                def button(label):
                    return next(child for child in content.children if isinstance(child, toga.Button) and child.text == label)
                button('Add current network').on_press()
                app.loop.run_until_complete(asyncio.sleep(.01))
                self.assertEqual(network_names(app.preferences.values['trusted_wifi_networks']), ['Home'])
                row = next(child for child in content.children if isinstance(child, toga.Box) and child.children
                           and isinstance(child.children[0], toga.Box))
                remove = row.children[0].children[1]
                self.assertEqual(remove.text, '−')
                self.assertEqual(remove.style.width, 48)
                remove.on_press()
                self.assertEqual(network_names(app.preferences.values['trusted_wifi_networks']), [])
                entry = next(child for child in content.children if isinstance(child, toga.TextInput))
                entry.value = 'x' * 33
                button('Add network name').on_press()
                self.assertEqual(entry.value, 'x' * 33)
                self.assertEqual(network_names(app.preferences.values['trusted_wifi_networks']), [])
            choice.value = False
            self.assertIsNone(manage.parent)
            # Exercise the actual grouped Settings page, not just its factory.
            app.show_settings(present=False)
            app.preferences.save(session_trusted_wifi='true')
            section = app.settings_navigation.sections['Workspaces']
            def descendants(widget):
                yield widget
                for child in getattr(widget, 'children', ()):
                    yield from descendants(child)
            switch = next(widget for widget in descendants(section) if isinstance(widget, toga.Switch)
                          and widget is not app.show_legacy_choice)
            for enabled in (False, True, False, True, False):
                switch.value = enabled
                buttons = [widget for widget in descendants(section) if isinstance(widget, toga.Button)
                           and widget.text == 'Trusted Wi-Fi networks…']
                self.assertEqual(len(buttons), int(enabled))

    def test_denial_keeps_manual_entry_and_reopening_asks_again(self):
        import asyncio
        import toga
        from mobile.app import LogisticsMobile
        from mobile.settings.trusted_wifi import show
        with TemporaryDirectory() as directory:
            with patch.object(LogisticsMobile, 'storage_root', Path(directory)):
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            decision = app.loop.create_future()
            async def ask(dialog):
                return await decision
            with patch.object(app, 'show_view') as present, \
                    patch.object(app.main_window, 'dialog', new=AsyncMock(side_effect=ask)) as dialog, \
                    patch('mobile.settings.trusted_wifi.access_state', return_value='prompt'), \
                    patch('mobile.settings.trusted_wifi.request_access', new=AsyncMock(return_value=False)) as request, \
                    patch('mobile.settings.trusted_wifi.read_ssid', new=AsyncMock()) as read:
                show(app)
                app.loop.run_until_complete(asyncio.sleep(.01))
                content = present.call_args.args[0].content
                buttons = {child.text: child for child in content.children if isinstance(child, toga.Button)}
                self.assertNotIn('Refresh current network', buttons)
                self.assertNotIn('Allow Wi-Fi identification…', buttons)
                self.assertFalse(buttons['Add current network'].enabled)
                read.assert_not_awaited()
                request.assert_not_awaited()
                # The manual controls work even while the permission decision is pending.
                entry = next(child for child in content.children if isinstance(child, toga.TextInput))
                entry.value = ' Manual home '
                buttons['Add network name'].on_press()
                self.assertEqual(network_names(app.preferences.values['trusted_wifi_networks']), [' Manual home '])
                decision.set_result(False)
                app.loop.run_until_complete(asyncio.sleep(.01))
                self.assertFalse(buttons['Add current network'].enabled)
                request.assert_not_awaited()
                show(app)
                app.loop.run_until_complete(asyncio.sleep(.01))
                self.assertEqual(dialog.await_count, 2)
                # A later visit accepts our explanation but denies the OS prompt.
                decision = app.loop.create_future()
                decision.set_result(True)
                show(app)
                app.loop.run_until_complete(asyncio.sleep(.01))
                request.assert_awaited_once()
                read.assert_not_awaited()
                content = present.call_args.args[0].content
                add_current = next(child for child in content.children
                    if isinstance(child, toga.Button) and child.text == 'Add current network')
                self.assertFalse(add_current.enabled)

    def test_grant_waits_for_os_then_add_reads_fresh_and_revocation_disables(self):
        import asyncio
        import toga
        from mobile.app import LogisticsMobile
        from mobile.settings.trusted_wifi import show
        with TemporaryDirectory() as directory:
            with patch.object(LogisticsMobile, 'storage_root', Path(directory)):
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            decision = app.loop.create_future()
            state = 'prompt'
            async def request(app):
                return await decision
            with patch.object(app, 'show_view') as present, \
                    patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)), \
                    patch('mobile.settings.trusted_wifi.access_state', side_effect=lambda app: state), \
                    patch('mobile.settings.trusted_wifi.request_access', side_effect=request), \
                    patch('mobile.settings.trusted_wifi.read_ssid', new=AsyncMock(side_effect=['Home', 'Cottage'])) as read:
                show(app)
                app.loop.run_until_complete(asyncio.sleep(.01))
                content = present.call_args.args[0].content
                button = next(child for child in content.children
                    if isinstance(child, toga.Button) and child.text == 'Add current network')
                self.assertFalse(button.enabled)
                read.assert_not_awaited()
                state = 'granted'
                decision.set_result(True)
                app.loop.run_until_complete(asyncio.sleep(.01))
                self.assertTrue(button.enabled)
                button.on_press()
                app.loop.run_until_complete(asyncio.sleep(.01))
                self.assertEqual(network_names(app.preferences.values['trusted_wifi_networks']), ['Cottage'])
                state = 'settings'
                button.on_press()
                app.loop.run_until_complete(asyncio.sleep(.01))
                self.assertFalse(button.enabled)
                self.assertEqual(read.await_count, 2)

    def test_permanent_denial_explains_system_settings_each_visit(self):
        import asyncio
        from mobile.app import LogisticsMobile
        from mobile.settings.trusted_wifi import show
        with TemporaryDirectory() as directory:
            with patch.object(LogisticsMobile, 'storage_root', Path(directory)):
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            with patch.object(app, 'show_view'), \
                    patch.object(app.main_window, 'dialog', new=AsyncMock()) as dialog, \
                    patch('mobile.settings.trusted_wifi.access_state', return_value='settings'), \
                    patch('mobile.settings.trusted_wifi.request_access', new=AsyncMock()) as request, \
                    patch('mobile.settings.trusted_wifi.read_ssid', new=AsyncMock()) as read:
                for _ in range(2):
                    show(app)
                    app.loop.run_until_complete(asyncio.sleep(.01))
                self.assertEqual(dialog.await_count, 2)
                import toga
                self.assertIsInstance(dialog.call_args.args[0], toga.InfoDialog)
                request.assert_not_awaited()
                read.assert_not_awaited()


class NativeWifiTests(unittest.TestCase):
    def test_ios_permission_states_include_denial_and_reduced_accuracy(self):
        import sys
        from mobile.trusted_wifi import access_state
        impl = type('Impl', (), {'__module__': 'toga_iOS.app'})()
        manager = NS(authorizationStatus=0, accuracyAuthorization=0)
        app = NS(_impl=impl, _wifi_location_manager=manager)
        with patch.dict(sys.modules, {'rubicon.objc': NS(ObjCClass=Mock())}), patch('ctypes.CDLL'):
            for status, accuracy, expected in ((0, 0, 'prompt'), (1, 0, 'settings'),
                    (2, 0, 'settings'), (3, 0, 'granted'), (4, 0, 'granted'), (4, 1, 'settings')):
                manager.authorizationStatus, manager.accuracyAuthorization = status, accuracy
                self.assertEqual(access_state(app), expected)

    def test_android_request_awaits_decision_and_detects_permanent_denial(self):
        import asyncio
        from mobile.trusted_wifi import access_state, request_access
        impl = type('Impl', (), {'__module__': 'toga_android.app'})()
        impl.native = Mock()
        impl.native.checkSelfPermission.return_value = -1
        impl.native.shouldShowRequestPermissionRationale.return_value = False
        impl.request_permissions = Mock(side_effect=lambda permissions, on_complete:
            on_complete(permissions, [-1, -1]))
        app = NS(_impl=impl, location=NS(request_permission=AsyncMock(return_value=False)))
        self.assertEqual(access_state(app), 'prompt')
        self.assertFalse(asyncio.run(request_access(app)))
        impl.request_permissions.assert_called_once()
        app.location.request_permission.assert_not_awaited()
        self.assertEqual(access_state(app), 'settings')
        self.assertFalse(asyncio.run(request_access(app)))
        impl.request_permissions.assert_called_once()
        impl.native.shouldShowRequestPermissionRationale.return_value = True
        self.assertEqual(access_state(app), 'prompt')
        impl.native.checkSelfPermission.return_value = 0
        self.assertEqual(access_state(app), 'granted')
        self.assertTrue(asyncio.run(request_access(app)))

    def test_android_approximate_grant_can_be_upgraded_to_precise(self):
        import asyncio
        from mobile.trusted_wifi import request_access
        impl = type('Impl', (), {'__module__': 'toga_android.app'})()
        impl.native = Mock()
        impl.native.checkSelfPermission.return_value = -1
        impl.native.shouldShowRequestPermissionRationale.return_value = True
        app = NS(_impl=impl, location=NS(request_permission=AsyncMock(return_value=True)))
        def complete(permissions, on_complete):
            impl.native.checkSelfPermission.return_value = 0
            on_complete(permissions, [0, 0])
        impl.request_permissions = Mock(side_effect=complete)
        self.assertTrue(asyncio.run(request_access(app)))
        impl.request_permissions.assert_called_once()
        app.location.request_permission.assert_not_awaited()

    def test_android_permissions_unknown_ssid_and_cellular_fail_closed(self):
        import sys
        native = Mock()
        impl = type('Impl', (), {'__module__': 'toga_android.app'})()
        impl.native = native
        app = NS(_impl=impl)
        info = native.getApplicationContext.return_value.getSystemService.return_value.getConnectionInfo.return_value
        native.checkSelfPermission.return_value = 0
        info.getNetworkId.return_value = 1
        info.getSSID.return_value = '"Home"'
        capabilities = native.getSystemService.return_value.getNetworkCapabilities.return_value
        capabilities.hasTransport.return_value = True
        with patch.dict(sys.modules, {'java': NS(jclass=Mock())}):
            self.assertEqual(current_ssid(app), 'Home')
            info.getSSID.return_value = '<unknown ssid>'
            self.assertIsNone(current_ssid(app))
            info.getSSID.return_value = '"Home"'
            capabilities.hasTransport.return_value = False
            self.assertIsNone(current_ssid(app))
            capabilities.hasTransport.return_value = True
            native.checkSelfPermission.return_value = -1
            self.assertIsNone(current_ssid(app))

    def test_ios_async_result_and_missing_entitlement_fail_closed(self):
        import asyncio
        import sys
        from mobile.trusted_wifi import read_ssid, _ios_callbacks
        impl = type('Impl', (), {'__module__': 'toga_iOS.app'})()
        app = NS(_impl=impl)
        network = NS(SSID='Home')
        fetch = Mock(side_effect=lambda callback: callback(network))
        fake = NS(ObjCClass=lambda name: NS(fetchCurrentWithCompletionHandler=fetch),
                  ObjCInstance=lambda pointer: pointer, Block=lambda function, *args: function,
                  objc_id=object())
        with patch.dict(sys.modules, {'rubicon.objc': fake}), patch('ctypes.CDLL'):
            self.assertEqual(asyncio.run(read_ssid(app)), 'Home')
            self.assertEqual(_ios_callbacks, set())
            fetch.side_effect = lambda callback: callback(None)
            self.assertIsNone(asyncio.run(read_ssid(app)))
            network.SSID = None
            fetch.side_effect = lambda callback: callback(network)
            self.assertIsNone(asyncio.run(read_ssid(app)))
            fetch.side_effect = RuntimeError('unavailable entitlement')
            self.assertIsNone(asyncio.run(read_ssid(app)))
            self.assertEqual(_ios_callbacks, set())
