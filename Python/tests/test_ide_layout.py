"""Project ownership, compact menus, tab geometry and confined editor gestures."""
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.ide.page import IDEPage
from features.ide.projects import Project
from features.ide.workspace import ProjectWorkspace


class IDELayoutTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()

    def settle(self):
        for _ in range(8):
            self.app.processEvents()

    def wait(self, view):
        deadline = time.monotonic() + 8
        while view.worker or view.queue:
            self.settle()
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.001)

    def page(self):
        page = IDEPage(store_path=self.root / 'state.json')
        page.resize(1200, 700)
        page.show()
        return page

    def project(self, page, number, destination=None):
        project = Project(f'Project {number}', str(self.root))
        page.store.projects[project.id] = project
        view = page.open_project(project, destination)
        self.wait(view)
        self.settle()
        return view

    def test_empty_one_two_three_projects_and_local_detached_plus(self):
        page = self.page()
        self.settle()
        self.assertTrue(page.workspace.empty_new_button.isVisible())
        self.assertEqual(page.views, [])
        first = self.project(page, 1)
        dock = page.dock_for(first)
        self.assertGreater(dock.tab_header.height(), 0)
        for number in (2, 3):
            self.project(page, number)
            page.workspace._refresh_tab_headers()
            self.settle()
            bar = next(b for b in page.workspace.findChildren(qt.QTabBar)
                       if b.parent() is page.workspace and b.count() == number)
            widths = [bar.tabRect(i).width() for i in range(number)]
            self.assertLessEqual(max(widths) - min(widths), 1)
            self.assertGreater(sum(widths), bar.width() * .8)
        window = page.workspace.detach_dock(dock)
        self.settle()
        self.assertEqual(dock.tab_header.height(), 0)
        self.assertTrue(dock.local_new_button.isVisible())
        with patch.object(page, 'project_menu', wraps=page.project_menu):
            menu = window.workspace.request_new_view()
            with patch.object(page, 'register_project') as register:
                menu.actions()[0].trigger()
                register.assert_called_once_with(window.workspace)
            menu.close()
        self.project(page, 4, window.workspace)
        self.assertEqual(len(window.workspace.docks), 2)
        self.assertEqual(len(page.workspace.docks), 2)
        self.assertTrue(page.can_close())
        self.assertTrue(page.prepare_close())

    def test_splitter_menus_and_project_close_veto(self):
        page = self.page()
        view = self.project(page, 1)
        path = self.root / 'a.py'
        path.write_text('text\n')
        view.open_path(path)
        self.wait(view)
        view.splitter.setSizes([0, 10000])
        self.settle()
        self.assertGreaterEqual(view.splitter.sizes()[0], view.browser.minimumWidth())
        self.assertFalse(view.splitter.childrenCollapsible())
        self.assertFalse(view.findChildren(qt.QToolBar))
        self.assertEqual([a.text() for a in view.menuBar().actions()], ['File', 'Edit', 'View', 'Navigate', 'Project'])
        view.current.insertPlainText('edited')
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
            self.assertFalse(page.close_project(view))
        self.assertIn(view, page.views)
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Discard):
            self.assertTrue(page.close_project(view))
        self.settle()
        self.assertEqual(page.views, [])
        self.assertTrue(page.workspace.empty_new_button.isVisible())

    def test_three_groups_drag_reorder_boundaries_and_buffer_preservation(self):
        view = ProjectWorkspace(Project('test', str(self.root)))
        view.resize(1200, 700)
        view.show()
        for name in ('a.py', 'b.py', 'c.py'):
            path = self.root / name
            path.write_text(name)
            view.open_path(path)
        self.wait(view)
        first = view.groups[0]
        a, b, c = [first.widget(i) for i in range(3)]
        b.insertPlainText('unsaved')
        buffer = b.document()
        view.drop_editor(b, first, 'right')
        view.drop_editor(c, view.groups[-1], 'right')
        self.assertEqual(len(view.groups), 3)
        self.assertFalse(view.drop_editor(a, first, 'left'))
        self.assertIs(b.document(), buffer)
        self.assertTrue(buffer.isModified())
        self.settle()
        bar = view.group_for(b).tabBar()
        self.assertIsNone(bar.target(view.editors.mapToGlobal(qt.QPoint(-20, 100))))
        foreign = qt.QTabWidget()
        self.assertFalse(view.drop_editor(b, foreign))
        # A real press/move/release from b's header into a's center merges groups.
        start = bar.mapToGlobal(bar.tabRect(0).center())
        end = first.mapToGlobal(first.rect().center())
        for kind, point in ((qt.QEvent.Type.MouseButtonPress, start),
                            (qt.QEvent.Type.MouseMove, end), (qt.QEvent.Type.MouseButtonRelease, end)):
            event = qt.QMouseEvent(kind, qt.QPointF(bar.mapFromGlobal(point)), qt.QPointF(point),
                qt.Qt.MouseButton.NoButton if kind == qt.QEvent.Type.MouseMove else qt.Qt.MouseButton.LeftButton,
                qt.Qt.MouseButton.NoButton if kind == qt.QEvent.Type.MouseButtonRelease else qt.Qt.MouseButton.LeftButton,
                qt.Qt.KeyboardModifier.NoModifier)
            self.app.sendEvent(bar, event)
        self.assertEqual(len(view.groups), 2)
        self.assertIs(view.group_for(b), first)
        self.assertIs(b.document(), buffer)
        view.drop_editor(b, first, 'tabs', 0)
        self.assertIs(first.widget(0), b)
        view.activate(view.group_for(c))
        view.close_group()
        self.assertEqual(len(view.groups), 1)
        self.assertEqual(len(view.documents), 3)
        for doc in view.documents.values():
            doc.document().setModified(False)
        view.prepare_close()

    def test_edit_menu_routes_to_active_editor_and_native_publication(self):
        page = self.page()
        one, two = self.project(page, 1), self.project(page, 2)
        for view, name in ((one, 'a.py'), (two, 'b.py')):
            path = self.root / name
            path.write_text(name)
            view.open_path(path)
            self.wait(view)
        two.current.insertPlainText('change')
        undo = next(a for a in two.menus['Edit'].actions() if a.text() == 'Undo')
        undo.trigger()
        self.assertEqual(two.current.toPlainText(), 'b.py')
        self.assertEqual(one.current.toPlainText(), 'a.py')
        from commonUtils.ui.workspace_menus import sync_native_menus
        host = qt.QMainWindow()
        with patch('commonUtils.ui.workspace_menus.sys.platform', 'darwin'):
            sync_native_menus(host, two)
            self.assertEqual(host.menuBar().actions(), two.menuBar().actions())
            sync_native_menus(host, one)
            self.assertEqual(host.menuBar().actions(), one.menuBar().actions())
        for view in (one, two):
            view.current.document().setModified(False)
        page.can_close()
        page.prepare_close()
