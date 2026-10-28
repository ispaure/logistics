"""Storage subtitles replace body rows without returning after fullscreen."""
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import toga
from mobile.document_location import install_document_location, mount_apple_title
from mobile.reader_controls import ReadingFrame


class DocumentLocationTests(unittest.TestCase):
    def test_native_subtitle_refresh_and_fullscreen_restore(self):
        frame = ReadingFrame(toga.Box(), [toga.Box(), toga.Box()], margin=0)
        view = frame.widget
        controller = NS(view=NS(bounds=NS(size=NS(width=466))), navigationItem=NS())
        with patch('mobile.document_location.storage_identity', return_value=('On-device', False, False)):
            install_document_location(view)
        row = view._document_location_row
        self.assertEqual(frame.top_controls, 2)
        with patch('mobile.folder_title.storage_title', return_value=object()) as make, \
                patch('mobile.ios_toolbar.vertical_edge', return_value=2):
            mount_apple_title(view, controller, 'Comic.cbz')
            self.assertIsNone(row.parent)
            self.assertEqual(frame.top_controls, 1)
            frame.set_immersive(True, comic=True)
            frame.set_immersive(False, comic=True)
            self.assertIsNone(row.parent)
            mount_apple_title(view, controller, 'Comic.cbz')
            self.assertEqual(make.call_count, 1)
            view._document_storage_status = 'Cloud · Unlocked'
            mount_apple_title(view, controller, 'Comic.cbz')
            self.assertEqual(make.call_count, 2)
            self.assertEqual(make.call_args.args[1], 'Cloud · Unlocked')

    def test_routes_without_storage_clear_previous_subtitle(self):
        controller = NS(navigationItem=NS(titleView=object()))
        mount_apple_title(toga.Box(), controller, 'Settings')
        self.assertIsNone(controller.navigationItem.titleView)
