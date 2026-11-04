"""Exercise the native acceptance fixture before spending a disposable build."""
import asyncio
import inspect
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage
from mobile.app import LogisticsMobile
from mobile_build.native_tests.tests.logisticsmobile import links_images_voices_probe as fixture

TEST_STAGE = TestStage.REGRESSION


class HostProbe(fixture.LinksImagesVoicesProbe):
    def startup(self):
        LogisticsMobile.startup(self)

    def on_running(self):
        pass

    async def screenshot(self, name):
        self.screenshots.append(name)

    async def tap(self, button):
        result = button.on_press()
        if inspect.isawaitable(result):
            await result
        await asyncio.sleep(0)


class FeedbackProbeTests(unittest.TestCase):
    def test_fixture_runs_all_three_tasks_without_overriding_navigation_guard(self):
        from unittest.mock import AsyncMock, patch
        self.assertIs(HostProbe.checkpoint, LogisticsMobile.checkpoint)
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = HostProbe('Feedback probe fixture', 'io.github.ispaure.logisticsnotebookqa')
            app.screenshots, app.report = [], {}
            async def exercise():
                root = app.private_root / 'FeedbackFixtures'
                root.mkdir()
                await app.links(root)
                await app.images(root)
                await app.voices()
                for task in ('task15', 'task16', 'task17'):
                    self.assertTrue(app.report[task]['success'], app.report)
                self.assertIn('16-information', app.screenshots)
                self.assertIn('17-settings', app.screenshots)
            try:
                with patch.object(fixture, 'rotate', new=AsyncMock()):
                    app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                close_loop(app.loop)
