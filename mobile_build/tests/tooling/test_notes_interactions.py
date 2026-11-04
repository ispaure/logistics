"""Native acceptance must observe completed copies and validate their contents."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from mobile_build.native_tests.tests.logisticsmobile.notes_interactions import NotesInteractionChecks

TEST_STAGE = TestStage.REGRESSION


class CopyAcceptanceTests(IsolatedAsyncioTestCase):
    async def test_queued_menu_copy_is_awaited_even_before_busy_is_set(self):
        checks = NotesInteractionChecks()
        checks.cloud_busy = False
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'Source.md').write_bytes(b'Original\r\n')
            provider = LocalFiles(root)
            async def publish():
                await asyncio.sleep(.1)
                (root / 'Target.md').write_bytes(b'Original\r\n')
            task = asyncio.create_task(publish())
            try:
                await checks.check_copy_contents(provider, 'Source.md', 'Target.md', directory=False)
                self.assertTrue(task.done())
            finally:
                await task

    async def test_existing_file_or_folder_is_not_enough_when_contents_differ(self):
        checks = NotesInteractionChecks()
        checks.cloud_busy = False
        with TemporaryDirectory() as folder:
            root = Path(folder)
            provider = LocalFiles(root)
            for directory in (False, True):
                with self.subTest(directory=directory):
                    source, target = ('Source', 'Target') if directory else ('Source.md', 'Target.md')
                    original, copied = root / source, root / target
                    if directory:
                        original.mkdir()
                        copied.mkdir()
                        original, copied = original / 'Child.md', copied / 'Child.md'
                    original.write_bytes(b'Original')
                    copied.write_bytes(b'Incorrect')
                    with self.assertRaisesRegex(AssertionError, 'contents differ'):
                        await checks.check_copy_contents(provider, source, target, directory=directory)
                    copied.write_bytes(original.read_bytes())
                    await checks.check_copy_contents(provider, source, target, directory=directory)
