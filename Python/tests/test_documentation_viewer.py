"""Real desktop help widgets open the migrated guides and scoped file trees."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import MarkdownViewer
from commonUtils.ui.markdown.window import _windows
from commonUtils.formats.markdown_wiki import MarkdownWiki
from features import registry
from desktop.pages.settings import FeatureSettingsPanel

ROOT = Path(__file__).resolve().parents[2]


class DocumentationViewerTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def assert_scope(self, viewer, path, scope):
        self.assertEqual(viewer.current_path, path.resolve())
        self.assertEqual(viewer.wiki.catalog.root, scope.resolve())
        self.assertEqual(set(viewer.wiki.catalog.pages), set(MarkdownWiki(scope).pages))
        item = viewer.wiki.tree.currentItem()
        self.assertIsNotNone(item)
        self.assertEqual(item.data(0, qt.Qt.ItemDataRole.UserRole), path.resolve())

    def test_every_feature_help_button_opens_real_viewer_and_owned_tree(self):
        owners = sorted(p for p in (ROOT / 'Python/features').iterdir()
                        if not p.is_symlink() and (p / 'docs/user/user.md').is_file())
        self.assertGreaterEqual(len(owners), 22)
        for owner in owners:
            with self.subTest(feature=owner.name), patch.object(registry, 'get_settings', return_value=[]):
                state = SimpleNamespace(name=owner.name, label=owner.name, enabled=False, available=True)
                panel = FeatureSettingsPanel(state)
                before = set(_windows)
                panel.guide_button.click()
                opened = set(_windows) - before
                self.assertEqual(len(opened), 1)
                window = opened.pop()
                self.assert_scope(window.viewer, owner / 'docs/user/user.md', owner / 'docs')
                self.assertNotIn(ROOT / 'docs/user/user.md', window.viewer.wiki.catalog.pages)
                window.close()
                panel.close()
                panel.deleteLater()
                self.app.processEvents()

    def test_header_menu_browser_and_bulk_help_open_their_real_scopes(self):
        from types import MethodType
        from desktop.header_menus import HeaderMenus
        from desktop.browser_menus import BrowserMenus
        from desktop.bulk_rename import BulkRenameWindow
        host = qt.QMainWindow()
        menu = qt.QMenu(host)
        harness = SimpleNamespace(owner=SimpleNamespace(dlg=host), guides=menu)
        harness.guide = MethodType(HeaderMenus.guide, harness)
        states = [SimpleNamespace(name=p.name, label=p.name)
                  for p in (ROOT / 'Python/features').iterdir()
                  if not p.is_symlink() and (p / 'docs/user/user.md').is_file()]
        with patch.object(registry, 'get_feature_states', return_value=states):
            HeaderMenus.update_guides(harness)
        expected = {'Logistics Guide': ROOT / 'docs/user/user.md',
                    'Bulk Rename Guide': ROOT / 'Python/desktop/bulk_rename/docs/user/user.md'}
        expected.update({state.label: ROOT / 'Python/features' / state.name / 'docs/user/user.md'
                         for state in states})
        for action in menu.actions():
            with self.subTest(menu=action.text()):
                before = set(_windows)
                action.trigger()
                opened = set(_windows) - before
                self.assertEqual(len(opened), 1)
                window = opened.pop()
                page = expected.pop(action.text())
                self.assert_scope(window.viewer, page, page.parent.parent)
                window.close()
        self.assertFalse(expected)
        before = set(_windows)
        BrowserMenus.guide(SimpleNamespace(view=host))
        window = (set(_windows) - before).pop()
        self.assert_scope(window.viewer, ROOT / 'docs/user/files-and-documents.md', ROOT / 'docs')
        window.close()
        bulk = BulkRenameWindow(self.temporary_directory().name)
        self.wait_until(lambda: bulk.renamer._generation > 0 and not bulk.renamer.progress.busy,
                        message="Bulk Rename fixture scan did not finish")
        help_menu = next(action.menu() for action in bulk.menuBar().actions() if action.text() == 'Help')
        before = set(_windows)
        help_menu.actions()[0].trigger()
        window = (set(_windows) - before).pop()
        scope = ROOT / 'Python/desktop/bulk_rename/docs'
        self.assert_scope(window.viewer, scope / 'user/user.md', scope)
        window.close(); bulk.close(); host.close()

    def test_real_folder_rows_open_landings_and_up_history_keep_scope(self):
        scopes = [ROOT / 'docs', ROOT / 'Python/desktop/bulk_rename/docs'] + [
            p / 'docs' for p in (ROOT / 'Python/features').iterdir()
            if not p.is_symlink() and (p / 'docs/docs.md').is_file()]
        for scope in scopes:
            with self.subTest(scope=scope):
                viewer = MarkdownViewer(directory=scope)
                self.assert_scope(viewer, scope / 'docs.md', scope)
                for folder in sorted(p for p in scope.rglob('*') if p.is_dir()):
                    landing = folder / (folder.name + '.md')
                    iterator = qt.QTreeWidgetItemIterator(viewer.wiki.tree)
                    item = None
                    while iterator.value():
                        if iterator.value().data(0, qt.Qt.ItemDataRole.UserRole) == landing:
                            item = iterator.value(); break
                        iterator += 1
                    self.assertIsNotNone(item, str(landing))
                    viewer.wiki.tree.setCurrentItem(item)
                    self.assert_scope(viewer, landing, scope)
                    expected = folder.parent / (folder.parent.name + '.md')
                    viewer.wiki.up_button.click()
                    self.assert_scope(viewer, expected, scope)
                    viewer.back_button.click()
                    self.assert_scope(viewer, landing, scope)
                viewer.close()

    def test_real_feature_and_systemic_links_switch_tree_with_history(self):
        first = ROOT / 'docs/user/features.md'
        second = ROOT / 'Python/features/git/docs/user/user.md'
        viewer = MarkdownViewer(first, directory=ROOT / 'docs')
        viewer.follow_link(qt.QUrl('../../Python/features/git/docs/user/user.md'))
        self.assert_scope(viewer, second, second.parent.parent)
        viewer.follow_link(qt.QUrl('../development/development.md'))
        self.assert_scope(viewer, second.parent.parent / 'development/development.md', second.parent.parent)
        viewer.back_button.click(); viewer.back_button.click()
        self.assert_scope(viewer, first, ROOT / 'docs')
        viewer.forward_button.click()
        self.assert_scope(viewer, second, second.parent.parent)
        viewer.close()
