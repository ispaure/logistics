"""Exercise the native acceptance fixture before spending a disposable build."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from base64 import b64encode
import inspect
from io import BytesIO
import os
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
            self.enterContext(patch.dict(os.environ, {'TOGA_DUMMY_HOME': directory}))
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
                from mobile.file_browser_view import LocalFileBrowser
                # The dummy list has no native viewport. Admit the mounted rows
                # through the same viewport scheduler that the real probe uses.
                def visible_rows(browser):
                    return range(len(browser.native_list.data))

                def decode_file(action, *, fd, width, height):
                    from PIL import Image
                    self.assertEqual(action, 'file_thumbnail')
                    with os.fdopen(os.dup(fd), 'rb') as stream, Image.open(stream) as image:
                        image.thumbnail((width, height))
                        result = BytesIO()
                        image.save(result, format='PNG')
                    return {'data': b64encode(result.getvalue()).decode('ascii')}

                # Swap the unavailable native decoder for a real host decoder;
                # provider reads, corrupt-file handling and publication stay real.
                with patch.object(fixture, 'rotate', new=AsyncMock()), \
                        patch.object(LocalFileBrowser, '_visible_rows', visible_rows), \
                        patch('mobile.browser_preview.local_image_bridge') as bridge:
                    bridge.return_value.request.side_effect = decode_file
                    app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                close_loop(app.loop)
