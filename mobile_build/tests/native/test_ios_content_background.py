"""Artwork never moves readable content or retains private pixels after conceal."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from mobile.ios_content_background import Rect, extension_rect, clear, sync, expand_preview


class ContentBackgroundTests(unittest.TestCase):
    def test_right_and_left_bars_extend_only_the_adjacent_pane(self):
        root = Rect(0, 0, 1000, 700)
        canvas = Rect(350, 80, 550, 550)
        self.assertEqual(extension_rect(canvas, root, edge=2, safe_left=0, safe_right=100),
                         Rect(350, 80, 650, 550))
        self.assertIsNone(extension_rect(Rect(0, 80, 320, 550), root, edge=2, safe_left=0, safe_right=100))
        self.assertEqual(extension_rect(Rect(100, 80, 550, 550), root, edge=1, safe_left=100, safe_right=0),
                         Rect(0, 80, 650, 550))
        self.assertIsNone(extension_rect(canvas, root, edge=0, safe_left=0, safe_right=0))
        self.assertIsNone(extension_rect(Rect(350, 80, 550, 800), root, edge=2, safe_left=0, safe_right=100))

    def test_clear_releases_pixels_before_detaching_and_is_idempotent(self):
        calls = []
        class Picture:
            @property
            def image(self):
                return None
            @image.setter
            def image(self, value):
                calls.append(('image', value))
        state = NS(picture=Picture(), native=NS(removeFromSuperview=lambda: calls.append('removed')))
        app = NS(_ios_artwork_extension=state)
        clear(app)
        clear(app)
        self.assertEqual(calls, [('image', None), 'removed'])
        self.assertIsNone(app._ios_artwork_extension)

    def test_privacy_fullscreen_and_reduce_transparency_remove_artwork(self):
        backend = type('Backend', (), {'__module__': 'toga_iOS.app'})
        app = NS(_impl=backend(), native_host=NS(adapter=NS(navigation=[])),
                 screen_privacy=NS(inactive=False), _reader_chrome_hidden=False)
        for field in ('inactive', 'saved_content', 'shield', 'fullscreen', 'reduce-transparency'):
            with self.subTest(field=field):
                app.screen_privacy = NS(inactive=field == 'inactive',
                    saved_content=object() if field == 'saved_content' else None,
                    shield=object() if field == 'shield' else None)
                app._reader_chrome_hidden = field == 'fullscreen'
                picture = NS(image=object())
                native = Mock()
                app._ios_artwork_extension = NS(picture=picture, native=native)
                with patch('mobile.ios_content_background.reduce_transparency', return_value=field == 'reduce-transparency'):
                    sync(app)
                self.assertIsNone(picture.image)
                native.removeFromSuperview.assert_called_once()

    def test_photo_expands_only_bar_edge_and_restores_conservative_policy(self):
        container = NS(left_inset=18, right_inset=84, top_inset=50, bottom_inset=20)
        view = NS(_image_preview_surface=True, _impl=NS(container=container))
        app = NS(routes=object(), body=NS(children=[view]), native_host=NS(
            destinations=['files'], state=NS(destination='files'),
            adapter=NS(navigation=[NS(topViewController=object())], content_controller=lambda destination: object())))
        container.content = NS(interface=NS(app=app))
        with patch('mobile.ios_content_background.reduce_transparency', return_value=False), \
             patch('mobile.ios_toolbar.vertical_edge', return_value=2):
            self.assertTrue(expand_preview(container))
            self.assertEqual((container.left_inset, container.right_inset,
                              container.top_inset, container.bottom_inset), (18, 0, 50, 20))
            self.assertFalse(expand_preview(container))
            for reason in ('document', 'fold', 'privacy', 'other-container'):
                container.right_inset = 84  # UIKit restores native insets each layout.
                view._image_preview_surface = reason != 'document'
                app._hinge_status = 2 if reason == 'fold' else 0
                app.screen_privacy = NS(inactive=reason == 'privacy')
                view._impl.container = object() if reason == 'other-container' else container
                self.assertFalse(expand_preview(container), reason)
                self.assertEqual(container.right_inset, 84)
            view._impl.container = container
            app.screen_privacy.inactive = False
            with patch('mobile.ios_content_background.reduce_transparency', return_value=True):
                self.assertFalse(expand_preview(container))
        with patch('mobile.ios_content_background.reduce_transparency', return_value=False), \
             patch('mobile.ios_toolbar.vertical_edge', return_value=1):
            self.assertTrue(expand_preview(container))
            self.assertEqual((container.left_inset, container.right_inset), (0, 84))

    def test_accessibility_change_forces_layout_without_a_geometry_change(self):
        from mobile.screen_privacy import ScreenPrivacy
        container = object()
        adapter = NS(layout_content=Mock())
        app = NS(body=NS(children=[NS(_impl=NS(container=container))]),
                 native_host=NS(adapter=adapter), resize_workspace=Mock())
        privacy = object.__new__(ScreenPrivacy)
        privacy.app = app
        with patch('mobile.ios_content_background.sync') as refresh:
            privacy.artwork_accessibility_changed()
        adapter.layout_content.assert_called_once_with(container)
        refresh.assert_called_once_with(app)
        app.resize_workspace.assert_called_once_with()

    def test_background_remeasurement_is_coalesced_after_the_render_pass(self):
        callbacks = []
        backend = type('Backend', (), {'__module__': 'toga_iOS.app'})
        app = NS(_impl=backend(), loop=NS(call_soon=callbacks.append),
                 native_host=NS(adapter=None))
        sync(app)
        sync(app)
        self.assertEqual(len(callbacks), 1)
        with patch('mobile.ios_content_background.sync') as refresh:
            callbacks[0]()
        refresh.assert_called_once_with(app, settled=True)
        self.assertFalse(app._artwork_sync_pending)
