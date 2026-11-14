"""External output must never outlive the visible comic or a privacy change."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace as NS
import sys
import unittest
from unittest.mock import Mock, patch

from mobile.external_display import ExternalComicDisplay, comic_canvas, sync
from features.rclone.mobile.cloud import CloudClient


class Host:
    pass


def page(image):
    return NS(_external_comic_page=True, image=object(), children=[],
              _impl=NS(picture=NS(image=image), native=NS(getDrawable=lambda: image)))


class ExternalDisplayTests(unittest.TestCase):
    def setUp(self):
        self.observers = patch.object(CloudClient.credential_state, 'observers', set())
        self.observers.start()
        self.addCleanup(self.observers.stop)
        self.host = Host()
        self.host.active_host = True
        self.host._impl = NS()
        self.privacy = NS(inactive=False, saved_content=None, shield=None,
                          gates=lambda: (), disposed=False)
        self.host.screen_privacy = self.privacy
        from mobile.protection import for_app
        scope = for_app(self.host)
        scope.register(self, lambda: self.privacy.gates())
        self.addCleanup(scope.dispose)
        self.canvas = page('page one')
        self.host.body = NS(children=[NS(children=[self.canvas])])
        self.output = ExternalComicDisplay(NS())
        self.host.scene_manager = NS(external_comics=self.output)
        self.picture = NS(image=None)
        self.scene = NS(session=NS(persistentIdentifier='tv'), coordinateSpace=NS(bounds=object()))
        self.window = Mock()
        self.window.windowScene = None
        self.window.hidden = True
        self.window.setHidden.side_effect = lambda hidden: setattr(self.window, 'hidden', hidden)
        self.output.ios['tv'] = self.scene, self.window, self.picture

    def test_page_publication_navigation_and_suspension_clear_old_pixels(self):
        sync(self.host, select=True)
        self.assertEqual(self.picture.image, 'page one')
        self.assertIs(self.window.windowScene, self.scene)
        self.canvas._impl.picture.image = 'page two'
        sync(self.host)
        self.assertEqual(self.picture.image, 'page two')
        self.canvas.image = None
        sync(self.host)
        self.assertIsNone(self.picture.image)
        self.assertIs(self.window.windowScene, self.scene)
        self.canvas.image = object()
        sync(self.host)
        self.assertEqual(self.picture.image, 'page two')
        self.host.body = NS(children=[])
        sync(self.host, select=True)
        self.assertIsNone(self.picture.image)
        self.assertIsNone(self.window.windowScene)
        self.assertTrue(self.window.hidden)

    def test_ios_mirrors_outside_reader_only_while_unprotected(self):
        self.host.body = NS(children=[])
        sync(self.host, select=True)
        self.assertIsNone(self.window.windowScene)
        self.window.setHidden.assert_not_called()

        self.privacy.gates = lambda: (NS(locked=False),)
        sync(self.host)
        self.assertIs(self.window.windowScene, self.scene)
        self.assertIsNone(self.picture.image)
        self.assertFalse(self.window.hidden)

        self.privacy.gates = lambda: ()
        sync(self.host)
        self.assertIsNone(self.window.windowScene)
        self.assertTrue(self.window.hidden)

        self.host.body = NS(children=[self.canvas])
        sync(self.host)
        self.assertIs(self.window.windowScene, self.scene)
        self.assertEqual(self.picture.image, 'page one')
        self.assertFalse(self.window.hidden)

    def test_session_gate_blanks_even_local_comic_and_unlocked_gate(self):
        sync(self.host, select=True)
        gate = NS(locked=False)
        self.privacy.gates = lambda: (gate,)
        sync(self.host)
        self.assertIsNone(self.picture.image)
        self.privacy.gates = lambda: ()
        sync(self.host)
        self.assertEqual(self.picture.image, 'page one')

    def test_another_window_gate_blanks_selected_window(self):
        sync(self.host, select=True)
        observer = Mock(disposed=False)
        observer.gates.return_value = (NS(locked=False),)
        from mobile.protection import for_app
        scope = for_app(self.host).process.window()
        scope.register(observer, lambda: observer.gates())
        self.addCleanup(scope.dispose)
        self.output.refresh()
        self.assertIsNone(self.picture.image)
        observer.gates.return_value = ()
        self.output.refresh()
        self.assertEqual(self.picture.image, 'page one')

    def test_inactivity_lock_shield_and_shutdown_clear_output(self):
        for field, value in [('inactive', True), ('shield', object())]:
            with self.subTest(field=field):
                old = getattr(self.privacy, field)
                sync(self.host, select=True)
                setattr(self.privacy, field, value)
                sync(self.host)
                self.assertIsNone(self.picture.image)
                setattr(self.privacy, field, old)
        self.host.active_host = False
        sync(self.host)
        self.assertIsNone(self.picture.image)

    def test_photos_are_not_comics_and_android_gets_same_current_image(self):
        photo = NS(children=[], image=object())
        self.assertIsNone(comic_canvas(photo))
        android = self.output.android = Mock()
        sync(self.host, select=True)
        android.setImage.assert_called_with('page one')
        self.privacy.gates = lambda: (NS(locked=False),)
        sync(self.host)
        android.setImage.assert_called_with(None)
        self.output.dispose()
        android.dispose.assert_called_once()
        self.assertTrue(self.window.hidden)
        self.window.setHidden.assert_called_with(True)
        self.assertIsNone(self.picture.image)
        self.assertFalse(self.output.ios)
        self.assertIsNone(self.output.source)

    def test_pdf_uses_same_output_and_privacy_gate_as_comics(self):
        del self.canvas._external_comic_page
        self.canvas._external_document_page = True
        sync(self.host, select=True)
        self.assertEqual(self.picture.image, 'page one')
        self.privacy.gates = lambda: (NS(locked=False),)
        sync(self.host)
        self.assertIsNone(self.picture.image)

    def test_disconnect_clears_and_forgets_external_image(self):
        sync(self.host, select=True)
        self.output.disconnect_ios(self.scene)
        self.assertIsNone(self.picture.image)
        self.assertTrue(self.window.hidden)
        self.window.setHidden.assert_called_with(True)
        self.assertEqual(self.output.ios, {})

    def test_video_claims_scene_in_either_connection_order_and_restores_document(self):
        for connect_first in (False, True):
            with self.subTest(connect_first=connect_first):
                self.output.ios.clear()
                self.host.video_player = None
                sync(self.host, select=True)
                if connect_first:
                    self.output.ios['tv'] = self.scene, self.window, self.picture
                    self.output.refresh()
                    self.assertEqual(self.picture.image, 'page one')
                native = Mock()
                self.host.video_player = NS(closed=False, hidden=False, native=native, allowed=Mock(return_value=True))
                self.output.refresh()
                if not connect_first:
                    native.set_external_display.assert_not_called()
                    self.output.ios['tv'] = self.scene, self.window, self.picture
                    self.output.refresh()
                native.set_external_display.assert_called_with(self.picture)
                self.assertIsNone(self.picture.image)
                self.output.disconnect_ios(self.scene)
                native.disconnect_external_display.assert_called_once()
                self.output.ios['tv'] = self.scene, self.window, self.picture
                self.output.refresh()
                self.host.video_player.closed = True
                self.output.refresh()
                native.set_external_display.assert_called_with(None)
                self.assertEqual(self.picture.image, 'page one')

    def test_native_airplay_yields_the_legacy_window_and_restores_document_output(self):
        sync(self.host, select=True)
        self.assertIs(self.window.windowScene, self.scene)
        native = Mock(system_airplay=True)
        self.host.video_player = NS(closed=False, hidden=False, native=native, allowed=Mock(return_value=True))
        self.output.refresh()
        native.set_external_display.assert_not_called()
        self.assertIsNone(self.window.windowScene)
        self.assertIsNone(self.picture.image)
        self.host.video_player.closed = True
        self.output.refresh()
        self.assertIs(self.window.windowScene, self.scene)
        self.assertEqual(self.picture.image, 'page one')

    def test_video_denies_protected_entry_and_revokes_on_process_protection(self):
        from mobile.protection import for_app
        process = for_app(self.host).process
        protected = process.window()
        self.addCleanup(protected.dispose)
        release = protected.register(self, lambda: (), protected=lambda: True)
        native = Mock()
        self.host.video_player = NS(closed=False, hidden=False, native=native, allowed=Mock(return_value=True))
        sync(self.host, select=True)
        native.set_external_display.assert_not_called()
        self.assertIsNone(self.picture.image)
        self.assertIs(self.window.windowScene, self.scene)
        release()
        self.output.refresh()
        native.set_external_display.assert_called_once_with(self.picture)
        protected.register(self, lambda: (NS(locked=False),))
        self.output.refresh()
        native.revoke_external_display.assert_called_once()
        self.assertIsNone(self.output.ios_video)
        self.assertIsNone(self.picture.image)

    def test_sharing_layout_wakes_only_on_connection_or_permission_changes(self):
        with patch('mobile.layout_events.notify_layout') as wake:
            sync(self.host, select=True)
            self.assertTrue(self.output.sharing(self.host))
            wake.assert_called_once_with(self.host)
            self.output.refresh()
            self.assertEqual(wake.call_count, 1)
            self.privacy.inactive = True
            self.output.refresh()
            self.assertFalse(self.output.sharing(self.host))
            self.assertEqual(wake.call_count, 2)
            self.privacy.inactive = False
            self.output.refresh()
            self.assertTrue(self.output.sharing(self.host))
            self.assertEqual(wake.call_count, 3)
            self.output.disconnect_ios(self.scene)
            self.assertFalse(self.output.sharing(self.host))
            self.assertEqual(wake.call_count, 4)

    def test_android_layout_override_requires_a_showing_presentation(self):
        self.output.ios.clear()
        self.output.android = Mock()
        self.output.android.isShowing.return_value = False
        sync(self.host, select=True)
        self.assertFalse(self.output.sharing(self.host))
        self.output.android.isShowing.return_value = True
        self.output.refresh()
        self.assertTrue(self.output.sharing(self.host))
        other = Host()
        self.assertFalse(self.output.sharing(other))

    def test_ios_connection_dispatches_native_visibility_selector(self):
        output = ExternalComicDisplay(NS())
        window, controller, picture = Mock(), Mock(), Mock()
        classes = {name: Mock() for name in ('UIWindow', 'UIViewController', 'UIImageView', 'UIColor')}
        classes['UIWindow'].alloc.return_value.initWithFrame.return_value = window
        classes['UIViewController'].alloc.return_value.init.return_value = controller
        classes['UIImageView'].alloc.return_value.init.return_value = picture
        scene = NS(session=NS(persistentIdentifier='tv'), coordinateSpace=NS(bounds=object()))
        with patch.dict(sys.modules, {'rubicon.objc': NS(ObjCClass=classes.__getitem__)}):
            self.assertIs(output.connect_ios(scene), window)
        window.setHidden.assert_called_once_with(False)
        self.assertIs(window.rootViewController, controller)
        self.assertIs(controller.view, picture)
        output.disconnect_ios(scene)
        window.setHidden.assert_called_with(True)

    def test_casting_badge_survives_fullscreen_and_clears_with_output(self):
        self.host._impl = type('Backend', (), {'__module__': 'toga_iOS.app'})()
        self.host._comic_chrome_hidden = self.host._reader_chrome_hidden = True
        phone = Mock()
        self.host.main_window = NS(_impl=NS(native=phone))
        classes = {name: Mock() for name in ('UILabel', 'UIFont', 'UIColor')}
        classes['UILabel'].alloc.return_value.init.side_effect = Mock
        with patch.dict(sys.modules, {'rubicon.objc': NS(ObjCClass=classes.__getitem__)}), \
                patch.object(self.output, 'register_ios'):
            sync(self.host, select=True)
            first = self.output.ios_status[1]
            first.setText.assert_called_once_with('Casting to TV')
            first.setUserInteractionEnabled.assert_called_once_with(False)
            phone.addSubview.assert_called_once_with(first)
            self.output.refresh()
            self.assertIs(self.output.ios_status[1], first)
            self.privacy.gates = lambda: (NS(locked=False),)
            self.output.refresh()
            first.removeFromSuperview.assert_called_once()
            self.assertIsNone(self.output.ios_status)
            self.privacy.gates = lambda: ()
            self.output.refresh()
            second = self.output.ios_status[1]
            self.output.disconnect_ios(self.scene)
            second.removeFromSuperview.assert_called_once()
            self.assertIsNone(self.output.ios_status)

    def test_android_reconnect_rechecks_current_privacy_instead_of_cached_pixels(self):
        android = Mock()
        factory = Mock(return_value=android)
        def jclass(name):
            return object if name == 'java.lang.Runnable' else factory
        with patch.dict(sys.modules, {'java': NS(jclass=jclass, dynamic_proxy=lambda cls: object)}):
            self.host._impl.native = object()
            self.output.install_android(self.host)
        callback = factory.call_args.args[1]
        self.output.select(self.host)
        android.setImage.assert_called_with('page one')
        self.privacy.gates = lambda: (NS(locked=False),)
        callback.run()
        android.setImage.assert_called_with(None)
        self.privacy.gates = lambda: ()
        self.canvas._impl.native.getDrawable = lambda: 'new page'
        callback.run()
        android.setImage.assert_called_with('new page')


if __name__ == '__main__':
    unittest.main()
