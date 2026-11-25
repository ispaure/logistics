"""The application participant owns queued work without any browser window."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
import sqlite3
from unittest.mock import patch

from commonUtils.filesystem.index import DirectoryCache
from commonUtils.runtime.operations import OperationCancelled, check_cancelled
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.status import IndexProgress
from services.folders.ui.indexing import IndexService


class IndexServiceTests(QtTestCase):
    def test_refresh_runs_ahead_of_an_automatic_scan_of_the_same_folder(self):
        with self.temporary_directory() as temporary:
            base = Path(temporary)
            root = base / 'files'
            root.mkdir()
            nested = root / 'nested'
            nested.mkdir()
            target = nested / 'new.txt'
            automatic_started, allow_yield, stop_following = Event(), Event(), Event()
            original = DirectoryCache.reconcile_folder

            def reconcile(cache, folder, **options):
                if not options['full'] and not automatic_started.is_set():
                    automatic_started.set()
                    if not allow_yield.wait(10):
                        raise TimeoutError('Automatic scan was not released')
                    while not options['cancelled']():
                        sleep(.01)
                    check_cancelled(options['cancelled'])
                return original(cache, folder, **options)

            with (DirectoryCache(database=base / 'cache' / 'index.sqlite3') as cache,
                  patch('services.folders.ui.indexing.directory_cache', cache),
                  patch.object(DirectoryCache, 'reconcile_folder', reconcile)):
                service = IndexService()
                coordinator = service.coordinator
                automatic = coordinator.submit(root)
                service.start()
                try:
                    self.wait_until(automatic_started.is_set)
                    target.write_text('added after automatic indexing began')
                    refresh = coordinator.submit(root, full=True)
                    self.assertNotEqual(refresh, automatic)
                    progress = IndexProgress()

                    def report(done, total, message):
                        if message != 'Following shared index':
                            progress.update(done, message)
                            stop_following.set()

                    with self.assertRaises(OperationCancelled):
                        coordinator.follow(refresh, root, cancelled=stop_following.is_set, report=report)
                    self.assertIn('Queued for indexing', progress.render())

                    allow_yield.set()
                    deadline = monotonic() + 10
                    with coordinator.follow(refresh, root, cancelled=lambda: monotonic() >= deadline) as snapshot:
                        self.assertIsNotNone(snapshot.entry(target))
                finally:
                    allow_yield.set()
                    service.stop()

    def test_queued_work_runs_without_browsers_and_stops_cleanly(self):
        app = qt.QApplication.instance() or qt.QApplication([])
        with TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base/'files'
            root.mkdir()
            (root/'example.txt').write_text('example')
            with DirectoryCache(database=base/'cache'/'index.sqlite3') as cache:
                with patch('services.folders.ui.indexing.directory_cache', cache):
                    service = IndexService()
                    identity = service.coordinator.submit(root, background_priority=False)
                    activity = []
                    service.activity.connect(activity.append)
                    service.start()
                    try:
                        deadline = monotonic()+10
                        while True:
                            self.assertLess(monotonic(), deadline)
                            try:
                                if service.coordinator.status(identity)['state'] == 'done':
                                    break
                            except sqlite3.OperationalError as error:
                                # Receipt reads can contend with the writer on Windows.
                                # Keep the existing deadline and pump Qt between retries.
                                if not any(word in str(error) for word in ('locked', 'busy')):
                                    raise
                            app.processEvents()
                            sleep(.02)
                        self.assertTrue(service.worker.isRunning())
                        with cache.peek(root) as snapshot:
                            self.assertTrue(snapshot.complete)
                    finally:
                        service.stop()
                    app.processEvents()
                    self.assertTrue(activity)
                    self.assertFalse(service.worker.isRunning())
                    self.assertIsNone(cache.coordinator)
                    self.assertIsNone(cache.shared_activity)
