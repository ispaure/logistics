"""Reader chrome distinguishes immersive text from edge-to-edge comic images."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
import toga
from mobile.reader_controls import ReadingFrame
from mobile.reader_chrome import sync_comic_chrome


class ReaderFullscreenTests(unittest.TestCase):
    def test_text_fullscreen_keeps_margins_and_restores_controls(self):
        content, header, footer = toga.Box(), toga.Box(), toga.Box()
        frame = ReadingFrame(content, [header, footer])
        app = NS(_impl=NS(), adaptive=NS(secondary=None, split=None, detail_routes=[]),
                 routes=NS(screens={'documents': []}),
                 native_host=NS(adapter=None, chrome=Mock(), state=NS(destination='documents')))
        for comic in (False, True):
            frame.set_immersive(True, comic=comic)
            sync_comic_chrome(app, frame.widget)
            self.assertTrue(app._reader_chrome_hidden)
            self.assertEqual(app._comic_chrome_hidden, comic)
            self.assertEqual(frame.widget.style.margin_top, 0 if comic else 16)
            self.assertNotIn(header, frame.widget.children)
            frame.set_immersive(False, comic=comic)
            sync_comic_chrome(app, frame.widget)
            self.assertFalse(app._reader_chrome_hidden)
            self.assertFalse(app._comic_chrome_hidden)
            self.assertEqual(list(frame.widget.children), [header, content, footer])
            app.native_host.chrome.set_hidden.assert_called_with(False, navigation=None)

    def test_status_policy_is_window_local_and_distinguishes_images(self):
        from mobile import ios_reader_chrome as chrome
        app = NS(_reader_chrome_hidden=True, _comic_chrome_hidden=False)
        with patch.object(chrome, '_hosts', {7: app}):
            self.assertTrue(chrome.fullscreen(NS(ptr=NS(value=7))))
            self.assertFalse(chrome.fullscreen(NS(ptr=NS(value=7)), images=True))
            self.assertFalse(chrome.fullscreen(NS(ptr=NS(value=8))))
            self.assertFalse(chrome.fullscreen(None))

    def test_provider_epub_can_restore_controls_without_changing_location(self):
        from mobile.provider_ui import ProviderUI
        restore = toga.Button('Show reading controls')
        frame = ReadingFrame(toga.Box(), [toga.Box(), toga.Box()], restore=restore)
        reader = NS(kind='.epub', book=object(), editable=False)
        owner = NS(crypt_reader=reader, crypt_immersive=False, reading_frame=frame,
                   crypt_view=frame.widget, reader_restore=restore,
                   refresh_transfer_status=Mock(), resume_crypt=Mock(), epub_offset=1234)
        ProviderUI.toggle_private_reading_mode(owner)
        self.assertTrue(frame.widget._reader_fullscreen)
        self.assertFalse(frame.widget._comic_fullscreen)
        self.assertIn(owner.reader_restore, frame.widget.children)
        self.assertEqual(frame.widget.style.margin_top, 16)
        ProviderUI.toggle_private_reading_mode(owner)
        self.assertFalse(frame.widget._reader_fullscreen)
        self.assertNotIn(owner.reader_restore, frame.widget.children)
        self.assertEqual(owner.epub_offset, 1234)
