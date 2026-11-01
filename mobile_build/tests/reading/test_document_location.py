"""Storage subtitles replace body rows without returning after fullscreen."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
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
        controller = NS(view=NS(bounds=NS(size=NS(width=466))), navigationItem=NS(titleView=None))
        with patch('mobile.document_location.storage_identity', return_value=('On-device', False, False)):
            install_document_location(view)
        row = view._document_location_row
        self.assertEqual(frame.top_controls, 2)
        with patch('mobile.folder_title.storage_title', return_value=object()) as make, \
                patch('mobile.ios_toolbar.vertical_edge', return_value=2) as edge, \
                patch('mobile.document_location.empty_bar_title', return_value=object()), \
                patch('mobile.document_location.place_title_in_header'):
            mount_apple_title(view, controller, 'Comic.cbz')
            self.assertIsNone(row.parent)
            header = view._document_title_header
            self.assertIs(view.children[0], header)
            self.assertLess(view.children.index(header), view.children.index(frame.content))
            self.assertIs(controller.navigationItem.titleView, header._empty_bar_title)
            frame.set_immersive(True, comic=True)
            self.assertIsNone(header.parent)
            frame.set_immersive(False, comic=True)
            self.assertIsNone(row.parent)
            mount_apple_title(view, controller, 'Comic.cbz')
            self.assertEqual(make.call_count, 1)
            view._document_storage_status = 'Cloud · Unlocked'
            mount_apple_title(view, controller, 'Comic.cbz')
            self.assertEqual(make.call_count, 2)
            self.assertEqual(make.call_args.args[1], 'Cloud · Unlocked')
            edge.return_value = 0
            mount_apple_title(view, controller, 'Comic.cbz')
            self.assertIsNone(header.parent)
            self.assertNotIn(header, frame.controls)
            self.assertIs(controller.navigationItem.titleView, view._document_title_view)

    def test_routes_without_storage_clear_previous_subtitle(self):
        controller = NS(navigationItem=NS(titleView=object()))
        mount_apple_title(toga.Box(), controller, 'Settings')
        self.assertIsNone(controller.navigationItem.titleView)
