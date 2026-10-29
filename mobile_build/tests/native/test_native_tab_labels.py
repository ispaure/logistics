"""Cold-start contracts distinguish native icon rails from horizontal captions."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace as State
import sys
import unittest
from unittest.mock import Mock, patch

from mobile_build.native_tests.tests.logisticsmobile.navigation_checks import assert_cold_iphone_tab_labels


class NativeTabLabelTests(unittest.TestCase):
    def app(self, *, width=30):
        label_type = object()
        label = State(text='Home', bounds=State(size=State(width=width, height=14)),
            intrinsicContentSize=State(width=30, height=14), font=State(pointSize=12),
            subviews=[], isKindOfClass=lambda cls: cls is label_type)
        view = State(subviews=[label], isKindOfClass=lambda cls: False)
        tab = State(layoutIfNeeded=Mock(), items=[State(title='Home')], window=object(),
            isHidden=lambda: False, bounds=State(size=State(width=69, height=678)))
        controller = State(tabBar=tab, view=view)
        app = State(native_host=State(adapter=State(controller=controller,
            navigation=[State(view=object())]), labels=('Home',)))
        classes = {'UIDevice': State(currentDevice=State(userInterfaceIdiom=0)), 'UILabel': label_type}
        return app, tab, classes

    def check(self, app, classes, *, vertical):
        with patch.dict(sys.modules, {'rubicon.objc': State(ObjCClass=classes.__getitem__)}), \
                patch('mobile.ios_toolbar.vertical_edge', return_value=2 if vertical else 0):
            assert_cold_iphone_tab_labels(app)

    def test_vertical_rail_uses_native_items_instead_of_zero_sized_legacy_captions(self):
        app, _, classes = self.app(width=0)
        self.check(app, classes, vertical=True)

    def test_vertical_rail_must_be_mounted_and_have_the_correct_items(self):
        app, tab, classes = self.app(width=0)
        tab.window = None
        with self.assertRaisesRegex(AssertionError, 'not mounted'):
            self.check(app, classes, vertical=True)
        tab.window = object()
        tab.items = [State(title='Wrong destination')]
        with self.assertRaisesRegex(AssertionError, 'Missing native tab items'):
            self.check(app, classes, vertical=True)

    def test_horizontal_captions_still_reject_truncation(self):
        app, _, classes = self.app(width=0)
        with self.assertRaisesRegex(AssertionError, 'Truncated tab'):
            self.check(app, classes, vertical=False)

    def test_fully_laid_out_horizontal_captions_pass(self):
        app, _, classes = self.app()
        self.check(app, classes, vertical=False)
