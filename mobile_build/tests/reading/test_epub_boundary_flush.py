"""A real reading-position write cannot discard the user's next chapter action."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch
from commonUtils.runtime.resources.documents import LocalDocuments
from mobile.app import LogisticsMobile
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books


class EpubBoundaryFlushTests(unittest.TestCase):
    def test_next_arriving_during_position_write_runs_after_flush(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root / 'app'
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            release = Event()
            try:
                epub, _ = make_books(root)
                record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)
                async def exercise():
                    await app.open_book(record['id'])
                    owner = app.readers.active
                    started = asyncio.Event()
                    original = owner.library_store.progress
                    def delayed(*args, **kwargs):
                        app.loop.call_soon_threadsafe(started.set)
                        if not release.wait(5):
                            raise TimeoutError('Synthetic position write did not release')
                        return original(*args, **kwargs)
                    with patch.object(owner.library_store, 'progress', side_effect=delayed):
                        owner.epub_event(owner.book_reader, owner.book_epoch, 0, 'position', 5)
                        owner.request_position_flush()
                        await asyncio.wait_for(started.wait(), 2)
                        self.assertTrue(owner.book_busy)
                        owner.epub_event(owner.book_reader, owner.book_epoch, 0, 'next', 5)
                        await asyncio.sleep(0)
                        self.assertEqual(owner.book_record['position'], 0)
                        release.set()
                        await owner._epub_location_task
                        for _ in range(200):
                            if owner.book_record['position'] == 1 and not owner.book_busy:
                                break
                            await asyncio.sleep(.01)
                        self.assertEqual(owner.book_record['position'], 1)
                        self.assertFalse(owner.book_busy)
                    await app.reader_manager().catalog.wait_for_refresh()
                    app.readers.close(owner.session.id)
                app.loop.run_until_complete(exercise())
            finally:
                release.set()
                app.main_window.close()
                app.loop.close()
                LogisticsMobile.storage_root = None
