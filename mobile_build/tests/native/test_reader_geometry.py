"""Fullscreen assertions retain centering and dimensions on notched Android."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace as State
import unittest
from unittest.mock import patch

from mobile_build.native_tests.tests.logisticsmobile.reader_checks import _assert_comic_centered


class ComicSafeGeometryTests(unittest.TestCase):
    def check(self, *, cutout=142, height=2281, offset=0):
        masks=[]
        class Rect:
            def __init__(self,*args):self.x=self.y=0
            def centerX(self):return self.x
            def centerY(self):return self.y
        def mapped(rect):rect.x=540+offset;rect.y=height/2
        types=State(systemBars=lambda:1,displayCutout=lambda:2)
        def insets(mask):
            masks.append(mask)
            return State(left=0,top=cutout if mask&2 else 0,right=0,bottom=0)
        decor=State(getLocationOnScreen=lambda values:values.__setitem__(slice(None),[0,0]),getRootWindowInsets=lambda:State(getInsets=insets),getWidth=lambda:1080,getHeight=lambda:2424)
        native=State(getDrawable=lambda:State(getIntrinsicWidth=lambda:100,getIntrinsicHeight=lambda:100),
            getImageMatrix=lambda:State(mapRect=mapped),getWidth=lambda:1080,getHeight=lambda:height,
            getLocationOnScreen=lambda values:values.__setitem__(slice(None),[0,cutout]))
        activity=State(getWindow=lambda:State(getDecorView=lambda:decor))
        view=State(_impl=State(native=native,_native_activity=activity))
        java=State(jclass=lambda name:Rect if name=='android.graphics.RectF' else types,
                   jarray=lambda kind:lambda size:[0]*size,jint=int)
        with patch.dict('sys.modules',{'java':java}):_assert_comic_centered(view,fullscreen=True)
        return masks

    def test_hidden_bars_retain_camera_cutout_without_losing_centering(self):
        self.assertIn(3,self.check())
        self.check(cutout=0,height=2424)

    def test_real_shrinkage_and_off_center_images_still_fail(self):
        with self.assertRaisesRegex(AssertionError,'loses screen height'):self.check(height=2200)
        with self.assertRaisesRegex(AssertionError,'off center'):self.check(offset=20)
