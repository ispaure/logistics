"""The application participant owns queued work without any browser window."""
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from unittest.mock import patch

from commonUtils.filesystem.index import DirectoryCache
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from services.folders.ui.indexing import IndexService


class IndexServiceTests(QtTestCase):
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
                        while service.coordinator.status(identity)['state'] != 'done':
                            self.assertLess(monotonic(), deadline)
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
