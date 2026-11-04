"""Native folder work coalesces style changes and bounds scheduling overhead."""
import asyncio
from collections import Counter
import unittest
from unittest.mock import patch

from commonUtils.testing.stages import TestStage
from mobile import appearance
from mobile.obsidian import open_vault
from mobile_build.tests.documents import test_obsidian as fixtures

TEST_STAGE = TestStage.REGRESSION


class FolderRenderingTests(unittest.TestCase):
    setUp = fixtures.ObsidianTests.setUp
    tearDown = fixtures.ObsidianTests.tearDown
    run_async = fixtures.ObsidianTests.run_async

    async def library(self):
        folder = self.vault / 'Many'
        folder.mkdir()
        for index in range(40):
            (folder / f'Note {index}.md').write_text('# Fixture')
        return await open_vault(self.app, self.provider, 'Vault', 'documents')

    def test_new_folder_controls_paint_only_their_final_surface_style(self):
        async def exercise():
            owner = await self.library()
            painter = appearance._surface_painter
            paint = painter.paint
            painted = []
            def record(impl, style):
                if painter.pending.get() is None:
                    painted.append(impl)
                return paint(impl, style)
            with patch.object(painter, 'paint', side_effect=record):
                await owner.toggle_folder('Vault/Many')
            self.assertGreater(len(painted), 40)
            self.assertEqual(max(Counter(painted).values()), 1)
            owner.dispose()
        self.run_async(exercise())

    def test_cached_native_rows_do_not_require_one_timer_per_row(self):
        async def exercise():
            owner = await self.library()
            await owner.toggle_folder('Vault/Many')
            rows = list(owner.rows.children)
            pauses = []
            sleep = asyncio.sleep
            async def pause(delay):
                pauses.append(delay)
                self.assertEqual(owner.rows.children, rows)
                await sleep(0)
            with patch('commonUtils.ui.native.text_size.native_backend', return_value='toga_android.widgets.box'), \
                 patch('features.notes_library.mobile.notes_library.monotonic', return_value=0), \
                 patch('features.notes_library.mobile.notes_library.asyncio.sleep', side_effect=pause):
                owner.render_tree()
                await owner.tree_task
            self.assertGreater(len(pauses), 0)
            self.assertLessEqual(len(pauses), (len(rows) + 7) // 8)
            self.assertEqual(owner.rows.children, rows)
            owner.dispose()
        self.run_async(exercise())
