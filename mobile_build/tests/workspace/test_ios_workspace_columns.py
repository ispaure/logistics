"""Native Workspaces containment follows allocation without replacing routes."""
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

import toga

from mobile.ios_workspace_columns import WorkspaceColumns, sync


class WorkspaceColumnsTests(TestCase):
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
        workspace = NS(app=app, content_width=Mock(return_value=900))
        with patch('mobile.fold_layout.division', return_value=None), \
                patch('mobile.ios_workspace_columns.WorkspaceColumns') as create:
            sync(workspace)
            columns = workspace.file_columns
            create.assert_called_once_with(workspace, master)
            workspace.content_width.return_value = 1000
            sync(workspace)
            create.assert_called_once()
            columns.layout.assert_called_once()
            workspace.content_width.return_value = 390
            sync(workspace)
            columns.close.assert_called_once()
            self.assertIsNone(workspace.file_columns)
            sync(workspace)
            columns.close.assert_called_once()

    def test_sidebar_layout_keeps_its_assigned_column_frame(self):
        frame = object()
        container = NS(native=NS(frame=frame, bounds=NS(size=NS(width=330)),
                                safeAreaInsets=NS(top=24, bottom=20, left=0, right=0)),
                       content=NS(interface=Mock()))
        columns = object.__new__(WorkspaceColumns)
        columns.app, columns.sidebar_box = Mock(), Mock()
        with patch('mobile.appearance.reserve_navigation') as reserve, \
                patch('mobile.folder_hub_ui.reflow_folder_notice') as notice:
            columns.layout_sidebar(container)
        notice.assert_called_once_with(columns.app, 306)
        reserve.assert_called_once_with(columns.app, view=columns.sidebar_box)
        self.assertIs(container.native.frame, frame)
        self.assertEqual((container.top_inset, container.bottom_inset), (24, 20))
        container.content.interface.refresh.assert_called_once()

    def test_root_layout_never_publishes_inner_navigation_as_the_tab_controller(self):
        wrapper, bounds = object(), object()
        columns = object.__new__(WorkspaceColumns)
        columns.navigation = NS(view=NS(bounds=bounds))
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
        columns.app = Mock()
        columns.controller = NS(view=native)
        columns._layout_targets = ((62, 0, 367, 402), (445, 0, 367, 402))
        def rect(origin, size):
            return NS(origin=NS(x=origin[0], y=origin[1]), size=NS(width=size[0], height=size[1]))
        with patch.dict('sys.modules', {'rubicon.objc': NS(CGRect=rect)}), \
                patch('mobile.fold_layout.division', return_value=None), \
                patch('mobile.fold_layout.has_fold', return_value=False):
            columns.layout()
        self.assertIs(native.frame, bounds)
        self.assertEqual(native.bounds.size.height, 402)

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
