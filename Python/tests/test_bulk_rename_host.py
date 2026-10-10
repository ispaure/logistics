import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.filesystem.rename import RenameRules
from ui_new import main_window
from ui_new.bulk_rename import open_bulk_rename


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
        with TemporaryDirectory() as folder, patch.object(main_window.registry,'get_pages',return_value=[]):
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
            window.dlg.close()

    def test_latest_selection_wins_during_scan(self):
        from ui_new.bulk_rename.widget import BulkRenameWidget
        with TemporaryDirectory() as folder:
            a=Path(folder)/'a'; a.write_text('a'); b=Path(folder)/'b'; b.write_text('b')
            widget=BulkRenameWidget(paths=[a]); self.app.processEvents()
            widget.set_inputs(paths=[a]); widget.set_inputs(paths=[b]); self.wait(widget)
            self.assertEqual(widget.selected_paths(),(b.resolve(),))
