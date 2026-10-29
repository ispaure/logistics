"""Fullscreen centering compares screen positions using the actual window origin."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
from mobile_build.native_tests.tests.logisticsmobile.reader_checks import _assert_comic_centered


class NativeComicGeometryTests(unittest.TestCase):
    def check(self, origin, *, offset=(0, 0), cutout=0):
        bars = NS(left=0, top=cutout, right=0, bottom=0)
        width, height = 1000, 2000 - cutout
        def position(target, x, y):
            target[0], target[1] = x, y
        decor = NS(getWidth=lambda: 1000, getHeight=lambda: 2000,
                   getLocationOnScreen=lambda target: position(target, *origin),
                   getRootWindowInsets=lambda: NS(getInsets=lambda kind: bars))
        native = NS(getWidth=lambda: width, getHeight=lambda: height,
                    getDrawable=lambda: NS(getIntrinsicWidth=lambda: width, getIntrinsicHeight=lambda: height),
                    getImageMatrix=lambda: NS(mapRect=lambda rect: None),
                    getLocationOnScreen=lambda target: position(target,
                        origin[0] + offset[0], origin[1] + cutout + offset[1]))
        classes = {'android.graphics.RectF': lambda *args: NS(centerX=lambda: width / 2, centerY=lambda: height / 2),
                   'android.view.WindowInsets$Type': NS(systemBars=lambda: 1, displayCutout=lambda: 2)}
        java = NS(jclass=classes.__getitem__, jarray=lambda kind: lambda length: [0] * length, jint=int)
        view = NS(_impl=NS(native=native, _native_activity=NS(
            getWindow=lambda: NS(getDecorView=lambda: decor))))
        with patch.dict('sys.modules', java=java):
            _assert_comic_centered(view, fullscreen=True)

    def test_window_origins_are_not_assumed_to_be_display_origin(self):
        for origin in ((0, 0), (0, 142), (30, -20)):
            with self.subTest(origin=origin):
                self.check(origin)

    def test_safe_cutout_is_applied_inside_the_window(self):
        self.check((0, 142), cutout=34)

    def test_real_vertical_and_horizontal_displacement_still_fails(self):
        for offset in ((0, 6), (6, 0)):
            with self.subTest(offset=offset), self.assertRaises(AssertionError):
                self.check((20, 142), offset=offset)
