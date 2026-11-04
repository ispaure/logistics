"""Content columns avoid system clusters without borrowing their side-rail height."""
from types import SimpleNamespace as NS
import sys
import unittest
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from mobile.reader_edges import apple_reader_top, compact_apple_reader

TEST_STAGE = TestStage.REGRESSION


def rect(x, y, width, height):
    return NS(origin=NS(x=x, y=y), size=NS(width=width, height=height))


class ReaderTopClearanceTests(unittest.TestCase):
    def clearance(self, regions, *, width=951, height=669, top=102, left=0, right=84,
                  origin_y=0, supported=True):
        window=NS(safeAreaInsets=NS(top=top))
        native=NS(bounds=rect(0,0,width,height),
                  convertRect=lambda *a,**kw:rect(0,origin_y,width,height),
                  respondsToSelector=lambda selector:supported)
        container=NS(native=native,left_inset=left,right_inset=right)
        with patch.dict(sys.modules, {'rubicon.objc':NS(SEL=lambda selector:selector)}), patch(
                'mobile.ios_reader_chrome.occlusion_geometry',return_value=regions):
            return apple_reader_top(container,window)

    def test_side_cluster_does_not_spend_a_row_across_the_content(self):
        for width,height in ((951,669),(854,600),(669,951)):
            for leading in (False,True):
                with self.subTest(size=(width,height),leading=leading):
                    self.assertEqual(self.clearance(((0 if leading else width-84,0,84,102),),
                        width=width,height=height,left=84 if leading else 0,
                        right=0 if leading else 84),0)

    def test_camera_or_activity_over_the_content_still_reserves_its_height(self):
        self.assertEqual(self.clearance(((400,0,100,102),)),110)
        self.assertEqual(self.clearance(((400,0,100,22),),top=62),62)
        self.assertEqual(self.clearance(((867,0,84,102),(400,0,100,22)),top=62),62)
        self.assertEqual(self.clearance(((400,0,100,30),(400,45,100,60))),113)
        self.assertEqual(self.clearance(((400,-50,100,72),),top=24),30)

    def test_unsupported_or_unreported_geometry_keeps_hardware_fallback(self):
        self.assertEqual(self.clearance((),top=24),24)
        self.assertEqual(self.clearance(((867,0,84,102),),top=24,supported=False),24)
        self.assertEqual(self.clearance(((867,300,84,100),),top=24),24)
        self.assertEqual(self.clearance((),top=24,origin_y=12),12)

    def test_region_coordinates_are_local_to_an_already_offset_pane(self):
        self.assertEqual(self.clearance(((400,-100,100,62),),top=62,origin_y=100),0)
        self.assertEqual(self.clearance(((867,-12,84,114),),origin_y=12),0)

    def test_rotation_between_side_and_horizontal_bars_restores_each_allocation(self):
        window=NS(safeAreaInsets=NS(top=102,bottom=0))
        native=NS(window=window,bounds=rect(0,0,951,669),
                  safeAreaInsets=NS(bottom=0),respondsToSelector=lambda selector:True,
                  convertRect=lambda *a,**kw:rect(0,0,951,669))
        container=NS(native=native,top_inset=102,bottom_inset=0,left_inset=0,right_inset=84)
        reader=NS(children=[])
        reader._document_title_header=NS(parent=reader)
        container.content=NS(interface=NS(app=NS(),children=[reader]))
        # These are native bar/allocation variants, not device-name switches.
        cases=(('open landscape trailing',2,102,0,84,((867,0,84,102),),0),
               ('open portrait horizontal',0,116,0,0,(),116),
               ('closed phone portrait',0,116,0,0,(),116),
               ('phone landscape',0,78,62,62,(),78),
               ('tablet horizontal',0,74,0,0,(),74),
               ('split window leading',1,102,84,0,((0,0,84,102),),0),
               ('side bar unreported regions',2,102,0,84,(),102))
        with patch.dict(sys.modules, {'rubicon.objc':NS(SEL=lambda selector:selector)}), patch(
                'mobile.appearance.reserve_navigation'), patch(
                'mobile.ios_toolbar.vertical_edge') as edge, patch(
                'mobile.ios_reader_chrome.occlusion_geometry') as regions:
            for name,bar,top,left,right,occlusions,expected in cases:
                with self.subTest(allocation=name):
                    edge.return_value=bar
                    regions.return_value=occlusions
                    # The platform layout refresh supplies today's native insets.
                    container.top_inset=top
                    container.left_inset,container.right_inset=left,right
                    compact_apple_reader(container)
                    self.assertEqual(container.top_inset,expected)
