"""Native Workspaces containment follows allocation without replacing routes."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

import toga

from mobile.ios_workspace_columns import WorkspaceColumns, sync
from mobile.ios_system_occlusions import observe_window_occlusions
from mobile.workspace_navigation import WorkspaceFrame


class WorkspaceColumnsTests(TestCase):
    def test_native_prompt_discards_portable_pane_dimensions(self):
        frame = object.__new__(WorkspaceFrame)
        frame.row = toga.Box()
        prompt = frame._folder_prompt()
        prompt.style.width = 350
        prompt.style.height = 300
        prompt.style.margin_left = 36
        prompt.style.margin_top = 24
        prompt.style.flex = 0
        for _ in range(2):
            frame.mount_native_folder_prompt()
        self.assertEqual(list(frame.row.children), [prompt])
        self.assertEqual(prompt.style.width, toga.Box().style.width)
        self.assertEqual(prompt.style.height, toga.Box().style.height)
        self.assertEqual((prompt.style.margin_left, prompt.style.margin_top, prompt.style.flex), (0, 0, 1))
        self.assertEqual((prompt.style.align_items, prompt.style.justify_content), ('center', 'start'))

    def test_route_policy_mock_does_not_create_native_controllers(self):
        workspace = NS(app=NS(_impl=NS(), routes=NS(apple=True)))
        with patch('mobile.ios_workspace_columns.WorkspaceColumns') as create:
            sync(workspace)
        create.assert_not_called()

    def test_resize_reuses_columns_then_restores_compact_owner(self):
        master = NS()
        view = toga.Box()
        view._workspace_frame = master
        root = toga.Box(children=[view])
        native_impl = type('AppleApp', (), {'__module__': 'toga_iOS.app'})()
        app = NS(_impl=native_impl, native_host=NS(adapter=NS(navigation=[])), routes=NS(roots={'files': root}), main_window=Mock())
        app.main_window.size = NS(width=900, height=600)
        workspace = NS(app=app, content_width=Mock(return_value=900))
        with patch('mobile.fold_layout.division', return_value=None), \
                patch('mobile.ios_workspace_columns.WorkspaceColumns') as create:
            create.return_value.master = master
            sync(workspace)
            columns = workspace.file_columns
            create.assert_called_once_with(workspace, master)
            workspace.content_width.return_value = 1000
            sync(workspace)
            create.assert_called_once()
            columns.layout.assert_called_once()
            app.main_window.size = NS(width=800, height=1100)
            workspace.content_width.return_value = 800
            sync(workspace)
            columns.close.assert_called_once()
            self.assertIsNone(workspace.file_columns)
            sync(workspace)
            columns.close.assert_called_once()

    def test_rebuilt_workspaces_root_mounts_its_own_native_columns(self):
        previous, master = NS(), NS()
        view = toga.Box()
        view._workspace_frame = master
        native_impl = type('AppleApp', (), {'__module__': 'toga_iOS.app'})()
        app = NS(_impl=native_impl, native_host=NS(adapter=NS(navigation=[])),
                 routes=NS(roots={'files': toga.Box(children=[view])}),
                 main_window=NS(size=NS(width=900, height=600)))
        retired = Mock(master=previous)
        workspace = NS(app=app, content_width=lambda *_args, **_kwargs: 900, file_columns=retired)
        with patch('mobile.fold_layout.division', return_value=None), \
                patch('mobile.ios_workspace_columns.WorkspaceColumns') as create:
            sync(workspace)
        retired.close.assert_called_once()
        retired.layout.assert_not_called()
        create.assert_called_once_with(workspace, master)
        self.assertIs(workspace.file_columns, create.return_value)

    def test_native_prompt_aligns_to_the_source_row_even_when_the_detail_starts_lower(self):
        columns = WorkspaceColumns.__new__(WorkspaceColumns)
        source = NS(layout=NS(absolute_content_top=12))
        row = NS(layout=NS(absolute_content_top=8))
        prompt = NS(parent=row, style=NS(margin_top=0))
        columns.master = NS(row=row, folder_placeholder=prompt,
                            view=lambda: NS(_workspaces_source_row=source))
        columns.sidebar = NS(top_inset=48)
        columns.root_container = NS(top_inset=60)
        columns._layout_targets = ((0, 0), (388, 0))
        columns.align_prompt()
        self.assertEqual(prompt.style.margin_top, -8)

    def test_sidebar_layout_keeps_its_assigned_column_frame(self):
        frame = object()
        container = NS(native=NS(frame=frame, bounds=NS(size=NS(width=330)),
                                safeAreaInsets=NS(top=24, bottom=20, left=0, right=0)),
                       content=NS(interface=Mock()))
        columns = object.__new__(WorkspaceColumns)
        columns.closed = False
        columns.master = NS()
        columns.app, columns.sidebar_box = Mock(), Mock()
        with patch('mobile.appearance.reserve_navigation') as reserve, \
                patch('mobile.destination_actions.compact_content_top') as project_header, \
                patch('mobile.folder_hub_ui.reflow_folder_notice') as notice:
            columns.layout_sidebar(container)
        project_header.assert_called_once_with(container)
        notice.assert_called_once_with(columns.app, 306)
        reserve.assert_called_once_with(columns.app, view=columns.sidebar_box)
        self.assertIs(container.native.frame, frame)
        self.assertEqual((container.top_inset, container.bottom_inset), (24, 20))
        container.content.interface.refresh.assert_called_once()

    def test_root_layout_never_publishes_inner_navigation_as_the_tab_controller(self):
        wrapper, bounds = object(), object()
        columns = object.__new__(WorkspaceColumns)
        columns.closed = False
        columns.master = NS()
        columns.navigation = NS(view=NS(bounds=bounds))
        columns.app = NS(routes=NS(screens={'files': []}))
        container = NS(controller=wrapper, native=NS(safeAreaInsets=NS(top=0, bottom=20, left=0, right=0)),
                       content=NS(interface=Mock()))
        columns.layout_root(container)
        self.assertIs(container.controller, wrapper)
        self.assertIs(container.native.frame, bounds)
        container.content.interface.refresh.assert_called_once()

    def test_keyboard_return_repairs_stale_wrapper_before_geometry_cache(self):
        bounds = NS(size=NS(width=874, height=402))
        class Native:
            superview = NS(bounds=bounds)
            safeAreaInsets = NS(left=62, right=62)
            def __init__(self):
                self.bounds = NS(size=NS(width=874, height=147))
            @property
            def frame(self):
                return self._frame
            @frame.setter
            def frame(self, value):
                self._frame = value
                self.bounds = value
        native = Native()
        columns = object.__new__(WorkspaceColumns)
        columns.closed = False
        columns.app = NS(routes=NS(screens={'files': []}))
        columns.sidebar = NS(controller=NS(view=NS(hidden=False)))
        columns.controller = NS(view=native)
        columns.layout_sidebar = Mock()
        columns._layout_targets = ((62, 0, 367, 402), (445, 0, 429, 402))
        def rect(origin, size):
            return NS(origin=NS(x=origin[0], y=origin[1]), size=NS(width=size[0], height=size[1]))
        with patch.dict('sys.modules', {'rubicon.objc': NS(CGRect=rect)}), \
                patch('mobile.fold_layout.division', return_value=None), \
                patch('mobile.fold_layout.has_fold', return_value=False):
            columns.layout()
        self.assertIs(native.frame, bounds)
        self.assertEqual(native.bounds.size.height, 402)

    def test_cold_landscape_replays_sidebar_insets_on_root_only_occlusion_update(self):
        def rect(origin, size):
            return NS(origin=NS(x=origin[0], y=origin[1]), size=NS(width=size[0], height=size[1]))

        columns = object.__new__(WorkspaceColumns)
        columns.closed = False
        callbacks = []
        navigation = NS(view=NS(setNeedsLayout=Mock(), layoutIfNeeded=Mock()), navigationBar=Mock())

        class Adapter(NS):
            pass

        adapter = Adapter(navigation=[navigation])
        columns.app = NS(active_host=True, routes=NS(screens={'files': []}),
                         native_host=NS(adapter=adapter), loop=NS(call_soon=callbacks.append),
                         resize_workspace=columns.layout)
        columns.navigation = navigation
        columns.master = NS(mount_native_folder_prompt=Mock())
        columns.sidebar_box = object()
        safe = NS(top=84, bottom=20, left=0, right=0)
        window = NS(superview=None, bounds=rect((0, 0), (951, 669)), safeAreaInsets=safe,
                    respondsToSelector=lambda selector: True)
        root = NS(superview=None, bounds=window.bounds, safeAreaInsets=safe, window=window,
                  convertRect=lambda bounds, **kwargs: bounds)
        columns.controller = NS(view=root)
        native = NS(bounds=rect((0, 0), (374, 669)), safeAreaInsets=safe, window=window,
                    convertRect=lambda bounds, **kwargs: rect((24, 0), (374, 669)),
                    respondsToSelector=lambda selector: True, layoutIfNeeded=Mock())
        refresh = Mock()
        columns.sidebar = NS(native=native, controller=NS(view=native),
                             top_inset=0, bottom_inset=0, left_inset=0, right_inset=0,
                             content=NS(interface=NS(refresh=refresh)))
        bridge = NS(CGRect=rect, SEL=lambda value: value)
        with patch.dict('sys.modules', {'rubicon.objc': bridge}), \
                patch('mobile.fold_layout.division', return_value=None), \
                patch('mobile.fold_layout.has_fold', return_value=True), \
                patch('ctypes.CDLL') as library, \
                patch('mobile.ios_toolbar.vertical_edge', return_value=2) as edge, \
                patch('mobile.appearance.reserve_navigation'), \
                patch('mobile.folder_hub_ui.reflow_folder_notice'), \
                patch('mobile.ios_system_occlusions.reserve_bar_clearance'), \
                patch('mobile.ios_reader_chrome.occlusion_geometry') as regions:
            window_regions = ()
            regions.side_effect = lambda view: window_regions if view is window else ()
            library.return_value.UIAccessibilityIsReduceMotionEnabled.return_value = True
            # The first layout is already landscape. UIKit has supplied the safe
            # area and bar edge, but has yet to report the trailing system cluster.
            columns.layout()
            initial_frame = native.frame
            self.assertEqual(columns.sidebar.top_inset, 84)
            refresh.assert_called_once_with()
            observe_window_occlusions(columns.app, window)
            callbacks.pop()()
            refresh.assert_called_once_with()

            # Only the root is notified. Neither Toga's sidebar callback nor
            # a rotation runs before the observer replays workspace layout.
            window_regions = ((867, 0, 84, 84),)
            observe_window_occlusions(columns.app, window)
            callbacks.pop()()
            self.assertEqual(columns.sidebar.top_inset, 0)
            self.assertEqual(columns.sidebar.bottom_inset, 20)
            self.assertIs(native.frame, initial_frame)
            self.assertEqual(refresh.call_count, 2)

            # A later cluster that overlaps the sidebar must restore clearance,
            # still with the same frame and UIKit safe-area rectangle.
            window_regions = ((398, 0, 52, 96),)
            observe_window_occlusions(columns.app, window)
            callbacks.pop()()
            self.assertEqual(columns.sidebar.top_inset, 0)
            window_regions = ((390, 0, 52, 96),)
            observe_window_occlusions(columns.app, window)
            callbacks.pop()()
            self.assertEqual(columns.sidebar.top_inset, 104)
            window_regions = ()
            observe_window_occlusions(columns.app, window)
            callbacks.pop()()
            self.assertEqual(columns.sidebar.top_inset, 84)
            self.assertEqual(refresh.call_count, 4)
            self.assertIs(native.frame, initial_frame)
            native.layoutIfNeeded.assert_called_once_with()

            # A warm rotation uses the changed-frame path. Horizontal bars
            # keep their native inset, even with a side-only reserved region.
            edge.return_value = 0
            window_regions = ((867, 0, 84, 84),)
            root.bounds = rect((0, 0), (669, 951))
            safe.top = 116
            columns.layout()
            self.assertEqual(columns.sidebar.top_inset, 116)
            edge.return_value = 2
            root.bounds = rect((0, 0), (951, 669))
            safe.top = 84
            columns.layout()
            self.assertEqual(columns.sidebar.top_inset, 0)
            self.assertEqual(native.frame, initial_frame)
            self.assertEqual(refresh.call_count, 6)
            columns.master.mount_native_folder_prompt.assert_called_once_with()

    def test_documents_and_their_tools_use_whole_column_container_then_restore_browser(self):
        def rect(origin, size):
            return NS(origin=NS(x=origin[0], y=origin[1]), size=NS(width=size[0], height=size[1]))
        columns = object.__new__(WorkspaceColumns)
        columns.closed = False
        screens = [('folder:books', None, '')]
        columns.app = NS(routes=NS(screens={'files': screens}))
        native = NS(superview=None, bounds=rect((0, 0), (0, 0)),
                    safeAreaInsets=NS(left=20, right=10), window=None)
        columns.controller = NS(view=native)
        columns.sidebar = NS(controller=NS(view=NS(hidden=False, layoutIfNeeded=Mock())))
        columns.navigation = NS(view=NS(layoutIfNeeded=Mock()))
        heading = NS(hidden=False)
        columns._heading_container = NS(native=heading)
        columns._heading_box = NS(children=[object()])
        columns.master = NS(mount_native_folder_prompt=Mock())
        def mount_prompt():
            frame = columns.navigation.view.frame
            self.assertGreater(frame.origin.x, 20)
            self.assertEqual(frame.origin.x + frame.size.width, 900)
        columns.master.mount_native_folder_prompt.side_effect = mount_prompt
        columns.layout_sidebar = Mock()
        with patch.dict('sys.modules', {'rubicon.objc': NS(CGRect=rect)}), \
                patch('mobile.fold_layout.division', return_value=None), \
                patch('mobile.fold_layout.has_fold', return_value=False), \
                patch('ctypes.CDLL'):
            columns.layout()
            columns.master.mount_native_folder_prompt.assert_not_called()
            native.bounds = rect((0, 0), (900, 600))
            columns.layout()
            columns.master.mount_native_folder_prompt.assert_called_once()
            browser_frame = columns.navigation.view.frame
            self.assertGreater(browser_frame.origin.x, 20)
            self.assertEqual(browser_frame.origin.x + browser_frame.size.width, 900)
            self.assertTrue(heading.hidden)
            reader = NS(children=[NS(_reader_session_id='retained')])
            for route, panel in (('file-loading:comic', None), ('reader:comic', None), ('editor', None),
                                 ('private:pdf', None), ('notebook:notes', None), ('notes-library:vault', None),
                                 ('restored-view', reader)):
                with self.subTest(route=route):
                    screens[:] = [('folder:books', None, ''), (route, panel, ''), ('reader-tools', None, '')]
                    for width, height in ((900, 600), (650, 980)):
                        native.bounds = rect((0, 0), (width, height))
                        columns.layout()
                        frame = columns.navigation.view.frame
                        self.assertTrue(columns.sidebar.controller.view.hidden)
                        self.assertEqual((frame.origin.x, frame.origin.y), (0, 0))
                        self.assertEqual((frame.size.width, frame.size.height), (width, height))
            screens[:] = [('folder:books', None, '')]
            native.bounds = rect((0, 0), (900, 600))
            columns.layout()
            self.assertTrue(heading.hidden)
            screens.clear()
            columns.layout()
            self.assertFalse(heading.hidden)
            columns.layout_sidebar.assert_called_with(columns.sidebar, insets_only=True)
        self.assertFalse(columns.sidebar.controller.view.hidden)
        restored = columns.navigation.view.frame
        self.assertEqual((restored.origin.x, restored.size.width),
                         (browser_frame.origin.x, browser_frame.size.width))
        self.assertEqual(columns.layout_sidebar.call_count, 3)
        columns.master.mount_native_folder_prompt.assert_called_once()

    def test_active_fold_retains_native_columns_below_flat_breakpoint(self):
        view = toga.Box()
        view._workspace_frame = NS()
        app = NS(_impl=type('AppleApp', (), {'__module__': 'toga_iOS.app'})(),
                 native_host=NS(adapter=NS(navigation=[])),
                 routes=NS(roots={'files': toga.Box(children=[view])}), main_window=Mock())
        workspace = NS(app=app, content_width=Mock(return_value=600))
        with patch('mobile.fold_layout.division', return_value=object()), \
                patch('mobile.ios_workspace_columns.WorkspaceColumns') as create:
            sync(workspace)
            self.assertIs(workspace.file_columns, create.return_value)

    def test_closed_columns_ignore_late_native_layout_callbacks(self):
        columns = object.__new__(WorkspaceColumns)
        columns.closed = True
        columns.layout()
        columns.layout_root(None)
        columns.layout_sidebar(None)

    def test_close_retires_callbacks_before_native_detach_without_nil_weak_owner(self):
        import weakref
        class WeakOwnerController:
            @property
            def owner(self):
                return self._owner()
            @owner.setter
            def owner(self, value):
                self._owner = weakref.ref(value)
        columns = object.__new__(WorkspaceColumns)
        columns.closed = False
        columns.controller = WeakOwnerController()
        columns.controller.owner = columns
        container = Mock()
        container.setViewControllers.side_effect = lambda *a, **k: self.assertTrue(columns.closed)
        columns.adapter = NS(controller=container, impl=NS(refresh_tabs=Mock()))
        columns.navigation = Mock()
        columns.navigation_autoresizing = 18
        columns.sidebar = NS(controller=Mock(), content=object())
        columns.master = NS(main=toga.Box(), row=toga.Box())
        columns.sidebar_box = NS(window=object(), app=object())
        columns.root_container = NS(controller=object(), on_native_layout=None)
        columns.old_root_layout = object()
        columns.app = NS(native_host=NS(activate=Mock(), state=NS(destination='files')))
        columns.close()
        columns.close()
        container.setViewControllers.assert_called_once_with([], animated=False)
        self.assertIsNone(columns.sidebar.content)
        self.assertIs(columns.root_container.controller, columns.navigation)
        self.assertIs(columns.controller.owner, columns)
