"""Desktop breadcrumb navigation, scroll position and cleared-state safety."""
from types import SimpleNamespace

from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.notes_library.ui.document import BreadcrumbViewport, NotesBreadcrumbs

TEST_STAGE = TestStage.REGRESSION


class NotesBreadcrumbTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.existing = set(self.app.topLevelWidgets())

    def tearDown(self):
        self._release_windows(self.existing)

    def make_path(self):
        opened, revealed = [], []
        owner = SimpleNamespace(library=SimpleNamespace(root=''), library_label='Library',
            folder_pages={}, open_note=opened.append, reveal_folder=revealed.append)
        label = NotesBreadcrumbs(owner)
        font = qt.QFontDatabase.systemFont(qt.QFontDatabase.SystemFont.FixedFont)
        font.setStyleHint(qt.QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        label.setFont(font)
        viewport = owner.breadcrumb_viewport = BreadcrumbViewport(label)
        viewport.setFixedWidth(160)
        viewport.show()
        return owner, label, viewport, opened, revealed

    def test_new_path_with_same_width_reveals_its_end(self):
        _, label, viewport, _, _ = self.make_path()
        label.show_path('Folder/' + 'A' * 64 + '.md')
        bar = viewport.horizontalScrollBar()
        self.wait_until(lambda: bar.maximum() > 0 and bar.value() == bar.maximum())
        previous_maximum = bar.maximum()
        bar.setValue(0)
        label.show_path('Folder/' + 'B' * 64 + '.md')
        self.app.processEvents()
        self.assertEqual(bar.maximum(), previous_maximum)
        self.assertEqual(bar.value(), bar.maximum())

    def test_stale_or_invalid_link_callbacks_are_ignored(self):
        _, label, _, opened, revealed = self.make_path()
        label.show_path('Private/Folder/Note.md')
        label.entries = []
        label.clear()
        for value in ('0', '-1', '999', 'not-an-index'):
            label.activate(value)
        self.assertEqual(opened, [])
        self.assertEqual(revealed, [])

    def test_same_path_refresh_preserves_manual_scrolling(self):
        _, label, viewport, _, _ = self.make_path()
        path = 'Folder/' + 'A' * 64 + '.md'
        label.show_path(path)
        bar = viewport.horizontalScrollBar()
        self.wait_until(lambda: bar.maximum() > 0)
        bar.setValue(0)
        label.show_path(path)
        self.app.processEvents()
        self.assertEqual(bar.value(), 0)

    def test_clear_path_retires_ancestor_paths_and_scroll_extent(self):
        _, label, viewport, opened, revealed = self.make_path()
        label.show_path('Private/' + 'Folder' * 20 + '/Note.md')
        bar = viewport.horizontalScrollBar()
        self.wait_until(lambda: bar.maximum() > 0)
        label.clear_path()
        self.wait_until(lambda: bar.maximum() == 0)
        self.assertEqual(label.entries, [])
        self.assertEqual(label.folders, [])
        self.assertIsNone(label._path)
        self.assertEqual(label.text(), '')
        self.assertEqual(label.toolTip(), '')
        self.assertEqual(label.accessibleName(), '')
        label.activate('0')
        self.assertEqual(opened, [])
        self.assertEqual(revealed, [])
