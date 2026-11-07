"""Measured Home header restores the same controls when its free band contracts."""
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

from commonUtils.testing.stages import TestStage
import toga
from toga.style import Pack
from mobile import home_header

TEST_STAGE = TestStage.REGRESSION


class HomeHeaderTests(TestCase):
    def test_overview_actions_use_the_selected_tab_navigation_owner(self):
        from mobile.destination_actions import project_header, sync_native_host
        child, outer = Mock(), Mock()
        child.isNavigationBarHidden.return_value = True
        outer.isNavigationBarHidden.return_value = False
        view = NS(_destination_actions=(object(), [object(), object()]))
        adapter = NS(outer_navigation=outer, navigation_for=Mock(return_value=child))
        app = NS(routes=NS(apple=True, screens={'documents': []}),
                 native_host=NS(adapter=adapter), home_unlock_candidates=lambda: [])
        with (patch('mobile.destination_actions.project_header', wraps=project_header) as project,
              patch('mobile.ios_system_occlusions.reserve_bar_clearance') as configure):
            sync_native_host(app, view, 'documents')
        project.assert_called_once_with(app, view, 'documents')
        outer.setNavigationBarHidden.assert_called_once_with(True, animated=False)
        child.setNavigationBarHidden.assert_called_once_with(False, animated=False)
        adapter.navigation_for.assert_called_once_with('documents')
        self.assertEqual([call.args[0] for call in configure.call_args_list], [outer, child])

    def test_cold_duo_prepares_menu_without_a_hinge_or_native_navigation_adapter(self):
        from mobile.destination_actions import prepare
        row = toga.Box(children=[toga.Button('Open Document'), toga.Button('New Document')])
        content = toga.Box(children=[row])
        content._home_primary_actions = row
        content._home_primary_buttons = tuple(row.children)
        app = NS(routes=NS(apple=False), show_home_unlock=Mock(), home_unlock_candidates=lambda: [])
        with patch('mobile.fold_layout.is_iphone_duo', return_value=True), patch(
                'mobile.fold_layout.has_fold', side_effect=AssertionError('Home is not mounted yet')):
            prepare(app, content, 'home')
        self.assertIsNone(row.parent)
        self.assertEqual([title for title, _ in content._home_document_menu._home_commands.actions],
                         ['Open Document', 'New Document'])

    def test_preparing_wrapped_home_keeps_header_metadata(self):
        from mobile.destination_actions import prepare
        row = toga.Box(children=[toga.Button('Open'), toga.Button('New')])
        original = toga.Box(children=[row])
        original._hub_sections = True
        original._home_primary_actions = row
        original._home_primary_buttons = tuple(row.children)
        app = NS(show_home_unlock=Mock(), routes=NS(apple=True))
        view = prepare(app, original, 'home')
        self.assertIsNot(view, original)
        self.assertIs(view._home_primary_actions, row)
        self.assertEqual(view._home_primary_buttons, tuple(row.children))

    def test_overview_projection_retains_actions_and_restores_on_capacity_loss(self):
        from mobile.destination_actions import project_header
        buttons = [toga.Button(name, on_press=Mock(), style=Pack(width=48, height=48))
                   for name in ('Open', 'New', 'Search', 'Unlock')]
        header = toga.Box(style=Pack(margin=(0, 0, 8, 0)))
        original_height = header.style.height
        view = toga.Box(children=[header], style=Pack(margin=(8, 16, 16, 16)))
        view._destination_actions = header, buttons
        view._ios_toolbar_buttons = lambda: buttons
        view._ios_toolbar_leading = []
        frame = NS(origin=NS(x=0, y=0), size=NS(width=669, height=951))
        controller = NS(view=NS(bounds=frame, convertRect=lambda *a, **kw: frame))
        # Let Toga retain its own app/window while exercising native placement.
        adapter = NS(content_controller=lambda _: controller, layout_content=Mock())
        app = NS(native_host=NS(adapter=adapter), main_window=NS(_impl=NS(native=NS(safeAreaInsets=NS(top=82)))))
        app.widgets = Mock()
        app.main_window.app = app
        self.enterContext(patch('mobile.fold_layout.division', return_value=None))
        self.enterContext(patch('mobile.ios_toolbar.vertical_edge', return_value=0))
        regions = self.enterContext(patch('mobile.ios_toolbar.system_occlusions', return_value=((443, 0, 226, 82),)))
        callbacks = [button.on_press for button in buttons]
        for _ in range(2):
            self.assertTrue(project_header(app, view, 'files'))
            self.assertEqual(header.children[0].children, buttons)
            self.assertEqual(header.children[0].style.height, 48)
            self.assertEqual(header.style.margin_left, 0)
            regions.return_value = ((180, 0, 489, 82),)
            self.assertFalse(project_header(app, view, 'files'))
            self.assertIsNone(view._destination_top_band)
            self.assertIsNone(header.parent)
            self.assertEqual(header.style.height, original_height)
            self.assertEqual(header.style.margin, (0, 0, 8, 0))
            regions.return_value = ((443, 0, 226, 82),)
        self.assertEqual([button.on_press for button in buttons], callbacks)

    def test_activity_rotation_and_large_text_restore_original_actions(self):
        actions = [toga.Button(title, on_press=Mock(), style=Pack(height=72, flex=1))
                   for title in ('Open Document', 'New Document')]
        unlock = toga.Button('Unlock', style=Pack(width=48, height=48))
        row = toga.Box(children=actions)
        view = toga.Box(children=[row])
        view._home_primary_actions, view._home_primary_buttons = row, tuple(actions)
        view._destination_actions = (toga.Box(), [unlock])
        frame = NS(origin=NS(x=0, y=0), size=NS(width=669, height=951))
        controller = NS(view=NS(bounds=frame, convertRect=lambda *a, **kw: frame))
        adapter = NS(content_controller=lambda destination: controller, layout_content=Mock())
        app = NS(native_host=NS(adapter=adapter), home_unlock_candidates=Mock(return_value=['fixture']),
                 main_window=NS(_impl=NS(native=NS(safeAreaInsets=NS(top=82)))))
        size = NS(width=140, height=34)
        for button in [*actions, unlock]:
            self.enterContext(patch.object(button._impl, 'native', NS(sizeThatFits=lambda _: size), create=True))
        self.enterContext(patch.dict('sys.modules', {'rubicon.objc': NS(CGSize=lambda *args: args)}))
        self.enterContext(patch('mobile.fold_layout.division', return_value=None))
        regions = self.enterContext(patch('mobile.ios_toolbar.system_occlusions', return_value=((535, 0, 134, 82),)))
        edge = self.enterContext(patch('mobile.ios_toolbar.vertical_edge', return_value=0))
        callbacks = [button.on_press for button in actions]
        for _ in range(2):
            self.assertTrue(home_header.sync(app, view))
            self.assertEqual(row.children, [*actions, unlock])
            self.assertEqual([button.style.height for button in actions], [48, 48])
            self.assertEqual(row.style.margin_right, 134)
            regions.return_value = ((300, 0, 369, 160),)
            self.assertFalse(home_header.sync(app, view))
            self.assertEqual(row.children, actions)
            self.assertEqual([button.style.height for button in actions], [72, 72])
            regions.return_value = ((535, 0, 134, 82),)
        self.assertTrue(home_header.sync(app, view))
        edge.return_value = 2
        self.assertFalse(home_header.sync(app, view))
        edge.return_value = 0
        size.height = 90
        self.assertFalse(home_header.sync(app, view))
        self.assertEqual([button.on_press for button in actions], callbacks)
        self.assertEqual([button.style.height for button in actions], [72, 72])

    def test_native_rail_and_safe_horizontal_row_reuse_the_same_actions(self):
        from mobile.destination_actions import prepare

        primary = [toga.Button(title, style=Pack(height=48, flex=1))
                   for title in ('Open Document', 'New Document')]
        row = toga.Box(children=primary)
        original = toga.Box(children=[row])
        original._home_primary_actions, original._home_primary_buttons = row, tuple(primary)
        frame = NS(origin=NS(x=0, y=50), size=NS(width=390, height=840))
        controller = NS(view=NS(bounds=frame, convertRect=lambda *a, **kw: frame,
                                safeAreaInsets=NS(left=0, right=0)))
        app = NS(routes=NS(apple=True), show_home_unlock=Mock(),
                 native_host=NS(adapter=NS(content_controller=lambda _: controller)),
                 home_unlock_candidates=Mock(return_value=[]),
                 main_window=NS(_impl=NS(native=NS(safeAreaInsets=NS(top=50)))))
        view = prepare(app, original, 'home')
        unlock = view._destination_actions[1][0]
        for button in [*primary, unlock]:
            size = NS(width=48 if button is unlock else 120, height=38)
            self.enterContext(patch.object(button._impl, 'native', NS(sizeThatFits=lambda _, size=size: size),
                                           create=True))
        self.enterContext(patch.dict('sys.modules', {'rubicon.objc': NS(CGSize=lambda *args: args)}))
        self.enterContext(patch('mobile.fold_layout.division', return_value=None))
        edge = self.enterContext(patch('mobile.ios_toolbar.vertical_edge', return_value=2))

        self.assertFalse(home_header.sync(app, view))
        self.assertEqual(view._ios_toolbar_buttons(), primary)
        app.home_unlock_candidates.return_value = ['fixture']
        self.assertEqual(view._ios_toolbar_buttons(), [unlock, *primary])
        for button in primary:
            row.remove(button)  # Shared toolbar projection detaches the targets.

        edge.return_value = 0
        self.assertTrue(home_header.sync(app, view))
        self.assertEqual(row.children, [*primary, unlock])
        self.assertTrue(view._home_inline_unlock)
        frame.size.width = 320
        self.assertFalse(home_header.sync(app, view))
        self.assertEqual(row.children, primary)
        self.assertEqual(view._ios_toolbar_buttons(), [unlock])
        self.assertFalse(view._home_inline_unlock)

    def test_inline_row_avoids_detached_activity_below_the_safe_top(self):
        home = NS(_home_inline_unlock=True)
        root = NS(children=[home])
        native = NS(bounds=NS(size=NS(width=390)))
        container = NS(content=NS(interface=root), native=native,
                       left_inset=0, right_inset=0, top_inset=50)
        with patch('mobile.ios_reader_chrome.occlusion_geometry', return_value=((100, 48, 190, 50),)):
            self.assertTrue(home_header.compact_content_top(container))
            self.assertEqual(container.top_inset, 106)
            self.assertFalse(home_header.compact_content_top(container))
