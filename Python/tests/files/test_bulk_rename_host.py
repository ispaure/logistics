
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from threading import Event
from time import monotonic, sleep
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.filesystem.rename import RenameRules
from desktop import main_window
from desktop.bulk_rename import open_bulk_rename


class BulkRenameHostTests(QtTestCase):
    @classmethod
    def setUpClass(cls): cls.app=qt.QApplication.instance() or qt.QApplication([])

    def wait(self, widget):
        deadline=monotonic()+10
        while widget.progress.busy or widget.preview_timer.isActive() or not widget._items:
            self.app.processEvents(); sleep(.005)
            self.assertLess(monotonic(),deadline)
        self.app.processEvents()

    def test_one_embedded_page_replaces_selection_preserves_rules_and_survives_refresh(self):
        with self.temporary_directory() as folder, patch.object(main_window.registry,'get_pages',return_value=[]):
            first=Path(folder)/'first.txt'; first.write_text('a')
            second=Path(folder)/'second.txt'; second.write_text('b')
            window=main_window.MainWindow()
            rename=open_bulk_rename(paths=[first],parent=window.dlg)
            self.wait(rename)
            rename.controls.fields["prefix"].setText("kept_")
            rename.mask.setText("*.txt")
            rules=rename.controls.rules()
            again=open_bulk_rename(paths=[second],parent=window.dlg)
            self.assertIs(rename,again); self.wait(rename)
            self.assertEqual(rename.selected_paths(),(second.resolve(),))
            self.assertEqual(rename.controls.rules(),rules)
            self.assertEqual(rename.mask.text(),"*.txt")
            self.assertIs(window.tabs.currentWidget(),rename)
            self.assertFalse(rename.isWindow())
            window._sync_feature_pages()
            self.assertEqual(sum(window.tabs.widget(i) is rename for i in range(window.tabs.count())),1)
            # Retire native models while their source directory and Python owner
            # still exist; the outer QtTestCase cleanup runs after this context.
            deadline = monotonic() + 10
            while not window.can_close():
                self.app.processEvents(); sleep(.005)
                self.assertLess(monotonic(), deadline)
            window.dlg.close()
            window.dlg.deleteLater()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            self.app.processEvents()

    def test_latest_selection_wins_during_scan(self):
        from desktop.bulk_rename.widget import BulkRenameWidget
        with self.temporary_directory() as folder:
            a=Path(folder)/'a'; a.write_text('a'); b=Path(folder)/'b'; b.write_text('b')
            entered, release = Event(), Event()
            original = BulkRenameWidget._scan_items
            scans = []

            def delayed(paths, cancelled):
                scans.append(tuple(paths))
                if len(scans) == 1:
                    entered.set()
                    if not release.wait(5):
                        raise TimeoutError('Scan barrier was not released')
                return original(paths, cancelled)

            with patch.object(BulkRenameWidget, '_scan_items', side_effect=delayed):
                widget = BulkRenameWidget(paths=[a])
                try:
                    self.wait_until(entered.is_set)
                    self.assertTrue(widget.progress.busy)
                    widget.set_inputs(paths=[a])
                    widget.set_inputs(paths=[b])
                    self.assertTrue(widget.progress.cancelled.is_set())
                    self.assertFalse(widget.rename_button.isEnabled())
                finally:
                    release.set()
                    self.wait(widget)
                self.assertEqual(widget.selected_paths(), (b.resolve(),))
                self.assertEqual(scans, [(a.absolute(),), (b.absolute(),)])
            deadline = monotonic() + 10
            while not widget.prepare_close():
                self.app.processEvents(); sleep(.005)
                self.assertLess(monotonic(), deadline)
            widget.close()
            widget.deleteLater()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            self.app.processEvents()
