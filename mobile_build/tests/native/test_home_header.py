"""Shared destination headings and native safe-area placement."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-Andre Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock

import toga
from toga.style import Pack
from toga.style.pack import NONE
from commonUtils.testing.stages import TestStage

from mobile.destination_actions import align_title, compact_content_top, duo_heading_geometry, prepare
from mobile.fold_layout import Division
from mobile.ios_destination_rail import clear_landscape_gutters, uses_leading_rail

TEST_STAGE = TestStage.REGRESSION


class HomeHeaderTests(TestCase):
    def test_duo_header_uses_the_free_column_with_a_taller_island(self):
        for height in (120, 260, 430):
            regions = ((867, 0, 84, height),)
            self.assertEqual(duo_heading_geometry(regions, 24, 0, 867, 304, vertical=True),
                             (0, 867, 8, 60))
        regions = ((867, 0, 84, 120), (610, 4, 257, 60))
        fold = Division(468, 0, 12, 669)
        self.assertEqual(duo_heading_geometry(regions, 24, 0, 867, 304, vertical=True, fold=fold),
                         (0, 464, 8, 72))
        self.assertIsNone(duo_heading_geometry(((250, 0, 300, 62),), 24, 0, 867, 320,
                                               vertical=True))

    def test_duo_portrait_header_uses_the_strip_beside_status_items(self):
        regions = ((535, 0, 134, 82),)
        self.assertEqual(duo_heading_geometry(regions, 82, 0, 669, 336, vertical=False), (0, 535, 24, 90))
        self.assertIsNone(duo_heading_geometry(((320, 0, 349, 120),), 82, 0, 669, 336, vertical=False))

    def test_centered_title_clamps_to_available_space_and_restores_portrait(self):
        title = toga.Label('Documents')
        spacer = toga.Box()
        header = toga.Box(children=[title, spacer])
        align_title(header, centered=True, space=(16, 800), center=450)
        self.assertEqual(16 + title.style.margin_left + title.style.width / 2, 450)
        align_title(header, centered=True, space=(16, 430), center=450)
        self.assertEqual(16 + title.style.margin_left + title.style.width, 430)
        align_title(header, centered=False)
        self.assertEqual((title.style.text_align, title.style.width, title.style.margin_left,
                          title.style.flex, spacer.style.width, spacer.style.flex),
                         ('left', NONE, 0, 1, 0, 0))

    def test_documents_retains_actions_and_finishes_with_conditional_unlock(self):
        app = NS(routes=NS(apple=True), show_home_unlock=Mock(), new_hub_document=Mock(),
                 open_document_search=Mock(), home_unlock_candidates=Mock(return_value=['fixture']),
                 adaptive=NS(browsers={}), hub_controller=lambda: NS())
        view = prepare(app, toga.Box(), 'documents')
        header, (unlock, new, search) = view._destination_actions
        self.assertEqual(header.children[0].text, 'Documents')
        self.assertEqual(view._ios_toolbar_buttons(), [new, search, unlock])
        app.home_unlock_candidates.return_value = []
        self.assertEqual(view._ios_toolbar_buttons(), [new, search])

    def test_workspaces_shares_one_row_for_title_search_and_transfers(self):
        transfer = toga.Button('Transfers', style=Pack(width=48))
        app = NS(routes=NS(apple=False), show_home_unlock=Mock(), folder_source='Local',
                 feature_enabled=Mock(return_value=True), folder_transfers_button=transfer,
                 folder_view_toggle=toga.Button('Hierarchy'),
                 home_unlock_candidates=Mock(return_value=[]),
                 main_window=NS(size=NS(width=390, height=840)))
        view = toga.Box()
        view._workspaces_source_row = toga.Box()
        prepare(app, view, 'files')
        header, _ = view._destination_actions
        self.assertEqual(header.children[0].text, 'Workspaces')
        self.assertEqual(header.children[0].style.text_align, 'center')
        self.assertEqual(list(header.children)[2:], [view._workspace_search, app.folder_view_toggle, transfer])

    def test_iphone_landscape_rail_keeps_system_navigation_on_other_poses(self):
        self.assertTrue(uses_leading_rail(phone=True, duo=False, landscape=True, native_edge=0))
        self.assertFalse(uses_leading_rail(phone=True, duo=False, landscape=False, native_edge=0))
        self.assertFalse(uses_leading_rail(phone=True, duo=True, landscape=True, native_edge=2))
        self.assertFalse(uses_leading_rail(phone=False, duo=False, landscape=True, native_edge=0))

    def test_landscape_gutter_release_follows_sensor_and_system_regions(self):
        self.assertEqual(clear_landscape_gutters(874, 62, 62, 0, ()), (0, 62))
        self.assertEqual(clear_landscape_gutters(874, 62, 62, 874, ()), (62, 0))
        self.assertEqual(clear_landscape_gutters(874, 62, 62, 874, ((0, 0, 100, 44),)), (0, 0))
        self.assertEqual(clear_landscape_gutters(874, 62, 10, 0, ()), (0, 0))
        self.assertEqual(clear_landscape_gutters(874, 62, 62, 437, ()), (0, 0))

    def test_duo_root_clears_the_safe_area_once_through_tab_and_route_wrappers(self):
        header = toga.Box()
        header._destination_top_band = True
        page = toga.Box(children=[header, toga.Box()])
        tab = toga.Box(children=[toga.Box(children=[page])])
        window = object()
        native = NS(window=window, bounds=object(), convertRect=lambda *a, **k: NS(origin=NS(y=0)))
        container = NS(content=NS(interface=tab), native=native, top_inset=82)
        self.assertTrue(compact_content_top(container))
        self.assertEqual(container.top_inset, 0)
        page.remove(header)
        container.top_inset = 82
        self.assertFalse(compact_content_top(container))
        self.assertEqual(container.top_inset, 82)
