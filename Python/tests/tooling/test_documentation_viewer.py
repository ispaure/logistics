"""Real desktop help widgets open the migrated guides and scoped file trees."""

from commonUtils.testing.stages import TestStage, stage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import MarkdownViewer
from commonUtils.ui.markdown.window import _windows
from commonUtils.formats.markdown.wiki import MarkdownWiki
from features.application import registry
from desktop.pages.settings import FeatureSettingsPanel

ROOT = Path(__file__).resolve().parents[3]


class DocumentationViewerTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])
        # The wiki is immutable in this suite; do not rescan it after every click.
        scope = (ROOT / 'docs').resolve()
        cls.expected_pages = {scope: frozenset(MarkdownWiki(scope).pages)}

    def assert_scope(self, viewer, path, scope):
        scope = scope.resolve()
        if scope not in self.expected_pages:
            self.expected_pages[scope] = frozenset(MarkdownWiki(scope).pages)
        self.assertEqual(viewer.current_path, path.resolve())
        self.assertEqual(viewer.wiki.catalog.root, scope)
        self.assertEqual(set(viewer.wiki.catalog.pages), self.expected_pages[scope])
        item = viewer.wiki.tree.currentItem()
        self.assertIsNotNone(item)
        self.assertEqual(item.data(0, qt.Qt.ItemDataRole.UserRole), path.resolve())

    @stage(TestStage.EXTENDED)
    def test_every_feature_help_button_opens_real_viewer_and_owned_tree(self):
        owners = sorted(p for p in (ROOT / 'Python/features').iterdir()
                        if not p.is_symlink() and (ROOT / 'docs/features' / p.name / 'user/user.md').is_file())
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
                self.assert_scope(window.viewer, ROOT / 'docs/features' / owner.name / 'user/user.md', ROOT / 'docs')
                self.assertIn(ROOT / 'docs/user/user.md', window.viewer.wiki.catalog.pages)
                window.close()
                panel.close()
                panel.deleteLater()
                self.app.processEvents()

    def test_feature_help_button_opens_owned_page_in_root_wiki(self):
        with patch.object(registry, 'get_settings', return_value=[]):
            panel = FeatureSettingsPanel(SimpleNamespace(name='git', label='Git', enabled=False, available=True))
            before = set(_windows)
            panel.guide_button.click()
            window = (set(_windows) - before).pop()
            self.assert_scope(window.viewer, ROOT / 'docs/features/git/user/user.md', ROOT / 'docs')
            window.close()
            panel.close()
            panel.deleteLater()

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
                  if not p.is_symlink() and (ROOT / 'docs/features' / p.name / 'user/user.md').is_file()]
        expected = {'Logistics Guide': ROOT / 'docs/user/user.md',
                    'Bulk Rename Guide': ROOT / 'docs/features/bulk_rename/user/user.md'}
        expected.update({state.label: ROOT / 'docs/features' / state.name / 'user/user.md'
                         for state in states})
        # Verify every route, but render one representative header action.
        # The exhaustive feature-button render sweep remains extended coverage.
        with patch('services.documentation.open_guide') as open_guide:
            with patch.object(registry, 'get_feature_states', return_value=states):
                HeaderMenus.update_guides(harness)
            for action in menu.actions():
                with self.subTest(menu=action.text()):
                    action.trigger()
                    self.assertEqual(open_guide.call_args.args[0], expected.pop(action.text()))
                    self.assertIs(open_guide.call_args.kwargs['parent'], host)
        self.assertFalse(expected)
        with patch.object(registry, 'get_feature_states', return_value=states):
            HeaderMenus.update_guides(harness)
        before = set(_windows)
        menu.actions()[0].trigger()
        window = (set(_windows) - before).pop()
        self.assert_scope(window.viewer, ROOT / 'docs/user/user.md', ROOT / 'docs')
        window.close()
        before = set(_windows)
        BrowserMenus.guide(SimpleNamespace(view=host))
        window = (set(_windows) - before).pop()
        self.assert_scope(window.viewer, ROOT / 'docs/user/files-and-documents.md', ROOT / 'docs')
        window.close()
        bulk = BulkRenameWindow(self.temporary_directory().name)
        help_menu = next(action.menu() for action in bulk.menuBar().actions() if action.text() == 'Help')
        before = set(_windows)
        help_menu.actions()[0].trigger()
        window = (set(_windows) - before).pop()
        self.assert_scope(window.viewer, ROOT / 'docs/features/bulk_rename/user/user.md', ROOT / 'docs')
        window.close(); bulk.close(); host.close()

    @stage(TestStage.EXTENDED)
    def test_real_folder_rows_open_landings_and_up_history_keep_scope(self):
        scopes = [ROOT / 'docs']
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
        second = ROOT / 'docs/features/git/user/user.md'
        viewer = MarkdownViewer(first, directory=ROOT / 'docs')
        viewer.follow_link(qt.QUrl('../features/git/user/user.md'))
        self.assert_scope(viewer, second, ROOT / 'docs')
        viewer.follow_link(qt.QUrl('../development/development.md'))
        self.assert_scope(viewer, second.parent.parent / 'development/development.md', ROOT / 'docs')
        viewer.back_button.click(); viewer.back_button.click()
        self.assert_scope(viewer, first, ROOT / 'docs')
        viewer.forward_button.click()
        self.assert_scope(viewer, second, ROOT / 'docs')
        viewer.close()

    def test_external_wiki_links_restore_each_catalog_through_history(self):
        scope = Path(self.temporary_directory().name).resolve() / 'docs'
        scope.mkdir()
        (scope / 'docs.md').write_text('# Synthetic wiki')
        page = scope / 'child.md'
        page.write_text('# Synthetic child\n\nExternal guide content.')
        first = ROOT / 'docs/docs.md'
        viewer = MarkdownViewer(first, directory=ROOT / 'docs')
        self.assert_scope(viewer, first, ROOT / 'docs')
        viewer.follow_link(qt.QUrl.fromLocalFile(str(page)))
        self.assert_scope(viewer, page, scope)
        self.assertIn('External guide content.', viewer.browser.toPlainText())
        viewer.back_button.click()
        self.assert_scope(viewer, first, ROOT / 'docs')
        viewer.forward_button.click()
        self.assert_scope(viewer, page, scope)
        viewer.close()
