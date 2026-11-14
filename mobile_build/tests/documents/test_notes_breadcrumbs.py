"""Breadcrumb allocation and deferred native scrolling regressions."""
from collections import deque
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import toga
from toga.style import Pack
from toga.style.pack import ROW
from travertino.size import at_least

from commonUtils.testing.stages import TestStage
from features.notes_library.mobile.breadcrumbs import BreadcrumbScroll
from mobile_build.tests.support import notes as fixtures

TEST_STAGE = TestStage.REGRESSION


class Scheduler:
    def __init__(self):
        self.pending = deque()

    def call_soon(self, callback, *args):
        handle = SimpleNamespace(cancelled=False)
        handle.cancel = lambda: setattr(handle, 'cancelled', True)
        self.pending.append((handle, callback, args))
        return handle

    def call_later(self, delay, callback, *args):
        return self.call_soon(callback, *args)

    def step(self):
        handle, callback, args = self.pending.popleft()
        if not handle.cancelled:
            callback(*args)


class BreadcrumbTests(unittest.TestCase):
    setUp = fixtures.set_up_vault

    def scroll(self):
        return BreadcrumbScroll(content=toga.Box(), horizontal=True, vertical=False,
                                style=Pack(flex=1, height=44))

    def test_four_controls_and_path_fit_a_320_point_row(self):
        scroll = self.scroll()
        # Model the intrinsic hint installed by the native Toga backends, which
        # the dummy backend does not supply itself.
        scroll.intrinsic.width = at_least(scroll._MIN_WIDTH)
        scroll.intrinsic.height = at_least(scroll._MIN_HEIGHT)
        buttons = [toga.Button(str(i), style=Pack(width=48, height=44)) for i in range(4)]
        row = toga.Box(children=[*buttons[:2], scroll, *buttons[2:]],
                       style=Pack(direction=ROW, gap=4, margin_left=8, margin_right=8))
        row._impl.container = SimpleNamespace(width=320, height=44, refreshed=lambda: None)
        scroll.intrinsic.width = at_least(toga.ScrollContainer._MIN_WIDTH)
        row.refresh()
        self.assertGreater(row.layout.width, 320)
        scroll.intrinsic.width = at_least(scroll._MIN_WIDTH)
        row.refresh()
        self.assertLessEqual(row.layout.width, 320)
        self.assertLessEqual(buttons[-1].layout.absolute_content_right, 320)
        self.assertGreater(scroll.layout.width, 0)

    def test_scroll_waits_for_native_geometry_and_then_preserves_manual_position(self):
        scroll, loop = self.scroll(), Scheduler()
        with patch.object(scroll, '_layout_ready', side_effect=[False, False, True]):
            scroll.reveal_end(loop, valid=lambda: True)
            loop.step()
            self.assertEqual(scroll.horizontal_position, 0)
            loop.step()
            self.assertEqual(scroll.horizontal_position, 0)
            loop.step()
        self.assertEqual(scroll.horizontal_position, scroll.max_horizontal_position)
        scroll.horizontal_position = 0
        self.assertFalse(loop.pending)
        self.assertEqual(scroll.horizontal_position, 0)
        scroll.retry_end(loop, valid=lambda: True)
        self.assertFalse(loop.pending)

    def test_native_layout_readiness_rejects_stale_content_sizes(self):
        backend = type('Backend', (), {'__module__': 'toga_iOS.widgets.scrollcontainer'})()
        native = SimpleNamespace(bounds=SimpleNamespace(size=SimpleNamespace(width=80)),
                                 contentSize=SimpleNamespace(width=0))
        backend.native = native
        owner = SimpleNamespace(_impl=backend, layout=SimpleNamespace(content_width=80),
            content=SimpleNamespace(layout=SimpleNamespace(width=500)))
        self.assertFalse(BreadcrumbScroll._layout_ready(owner))
        native.contentSize.width = 500
        self.assertTrue(BreadcrumbScroll._layout_ready(owner))
        owner.layout.content_width = 100
        self.assertFalse(BreadcrumbScroll._layout_ready(owner))
        owner.layout.content_width = 80
        native.bounds.size.width = 0
        self.assertFalse(BreadcrumbScroll._layout_ready(owner))

        backend = type('Backend', (), {'__module__': 'toga_android.widgets.scrollcontainer'})()
        backend.native = SimpleNamespace(isLayoutRequested=lambda: False, getWidth=lambda: 160,
            getResources=lambda: SimpleNamespace(getDisplayMetrics=lambda: SimpleNamespace(density=2)))
        backend.native_content = SimpleNamespace(isLayoutRequested=lambda: False, getWidth=lambda: 600)
        owner._impl = backend
        self.assertFalse(BreadcrumbScroll._layout_ready(owner))
        backend.native_content.getWidth = lambda: 1000
        self.assertTrue(BreadcrumbScroll._layout_ready(owner))
        backend.native_content.isLayoutRequested = lambda: True
        self.assertFalse(BreadcrumbScroll._layout_ready(owner))

    def test_new_path_and_disposal_cancel_pending_scroll(self):
        scroll, loop = self.scroll(), Scheduler()
        with patch.object(scroll, '_layout_ready', return_value=False):
            scroll.reveal_end(loop, valid=lambda: True)
            loop.step()
            scroll.reveal_end(loop, valid=lambda: False)
            loop.step()  # Cancelled retry from the old path.
            loop.step()  # Invalid new path.
        self.assertEqual(scroll.horizontal_position, 0)
        scroll.reveal_end(loop, valid=lambda: True)
        scroll.cancel_pending_end()
        loop.step()
        self.assertEqual(scroll.horizontal_position, 0)
        self.assertFalse(loop.pending)

    def test_unmounted_layout_has_a_bounded_retry_lifetime(self):
        scroll, loop = self.scroll(), Scheduler()
        with patch.object(scroll, '_layout_ready', return_value=False):
            scroll.reveal_end(loop, valid=lambda: True)
            for _ in range(61):
                loop.step()
        self.assertFalse(loop.pending)
        self.assertIsNone(scroll._pending_end)
        with patch.object(scroll, '_layout_ready', return_value=True):
            scroll.retry_end(loop, valid=lambda: True)
            loop.step()
        self.assertEqual(scroll.horizontal_position, scroll.max_horizontal_position)
