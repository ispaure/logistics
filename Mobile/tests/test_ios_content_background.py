"""Artwork never moves readable content or retains private pixels after conceal."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from logisticsmobile.ios_content_background import Rect, extension_rect, clear, sync


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
                with patch('logisticsmobile.ios_content_background.reduce_transparency', return_value=field == 'reduce-transparency'):
                    sync(app)
                self.assertIsNone(picture.image)
                native.removeFromSuperview.assert_called_once()
