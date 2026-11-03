"""Storage subtitles replace body rows without returning after fullscreen."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
import toga
from mobile.document_location import install_document_location, mount_apple_title
from mobile.reader_controls import ReadingFrame


class DocumentLocationTests(unittest.TestCase):
    def test_android_hold_resolves_current_path_each_time(self):
        from mobile.document_location import bind_android_hold
        view = Mock()
        label = Mock()
        modules = {'android.view': NS(View=NS(OnLongClickListener=object)),
                   'java': NS(dynamic_proxy=lambda interface: interface)}
        with patch.dict('sys.modules', modules), patch('toga.InfoDialog') as dialog:
            bind_android_hold(view, label)
            listener = label.setOnLongClickListener.call_args.args[0]
            for path in ('Vault/First note.md', 'Vault/Nested/Second note.md'):
                view._document_path.return_value = path
                self.assertTrue(listener.onLongClick(label))
                dialog.assert_called_with('Document location', path)
                view.window.dialog.assert_called_with(dialog.return_value)
            view._document_path.return_value = None
            listener.onLongClick(label)
            self.assertEqual(dialog.call_count, 2)

    def test_apple_hold_shows_location_once_in_the_reader_window(self):
        from mobile.document_location import bind_apple_hold
        class Target:
            @classmethod
            def alloc(cls):
                return cls()

            def init(self):
                return self

        gesture = Mock()
        objc = NS(ObjCClass=lambda name: Target if name == 'NSObject' else gesture,
                  SEL=lambda selector: selector, objc_method=lambda method: method)
        view, native = Mock(), Mock()
        with patch.dict('sys.modules', {'rubicon.objc': objc}), \
                patch('mobile.document_location._apple_hold_target', None), \
                patch('toga.InfoDialog') as dialog:
            bind_apple_hold(view, native)
            native.addGestureRecognizer.assert_called_once()
            view._document_path.return_value = 'Vault/Projects/Report.md'
            for state in (1, 2, 3):
                view._title_hold_target.hold_(NS(state=state))
            dialog.assert_called_once_with('Document location', 'Vault/Projects/Report.md')
            view.window.dialog.assert_called_once_with(dialog.return_value)
            view.window = None
            view._title_hold_target.hold_(NS(state=1))
            self.assertEqual(dialog.call_count, 1)

    def test_side_header_reserves_title_height_after_bar_compression(self):
        from mobile.document_location import place_title_in_header
        host = Mock()
        header = NS(style=NS(height=0), _impl=NS(native=host))
        title = Mock()
        title.bounds.size.height = 0
        place_title_in_header(header, title, 'On-device')
        self.assertEqual(header.style.height, 37)
        host.addSubview.assert_called_once_with(title)
        title.superview = host
        header.style.height = 0
        place_title_in_header(header, title, 'On-device')
        self.assertEqual(header.style.height, 37)
        host.addSubview.assert_called_once()
        place_title_in_header(header, title, '')
        self.assertEqual(header.style.height, 21)

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

    def test_notes_title_stays_in_content_when_ios_actions_move_to_the_side(self):
        view = toga.Box()
        view._document_path = lambda: 'Vault/Project/Notes.md'
        controller = NS(view=NS(bounds=NS(size=NS(width=466))), navigationItem=NS(titleView=None))
        with patch('mobile.folder_title.storage_title', return_value=object()), \
                patch('mobile.ios_toolbar.vertical_edge', return_value=2) as edge, \
                patch('mobile.document_location.bind_apple_hold') as bind, \
                patch('mobile.document_location.empty_bar_title', return_value=object()), \
                patch('mobile.document_location.place_title_in_header'):
            mount_apple_title(view, controller, 'Notes.md')
            header = view._document_title_header
            self.assertIs(view.children[0], header)
            self.assertIs(controller.navigationItem.titleView, header._empty_bar_title)
            bind.assert_called_once_with(view, view._document_title_view)
            edge.return_value = 0
            mount_apple_title(view, controller, 'Notes.md')
            self.assertIsNone(header.parent)
            self.assertIs(controller.navigationItem.titleView, view._document_title_view)

    def test_routes_without_storage_clear_previous_subtitle(self):
        controller = NS(navigationItem=NS(titleView=object()))
        mount_apple_title(toga.Box(), controller, 'Settings')
        self.assertIsNone(controller.navigationItem.titleView)

    def test_library_pane_controls_surround_title_across_bar_orientations(self):
        view = toga.Box()
        view._document_path = lambda: 'Library'
        left, right = toga.Button('Files'), toga.Button('Links')
        view._document_title_controls = (left, right)
        controller = NS(view=NS(bounds=NS(size=NS(width=466))), navigationItem=NS(titleView=None))
        with patch('mobile.folder_title.storage_title', return_value=object()) as make, \
                patch('mobile.ios_toolbar.vertical_edge', return_value=2) as edge, \
                patch('mobile.document_location.bind_apple_hold'), \
                patch('mobile.document_location.empty_bar_title', return_value=object()), \
                patch('mobile.document_location.place_title_in_header') as place:
            for orientation in (2, 0, 2):
                edge.return_value = orientation
                mount_apple_title(view, controller, 'A long library name')
                header = view._document_title_header
                self.assertEqual(list(header.children), [left, header._title_content, right])
                self.assertIs(view.children[0], header)
                self.assertIs(controller.navigationItem.titleView, header._empty_bar_title)
                place.assert_called_with(header, view._document_title_view, '')
            self.assertEqual(make.call_args.args[0], 'A long library name')
