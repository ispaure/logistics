"""Host fixture storage and loops survive nesting and failed construction safely."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.SMOKE
import unittest
import asyncio
import shutil
from unittest.mock import patch

from mobile.app import LogisticsMobile
from mobile_build.tests.support.app import mobile_app


class MobileAppFixtureTests(unittest.TestCase):
    def test_nested_scopes_restore_previous_storage_and_close_only_their_loop(self):
        previous = LogisticsMobile.storage_root
        with mobile_app() as outer:
            outer_root = outer.storage_root
            self.assertTrue(outer_root.exists())
            with mobile_app() as inner:
                inner_root = inner.storage_root
                self.assertNotEqual(inner_root, outer_root)
                self.assertFalse(outer.loop.is_closed())
            self.assertTrue(inner.loop.is_closed())
            self.assertIs(asyncio.get_event_loop(), outer.loop)
            self.assertIs(LogisticsMobile.storage_root, outer_root)
            self.assertFalse(inner_root.exists())
        self.assertTrue(outer.loop.is_closed())
        self.assertFalse(outer_root.exists())
        self.assertIs(LogisticsMobile.storage_root, previous)

    def test_failed_construction_restores_storage(self):
        previous = LogisticsMobile.storage_root
        with patch('mobile_build.tests.support.app.LogisticsMobile', wraps=LogisticsMobile) as factory:
            factory.side_effect = RuntimeError('construction failed')
            factory.storage_root = previous
            with self.assertRaisesRegex(RuntimeError, 'construction failed'):
                with mobile_app():
                    self.fail('A failed app must never be yielded')
            self.assertIs(factory.storage_root, previous)

    def test_startup_failure_retires_a_loop_allocated_inside_the_backend(self):
        from toga_dummy.app import App
        original = App.__init__
        loops = []
        def observed(impl, interface):
            try:
                original(impl, interface)
            finally:
                if hasattr(impl, 'loop'):
                    loops.append(impl.loop)
        with patch.object(App, '__init__', observed), \
                patch.object(LogisticsMobile, 'startup', side_effect=RuntimeError('startup failed')):
            with self.assertRaisesRegex(RuntimeError, 'startup failed'):
                with mobile_app():
                    self.fail('Startup must fail')
        self.assertTrue(loops)
        self.assertTrue(all(loop.is_closed() for loop in loops))

    def test_failed_drain_retains_root_and_reports_its_location(self):
        from commonUtils.testing.event_loop import close_loop
        loops = []
        def cannot_close(loop):
            loops.append(loop)
            raise AssertionError('worker still alive')
        try:
            with patch('mobile_build.tests.support.app.close_loop', side_effect=cannot_close):
                with self.assertRaisesRegex(AssertionError, 'worker still alive') as caught:
                    with mobile_app() as app:
                        root = app.storage_root
            self.assertTrue(root.is_dir())
            self.assertTrue(any(str(root) in note for note in caught.exception.__notes__))
        finally:
            for loop in loops:
                close_loop(loop)
            if 'root' in locals():
                shutil.rmtree(root)
