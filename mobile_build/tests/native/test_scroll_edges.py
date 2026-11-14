"""Scrolling pages use full viewports without hiding their last touch target."""
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

from toga.style import Pack
from commonUtils.testing.stages import TestStage
from mobile.appearance import reserve_navigation
from mobile.scroll_edges import fill_bottom, sync_bottom

TEST_STAGE = TestStage.REGRESSION


def rect(y, height, width=900):
    return NS(origin=NS(y=y), size=NS(height=height, width=width))


def insets(top=0, left=0, bottom=0, right=0):
    return NS(top=top, left=left, bottom=bottom, right=right)


class ScrollEdgesTests(TestCase):
    def test_ios_scrolls_reclaim_safe_and_floating_bar_space_through_rotation(self):
        native = NS(contentInset=insets(3, 4, 0, 5), verticalScrollIndicatorInsets=insets(6, 7, 0, 8))
        scroll = NS(_impl=NS(native=native))
        impl = type('AppleBox', (), {'__module__': 'toga_iOS.widgets.box'})()
        impl.container = NS(native=NS(bounds=rect(0, 669), convertRect=lambda *a, **kw: rect(0, 669)),
                            top_inset=0, bottom_inset=34)
        view = NS(_impl=impl, style=Pack(margin=12))
        bar = NS(isHidden=lambda: False, bounds=rect(204, 440, 52),
                 convertRect=lambda *a, **kw: bar.bounds)
        app = NS(native_host=NS(adapter=NS(navigation=[], controller=NS(tabBar=bar))),
                 routes=NS(body=lambda: NS(children=[view])),
                 main_window=NS(_impl=NS(native=NS(bounds=rect(0, 669), safeAreaInsets=insets(bottom=34)))))
        with patch.dict('sys.modules', {'rubicon.objc': NS(UIEdgeInsets=insets)}):
            fill_bottom(view, scroll)
            for safe, bar_frame, expected_padding in ((34, rect(204, 440, 52), 46),
                    (0, rect(204, 440, 52), 46), (83, rect(586, 83), 95),
                    (0, rect(586, 83), 95), (34, rect(204, 440, 52), 46)):
                impl.container.bottom_inset = safe
                bar.bounds = bar_frame
                for _ in range(2):
                    reserve_navigation(app)
                    # Parent safe inset + outer margin no longer clips the viewport.
                    self.assertEqual(safe + view.style.margin_bottom, 0)
                    self.assertEqual(native.contentInset.bottom, expected_padding)
                    self.assertEqual(native.verticalScrollIndicatorInsets.bottom, expected_padding)
            self.assertEqual((native.contentInset.top, native.contentInset.left, native.contentInset.right), (3, 4, 5))
            self.assertEqual(native.contentInsetAdjustmentBehavior, 2)

    def test_expanded_notes_drawer_preserves_last_row_clearance_and_resets_when_closed(self):
        from features.notes_library.mobile.drawers import NotesDrawers
        drawer = NotesDrawers.__new__(NotesDrawers)
        drawer.host = NS(sync_bottom=sync_bottom)
        impl = type('AppleBox', (), {'__module__': 'toga_iOS.widgets.box'})()
        drawer.sidebar = NS(_impl=impl, style=Pack())
        native = NS(contentInset=insets(), verticalScrollIndicatorInsets=insets())
        drawer.set_files_scrolls(NS(_impl=NS(native=native)))
        drawer.expanded = True
        with patch.dict('sys.modules', {'rubicon.objc': NS(UIEdgeInsets=insets)}):
            self.assertTrue(drawer.extend_files_bottom(34))
            self.assertEqual(drawer.sidebar.style.margin_bottom, -34)
            self.assertEqual(native.contentInset.bottom, 46)
            self.assertFalse(drawer.extend_files_bottom(34))
            drawer.expanded = False
            self.assertTrue(drawer.extend_files_bottom(34))
            self.assertEqual(drawer.sidebar.style.margin_bottom, 0)
            self.assertEqual(native.contentInset.bottom, 12)

    def test_android_retains_other_padding_and_places_bottom_space_inside_scroller(self):
        native = Mock()
        native.getPaddingLeft.return_value, native.getPaddingTop.return_value = 8, 6
        native.getPaddingRight.return_value, native.getPaddingBottom.return_value = 10, 0
        scroll = NS(_impl=NS(native=native, scale_in=lambda value: int(value * 2)))
        impl = type('AndroidBox', (), {'__module__': 'toga_android.widgets.box'})()
        view = NS(_impl=impl, style=Pack(margin=12))
        fill_bottom(view, scroll)
        self.assertEqual(view.style.margin_bottom, 0)
        self.assertEqual(view.style.margin_left, 12)
        native.setPadding.assert_called_once_with(8, 6, 10, 24)
        native.setClipToPadding.assert_called_with(False)
        native.getPaddingBottom.return_value = 24
        sync_bottom(view)
        native.setPadding.assert_called_once()

    def test_ordinary_pages_keep_their_existing_clearance(self):
        view = NS(style=Pack(margin=12))
        self.assertFalse(sync_bottom(view, inset=34, overlap=49))
        self.assertEqual(view.style.margin_bottom, 12)
