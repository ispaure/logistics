"""External output must never outlive the visible comic or a privacy change."""
from types import SimpleNamespace as NS
import sys
import unittest
from unittest.mock import Mock, patch

from logisticsmobile.external_display import ExternalComicDisplay, comic_canvas, sync
from features.rclone.mobile.cloud import CloudClient


class Host:
    pass


def page(image):
    return NS(_external_comic_page=True, image=object(), children=[],
              _impl=NS(picture=NS(image=image), native=NS(getDrawable=lambda: image)))


class ExternalDisplayTests(unittest.TestCase):
    def setUp(self):
        self.observers = patch.object(CloudClient, '_credential_observers', set())
        self.observers.start()
        self.addCleanup(self.observers.stop)
        self.host = Host()
        self.host.active_host = True
        self.host._impl = NS()
        self.privacy = NS(inactive=False, saved_content=None, shield=None,
                          gates=lambda: (), disposed=False)
        self.host.screen_privacy = self.privacy
        self.canvas = page('page one')
        self.host.body = NS(children=[NS(children=[self.canvas])])
        self.output = ExternalComicDisplay(NS())
        self.host.scene_manager = NS(external_comics=self.output)
        self.picture = NS(image=None)
        self.window = Mock()
        self.window.hidden = False
        self.window.setHidden.side_effect = lambda hidden: setattr(self.window, 'hidden', hidden)
        self.output.ios['tv'] = self.window, self.picture

    def test_page_publication_navigation_and_suspension_clear_old_pixels(self):
        sync(self.host, select=True)
        self.assertEqual(self.picture.image, 'page one')
        self.canvas._impl.picture.image = 'page two'
        sync(self.host)
        self.assertEqual(self.picture.image, 'page two')
        self.canvas.image = None
        sync(self.host)
        self.assertIsNone(self.picture.image)
        self.canvas.image = object()
        sync(self.host)
        self.assertEqual(self.picture.image, 'page two')
        self.host.body = NS(children=[])
        sync(self.host, select=True)
        self.assertIsNone(self.picture.image)

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
        CloudClient._credential_observers.add(observer)
        self.output.refresh()
        self.assertIsNone(self.picture.image)
        observer.gates.return_value = ()
        self.output.refresh()
        self.assertEqual(self.picture.image, 'page one')

    def test_inactivity_lock_shield_and_shutdown_clear_output(self):
        for field, value in [('inactive', True), ('saved_content', object()), ('shield', object())]:
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
        self.privacy.gates = lambda: (object(),)
        sync(self.host)
        android.setImage.assert_called_with(None)
        self.output.dispose()
        android.dispose.assert_called_once()
        self.assertTrue(self.window.hidden)
        self.window.setHidden.assert_called_with(True)
        self.assertIsNone(self.picture.image)
        self.assertFalse(self.output.ios)
        self.assertIsNone(self.output.source)

    def test_disconnect_clears_and_forgets_external_image(self):
        sync(self.host, select=True)
        scene = NS(session=NS(persistentIdentifier='tv'))
        self.output.disconnect_ios(scene)
        self.assertIsNone(self.picture.image)
        self.assertTrue(self.window.hidden)
        self.window.setHidden.assert_called_with(True)
        self.assertEqual(self.output.ios, {})

    def test_ios_connection_dispatches_native_visibility_selector(self):
        output = ExternalComicDisplay(NS())
        window, controller, picture = Mock(), Mock(), Mock()
        classes = {name: Mock() for name in ('UIWindow', 'UIViewController', 'UIImageView', 'UIColor')}
        classes['UIWindow'].alloc.return_value.initWithWindowScene.return_value = window
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
            self.privacy.gates = lambda: (object(),)
            self.output.refresh()
            first.removeFromSuperview.assert_called_once()
            self.assertIsNone(self.output.ios_status)
            self.privacy.gates = lambda: ()
            self.output.refresh()
            second = self.output.ios_status[1]
            self.output.disconnect_ios(NS(session=NS(persistentIdentifier='tv')))
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
        self.privacy.gates = lambda: (object(),)
        callback.run()
        android.setImage.assert_called_with(None)
        self.privacy.gates = lambda: ()
        self.canvas._impl.native.getDrawable = lambda: 'new page'
        callback.run()
        android.setImage.assert_called_with('new page')


if __name__ == '__main__':
    unittest.main()
