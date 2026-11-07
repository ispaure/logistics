"""Measured native reader chrome keeps all targets and restores other owners."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, PropertyMock, patch
from commonUtils.testing.stages import TestStage
from mobile import reader_top_band as band
from mobile.document_location import mount_apple_title as refresh_native_title, place_title_in_header as refresh_title_in_header

TEST_STAGE = TestStage.REGRESSION


def rect(width=669, height=951, x=0, y=0):
    return NS(origin=NS(x=x, y=y), size=NS(width=width, height=height))


class BandGeometryTests(unittest.TestCase):
    def test_canvas_header_cannot_be_replaced_by_native_top_band(self):
        view = NS(_canvas_document_title=True)
        with patch.object(band, 'restore') as restore:
            self.assertFalse(band.project(object(), view, 'documents', object()))
            restore.assert_called_once_with(view)

    def test_actual_inner_portrait_moves_controls_into_free_column_with_safe_page_clearance(self):
        value = band.free_top_band(((535, 0, 134, 82),), 669, 82, 5 * 48 + 44 + 32)
        self.assertEqual(value, dict(left=0, right=535, width=669, row_height=60, row_top=11, reserve=90))

    def test_lowered_controls_still_avoid_expanded_activity_and_restore(self):
        regions = ((535, 0, 134, 82), (200, 64, 469, 30))
        self.assertIsNone(band.free_top_band(regions, 669, 82, 316))
        normal = band.free_top_band(regions[:1], 669, 82, 316)
        self.assertEqual(normal['row_top'] + normal['row_height'] / 2, 82 / 2)

    def test_missing_full_width_centered_short_or_too_narrow_keeps_existing_chrome(self):
        for regions, width, top, minimum in (((),669,82,316),
                (((0,0,669,82),),669,82,316), (((250,0,100,82),),669,82,316),
                (((535,0,134,24),),669,24,316), (((200,0,134,82),),334,82,316)):
            with self.subTest(regions=regions):
                self.assertIsNone(band.free_top_band(regions,width,top,minimum))

    def test_mirrored_edge_and_detached_activity_keep_geometry_clear(self):
        value = band.free_top_band(((0,0,134,82),),669,82,316)
        self.assertEqual((value['left'],value['right']), (134,669))
        value = band.free_top_band(((535,0,134,82),(535,100,134,30)),669,82,316)
        self.assertEqual(value['reserve'],138)


class NativeBandContentInsetsTests(unittest.TestCase):
    def test_native_header_reserves_clock_inside_content_without_negative_window_origin(self):
        from mobile.reader_edges import compact_apple_reader
        for origin_y, expected in ((0,0),(-20,20)):
            with self.subTest(origin_y=origin_y):
                window=NS(safeAreaInsets=NS(top=82,bottom=34))
                native=NS(window=window,bounds=rect(),safeAreaInsets=NS(bottom=34),
                    convertRect=lambda *args,**kwargs:rect(y=origin_y))
                reader=NS(children=[],_reader_top_band_state={'geometry':{'reserve':90}})
                reader._document_title_header=NS(parent=reader)
                container=NS(native=native,top_inset=148,bottom_inset=34,left_inset=0,right_inset=0,
                    content=NS(interface=NS(app=NS(),children=[reader])))
                with patch('mobile.appearance.reserve_navigation'):
                    self.assertTrue(compact_apple_reader(container))
                self.assertEqual(container.top_inset,expected)
                self.assertEqual(reader._reader_top_band_state['geometry']['reserve'],90)


class NativeBandOwnershipTests(unittest.TestCase):
    def setUp(self):
        import toga
        from toga.style import Pack
        from mobile_build.tests.support.app import create_app
        self.app = create_app(self)
        self.view = toga.Box()
        self.buttons = [toga.Button(str(i), on_press=Mock(), style=Pack(width=48,height=48)) for i in range(5)]
        self.view._reader_close_button = self.buttons[0]
        self.view._native_reader_buttons = lambda:self.buttons[1:]
        self.view._native_reader_toolbar = toga.Box(children=self.buttons[1:])
        self.view.add(self.view._native_reader_toolbar)
        self.view._native_reader_title = lambda:'Retained notebook'
        self.view._document_storage_status = 'On-device'
        self.view._document_storage_kinds = [('storage_local','On-device folder')]
        native = NS(bounds=rect(),convertRect=lambda *args,**kwargs:rect())
        self.controller = NS(ptr=NS(value=13),view=native,navigationItem=NS(title='Retained notebook',titleView=None))
        self.navigation = NS(hidden=False)
        self.navigation.isNavigationBarHidden = lambda:self.navigation.hidden
        self.navigation.setNavigationBarHidden = lambda hidden,**kwargs:setattr(self.navigation,'hidden',hidden)
        adapter = NS(navigation=[self.navigation], navigation_for=lambda destination:self.navigation,
                     content_controller=lambda destination:self.controller, layout_content=Mock())
        self.enterContext(patch.object(self.app.native_host,'adapter',adapter))
        window = NS(safeAreaInsets=NS(top=82))
        self.enterContext(patch.object(self.app.main_window._impl,'native',window,create=True))
        self.edge = self.enterContext(patch('mobile.ios_toolbar.vertical_edge',return_value=0))
        self.enterContext(patch('mobile.ios_toolbar.system_occlusions',return_value=((535,0,134,82),)))
        def mount(view,controller,title):view._document_title_view=object()
        self.mount = self.enterContext(patch('mobile.document_location.mount_apple_title',side_effect=mount))
        self.clear = self.enterContext(patch('mobile.ios_toolbar.clear_actions'))
        def leading(controller,buttons,**kwargs):
            for button in buttons:
                button._ios_action_item=object()
        self.leading = self.enterContext(patch('mobile.ios_toolbar.mount_leading',side_effect=leading))
        self.place = self.enterContext(patch('mobile.document_location.place_title_in_header'))

    def test_all_original_native_controls_title_and_commands_mount_once(self):
        self.assertTrue(band.project(self.app,self.view,'documents',self.controller))
        state = self.view._reader_top_band_state
        row = state['header'].children[0]
        self.assertEqual([child for child in row.children if child in self.buttons], self.buttons)
        self.assertEqual(state['header'].style.height,90)
        self.assertEqual(row.style.margin_right,142)
        self.assertEqual(row.style.margin_top,17)
        self.assertTrue(self.navigation.hidden)
        self.assertIsNone(self.view._native_reader_toolbar.parent)
        self.place.assert_called_once_with(row,self.view._document_title_view,'On-device')
        self.buttons[0].on_press()
        self.assertTrue(band.project(self.app,self.view,'documents',self.controller))
        self.assertIs(self.view._reader_top_band_state,state)
        self.mount.assert_called_once()

    def test_epub_contents_stays_next_to_close_before_title(self):
        import toga
        from toga.style import Pack
        menu = toga.Button('Contents', on_press=Mock(), style=Pack(width=52, height=52))
        self.view._workspace_menu_button = menu
        self.assertTrue(band.project(self.app, self.view, 'documents', self.controller))
        row = self.view._reader_top_band_state['header'].children[0]
        self.assertEqual(list(row.children), [self.buttons[0], menu, row._title_content, *self.buttons[1:]])

    def test_vertical_rotation_and_new_route_restore_owned_header_and_controls(self):
        import toga
        self.assertTrue(band.project(self.app,self.view,'documents',self.controller))
        header = self.view._reader_top_band_state['header']
        self.edge.return_value=2
        self.assertFalse(band.project(self.app,self.view,'documents',self.controller))
        self.assertIsNone(header.parent)
        self.assertIsNone(self.view._reader_top_band_state)
        self.assertTrue(all(button.parent is None for button in self.buttons))
        self.edge.return_value=0
        self.assertTrue(band.project(self.app,self.view,'documents',self.controller))
        band.release_other(self.app,toga.Box())
        self.assertIsNone(self.view._reader_top_band_state)

    def test_existing52pt_menu_is_not_clipped_by_title_factory(self):
        import toga
        from toga.style import Pack
        self.view._workspace_menu_button=toga.Button('Files',style=Pack(width=52,height=52))
        self.place.side_effect=lambda row,*args:setattr(row.style,'height',48)
        self.assertTrue(band.project(self.app,self.view,'documents',self.controller))
        state=self.view._reader_top_band_state
        self.assertEqual(state['geometry']['row_height'],64)
        self.assertEqual(state['header'].children[0].style.height,52)
        self.assertIs(self.view._workspace_menu_button.parent,state['header'].children[0])

    def test_native_owner_bookkeeping_remounts_vertical_and_clears_nonreader_route(self):
        import toga
        from mobile.workspace_navigation import sync_reader_toolbar
        self.app._reader_toolbar_controllers=set()
        self.app._reader_toolbar_projections={13:'old',(13,'leading'):'old'}
        with patch.object(type(self.app.routes),'apple',new_callable=PropertyMock,return_value=True), patch.object(self.app,'refresh_reader_exit'), \
                patch('mobile.ios_toolbar.mount_actions') as trailing, \
                patch('mobile.ios_toolbar.action_state',return_value=('native-buttons',)):
            sync_reader_toolbar(self.app,self.view,'documents')
            self.assertIs(self.app._reader_toolbar_controller,self.controller)
            self.assertIs(self.app._reader_title_controller,self.controller)
            self.assertIn(13,self.app._reader_toolbar_controllers)
            self.assertNotIn(13,self.app._reader_toolbar_projections)
            self.assertEqual(self.controller.navigationItem.title,'Retained notebook')
            sync_reader_toolbar(self.app,self.view,'documents')
            self.clear.assert_called_once()
            self.edge.return_value=2
            sync_reader_toolbar(self.app,self.view,'documents')
            trailing.assert_called_once()  # Same buttons must remount after header retirement.
            self.assertIsNone(self.view._reader_top_band_state)
            sync_reader_toolbar(self.app,toga.Box(),'documents')
            self.assertNotIn(13,self.app._reader_toolbar_controllers)
            self.assertIsNone(self.app._reader_toolbar_controller)
            self.assertIsNone(self.controller.navigationItem.titleView)
            self.assertNotIn(13,self.app._reader_toolbar_projections)

    def test_real_independent_title_refresh_preserves_active_native_header_owner(self):
        import toga
        from toga.style import Pack
        self.view._workspace_menu_button=toga.Button('Files',style=Pack(width=52,height=52))
        self.assertTrue(band.project(self.app,self.view,'documents',self.controller))
        state=self.view._reader_top_band_state
        header=state['header'];row=header.children[0]
        frame=NS(controls=[header],top_controls=1)
        self.view._reading_frame_owner=frame
        class NativeTitle:
            def __init__(self):self.superview=None
            def removeFromSuperview(self):self.superview=None
        host=NS(bounds=rect(width=240,height=52))
        host.addSubview=lambda title:setattr(title,'superview',host)
        title=NativeTitle()
        self.view._document_storage_status='Updated storage identity'
        self.controller.navigationItem.titleView=object()  # Stale UIKit title ownership must clear.
        with patch.object(row._title_content._impl,'native',host,create=True), \
                patch('mobile.folder_title.storage_title',return_value=title), \
                patch('mobile.document_location.place_title_in_header',wraps=refresh_title_in_header):
            refresh_native_title(self.view,self.controller,'Updated native title')
        self.assertIs(header.parent,self.view)
        self.assertIs(self.view._document_title_header,header)
        self.assertEqual(frame.controls,[header])
        self.assertEqual(frame.top_controls,1)
        self.assertIsNone(self.controller.navigationItem.titleView)
        self.assertIs(title.superview,host)
        self.assertEqual(row.style.height,52)
        self.assertIs(self.view._reader_top_band_state,state)
        self.assertTrue(all(button.parent is row for button in state['buttons']))

    def test_identical_signature_on_new_controller_rebuilds_native_owner(self):
        self.assertTrue(band.project(self.app,self.view,'documents',self.controller))
        previous=self.view._reader_top_band_state
        controller=NS(ptr=NS(value=99),view=self.controller.view,navigationItem=NS(title='Retained notebook',titleView=None))
        self.assertTrue(band.project(self.app,self.view,'documents',controller))
        self.assertIsNot(self.view._reader_top_band_state,previous)
        self.assertIs(self.view._reader_top_band_state['controller'],controller)
        self.assertIsNone(previous['header'].parent)
        self.assertEqual(self.mount.call_count,2)

    def test_fullscreen_and_actionable_error_keep_existing_native_owner(self):
        self.assertTrue(band.project(self.app,self.view,'documents',self.controller))
        self.view._reader_fullscreen=True
        self.assertFalse(band.project(self.app,self.view,'documents',self.controller))
        self.view._reader_fullscreen=False
        self.view._native_reader_status=NS(text='Save failed: retained error')
        self.assertFalse(band.project(self.app,self.view,'documents',self.controller))
        self.assertIsNone(self.view._reader_top_band_state)


class NotebookClearanceTests(unittest.TestCase):
    def test_verified_column_and_all_state_clearance(self):
        regions=((535,0,134,82),)
        geometry=band.free_top_band(regions,669,82,316)
        value=band.notebook_geometry(geometry,regions,band.NOTEBOOK_TOOLBAR_CLEARANCE)
        self.assertEqual(value['reserve'],71)
        self.assertGreaterEqual(value['reserve']+value['content_clearance'],geometry['reserve'])
        detached=regions+((535,100,134,30),)
        full=band.free_top_band(detached,669,82,316)
        self.assertEqual(band.notebook_geometry(full,detached,band.NOTEBOOK_TOOLBAR_CLEARANCE)['reserve'],90)

    def test_ambiguous_width_offset_margins_and_detached_center_decline(self):
        regions=((316,0,134,82),)
        geometry=band.free_top_band(regions,450,82,316)
        self.assertIsNone(band.notebook_geometry(geometry,regions,band.NOTEBOOK_TOOLBAR_CLEARANCE))
        regions=((535,0,134,82),)
        geometry=band.free_top_band(regions,669,82,316)
        for kwargs in ({'contract':None},{'origin_x':2},{'margins':(1,0,0)}):
            args=dict(contract=band.NOTEBOOK_TOOLBAR_CLEARANCE);args.update(kwargs)
            self.assertIsNone(band.notebook_geometry(geometry,regions,**args))
        self.assertIsNone(band.notebook_geometry(geometry,regions+((300,100,40,30),),band.NOTEBOOK_TOOLBAR_CLEARANCE))


class NotebookNativeProjectionTests(NativeBandOwnershipTests):
    def test_compacts_only_after_current_canvas_readiness_and_retirement_invalidates(self):
        self.view._notebook_dom_toolbar_contract=band.NOTEBOOK_TOOLBAR_CLEARANCE
        band.project(self.app,self.view,'documents',self.controller)
        first=self.view._reader_top_band_state
        token=first['notebook_candidate']
        self.assertIsNotNone(token)
        self.assertEqual(first['header'].style.height,90)
        self.view._notebook_dom_ready=token
        band.project(self.app,self.view,'documents',self.controller)
        self.assertEqual(self.view._reader_top_band_state['header'].style.height,71)
        self.assertEqual(self.view._reader_top_band_state['buttons'],self.buttons)
        band.restore(self.view)
        self.assertIsNone(self.view._notebook_dom_ready)
        band.project(self.app,self.view,'documents',self.controller)
        self.assertEqual(self.view._reader_top_band_state['header'].style.height,90)
        self.assertNotEqual(token,self.view._reader_top_band_state['notebook_candidate'])
