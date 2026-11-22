"""Project tree ordering through the real asynchronous filesystem model."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
from pathlib import Path
import subprocess
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.colors import contrast_ratio
from commonUtils.ui.appearance.theme import configured_colors, theme_palette
from features.ide.ui.browser import ProjectBrowser
from features.ide.ui.project_structure import ProjectStructure
from features.ide.projects import Project


class ProjectBrowserTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def wait_for_names(self, browser, path, expected):
        names = []
        def matches():
            nonlocal names
            parent = browser.proxy.mapFromSource(browser.model.index(str(path)))
            names = [browser.proxy.data(browser.proxy.index(row, 0, parent))
                     for row in range(browser.proxy.rowCount(parent))]
            return names == expected
        self.wait_until(matches, message=lambda: f'Project browser expected {expected}, got {names}; filter={browser.proxy.query!r}')

    def test_folders_first_natural_names_nested_filter_and_new_entries(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            for name in ('a10.py', 'a2.py', 'B.py'):
                (root / name).touch()
            for name in ('z10', 'z2'):
                (root / name).mkdir()
            nested = root / 'z2'
            (nested / 'a.py').touch()
            (nested / 'z_folder').mkdir()
            owner = qt.QWidget()
            browser = ProjectBrowser(Project('test', str(root), autosave='off'), owner)
            self.wait_for_names(browser, root, ['z2', 'z10', 'a2.py', 'a10.py', 'B.py'])
            nested_index = browser.proxy.mapFromSource(browser.model.index(str(nested)))
            browser.tree.expand(nested_index)
            self.wait_for_names(browser, nested, ['z_folder', 'a.py'])
            browser.filter.setText('a')
            self.wait_for_names(browser, root, ['z2', 'z10', 'a2.py', 'a10.py'])
            browser.filter.clear()
            (root / 'z1').mkdir()
            (root / 'a1.py').touch()
            self.wait_for_names(browser, root, ['z1', 'z2', 'z10', 'a1.py', 'a2.py', 'a10.py', 'B.py'])
            browser.locate(root / 'a2.py')
            self.assertEqual(browser.path(), root / 'a2.py')
            owner.close()

    def test_folder_roles_match_settings_in_light_and_dark(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            roles = {
                'src': 'Source',
                'src/lib': 'Source',
                'src/lib/generated': 'Excluded',
                'src/lib/generated/nested': 'Excluded',
                'src/lib/generated/nested/leaf': 'Excluded',
                'other/code': 'Source',
                'other/code/nested': 'Source',
                'other/code/cache': 'Excluded',
                'other/code/build.pkg': 'Excluded',
                '.venv': 'Excluded',
                'other': '',
            }
            for name in roles:
                (root / name).mkdir(parents=True, exist_ok=True)
            (root / '.unrelated').mkdir()
            (root / 'src/lib/generated/nested/skipped.py').touch()
            (root / 'src/skipped.tmp').touch()
            (root / 'src/shown.py').touch()
            project = Project('test', str(root), source_paths=['src', str(root / 'other/code'),
                                                               'src/lib/generated/nested'],
                              excluded_paths=['src/lib/generated', 'cache', '.venv'],
                              excluded_patterns=['*.pkg', '*.tmp'])
            owner = qt.QWidget()
            layout = qt.QHBoxLayout(owner)
            settings = ProjectStructure(project, owner)
            browser = ProjectBrowser(project, owner)
            browser.git_status.stop()
            layout.addWidget(settings)
            layout.addWidget(browser)
            owner.show()

            def browser_index(name):
                return browser.proxy.mapFromSource(browser.model.index(str(root / name)))

            names = ['.venv', 'other', 'src']
            if not qt.QFileInfo(str(root / '.unrelated')).isHidden():
                names.insert(0, '.unrelated')
            self.wait_for_names(browser, root, names)
            for name, children in (
                ('src', ['lib', 'shown.py']),
                ('src/lib', ['generated']),
                ('src/lib/generated', ['nested']),
                ('src/lib/generated/nested', ['leaf']),
                ('other', ['code']),
                ('other/code', ['build.pkg', 'cache', 'nested']),
            ):
                browser.tree.expand(browser_index(name))
                settings.tree.expand(settings.model.index(str(root / name)))
                self.wait_for_names(browser, root / name, children)

            foreground = qt.Qt.ItemDataRole.ForegroundRole
            tooltip = qt.Qt.ItemDataRole.ToolTipRole
            self.assertIsNone(browser_index('src/shown.py').data(foreground))
            excluded = 'src/lib/generated'
            browser.proxy.git_changes[root / excluded] = ('ignored', 'Ignored')
            browser.locate(root / 'src/lib')
            colors = []
            for dark in (False, True):
                if dark:
                    # A filesystem update can move a row between palette comparisons.
                    (root / 'src/lib/added').mkdir()
                    self.wait_for_names(browser, root / 'src/lib', ['added', 'generated'])
                owner.setPalette(theme_palette(configured_colors(dark)))
                self.app.processEvents()
                self.assertEqual(browser.path(), root / 'src/lib')
                self.assertEqual(settings.tree.palette(), browser.tree.palette())
                palette = browser.tree.palette()
                palette_role = qt.QPalette.ColorRole
                background = palette.color(palette_role.Base).rgba()
                self.assertGreaterEqual(contrast_ratio(palette.color(palette_role.HighlightedText).rgba(),
                                                       palette.color(palette_role.Highlight).rgba()), 4.5)
                for name, status in roles.items():
                    with self.subTest(name=name, dark=dark):
                        index = browser_index(name)
                        self.assertTrue(index.isValid())
                        settings_index = settings.model.index(str(root / name))
                        self.assertTrue(settings_index.isValid())
                        self.assertEqual(settings.status_for(root / name), status)
                        self.assertEqual(index.data(foreground), settings_index.data(foreground))
                        if status:
                            self.assertEqual(index.data(tooltip).splitlines()[1], status)
                            color = index.data(foreground).color()
                            self.assertGreaterEqual(contrast_ratio(color.rgba(), background), 4.5)
                            for tree, item in ((browser.tree, index), (settings.tree, settings_index)):
                                option = qt.QStyleOptionViewItem()
                                option.initFrom(tree)
                                tree.itemDelegate().initStyleOption(option, item)
                                self.assertEqual(option.palette.color(qt.QPalette.ColorRole.Text), color)
                # Resolve the path after event processing and any proxy layout changes.
                excluded_index = browser_index(excluded)
                description = excluded_index.data(tooltip)
                self.assertIn('Git: Ignored', description)
                self.assertIn('Excluded', description)
                source_color = browser_index('src').data(foreground)
                excluded_color = excluded_index.data(foreground)
                self.assertNotEqual(source_color, excluded_color)
                colors.append((source_color, excluded_color))
            self.assertNotEqual(*colors)
            owner.close()

    def test_git_colors_refresh_for_modified_new_staged_and_clean_files(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            def git(*args):
                subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
            git('init')
            for name in ('edited.py', 'clean.py'):
                (root / name).write_text('original\n')
            (root / '.gitignore').write_text('ignored.py\nignored_folder/\n')
            (root / 'deleted_folder').mkdir()
            (root / 'deleted_folder' / 'gone.py').write_text('gone\n')
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.test', 'commit', '-m', 'initial')
            (root / 'edited.py').write_text('edited\n')
            (root / 'new_folder').mkdir()
            new = root / 'new_folder' / 'new.py'
            new.write_text('new\n')
            (root / 'ignored.py').write_text('ignored\n')
            ignored = root / 'ignored_folder'
            (ignored / 'nested').mkdir(parents=True)
            (ignored / 'nested' / 'child.py').write_text('ignored child\n')
            (root / 'deleted_folder' / 'gone.py').unlink()
            owner = qt.QWidget()
            browser = ProjectBrowser(Project('test', str(root), source_paths=[], autosave='off'), owner)
            self.wait_until(lambda: root / 'edited.py' in browser.proxy.git_changes)
            names = ['.git', 'deleted_folder', 'ignored_folder', 'new_folder', 'clean.py', 'edited.py', 'ignored.py']
            if not qt.QFileInfo(str(root / '.gitignore')).isHidden():
                names.insert(4, '.gitignore')
            self.wait_for_names(browser, root, names)
            def data(path, role):
                index = browser.proxy.mapFromSource(browser.model.index(str(path)))
                self.assertTrue(index.isValid(), path)
                return browser.proxy.data(index, role)
            foreground = qt.Qt.ItemDataRole.ForegroundRole
            tooltip = qt.Qt.ItemDataRole.ToolTipRole
            self.assertEqual(data(root / 'edited.py', foreground).color().name(), '#408bd6')
            for path in (root / 'edited.py', new):
                actual = data(path, qt.Qt.ItemDataRole.DecorationRole).pixmap(16, 16).toImage()
                expected = browser.model.fileIcon(browser.model.index(str(path))).pixmap(16, 16).toImage()
                self.assertEqual(actual, expected)
                self.assertEqual(data(path, qt.Qt.ItemDataRole.DisplayRole), path.name)
            self.assertEqual(data(new, foreground).color().name(), '#009e73')
            self.assertIn('untracked', data(new, tooltip))
            for folder in (root, root / 'new_folder', root / 'deleted_folder'):
                self.assertNotIn(folder, browser.proxy.git_changes)
                self.assertIsNone(data(folder, foreground))
            for path in (ignored, ignored / 'nested', ignored / 'nested' / 'child.py', root / 'ignored.py'):
                self.assertEqual(data(path, foreground).color().name(), '#848504')
                self.assertIn('Git: Ignored', data(path, tooltip))
            self.assertNotIn(root / 'clean.py', browser.proxy.git_changes)
            git('add', str(new))
            browser.git_status.refresh()
            self.wait_until(lambda: 'staged' in browser.proxy.git_changes[new][1])
            self.assertIn('staged', data(new, tooltip))
            (root / 'edited.py').write_text('original\n')
            self.wait_until(lambda: root / 'edited.py' not in browser.proxy.git_changes)
            self.assertIsNone(data(root / 'edited.py', foreground))

    def test_git_status_worker_start_failure_clears_stale_colors_and_retries(self):
        from unittest.mock import patch
        from features.ide.ui import git_status
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            path = root / 'file.py'
            path.write_text('fixture')
            subprocess.run(['git', '-C', str(root), 'init'], check=True, capture_output=True)
            owner = qt.QWidget()
            browser = ProjectBrowser(Project('test', str(root), autosave='off'), owner)
            self.wait_until(lambda: path in browser.proxy.git_changes and browser.git_status.future is None)
            for error in (OSError('synthetic start failure'), RuntimeError()):
                with self.subTest(error=type(error).__name__):
                    with patch.object(git_status._executor, 'submit', side_effect=error):
                        browser.git_status.refresh()
                    self.assertEqual(browser.proxy.git_changes, {})
                    self.assertIsNone(browser.git_status.future)
                    self.assertEqual(browser.git_status.pending, [])
                    self.assertTrue(browser.git_status.timer.isActive())
                    browser.git_status.refresh()
                    self.wait_until(lambda: path in browser.proxy.git_changes
                                    and browser.git_status.future is None)
            self.assertEqual(path.read_text(), 'fixture')

    def test_non_git_project_has_no_status_colors(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            self.enterContext(patch.dict(os.environ, GIT_CEILING_DIRECTORIES=str(root.parent)))
            (root / 'file.py').touch()
            owner = qt.QWidget()
            browser = ProjectBrowser(Project('test', str(root), autosave='off'), owner)
            self.wait_until(lambda: browser.git_status.future is None)
            self.assertEqual(browser.proxy.git_changes, {})

    def test_inline_rename_uses_filename_without_status_label_and_escape_cancels(self):
        from PySide6.QtTest import QTest
        from unittest.mock import Mock
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            path = root / 'file.py'
            path.write_text('content\n')
            folder = root / 'folder'
            folder.mkdir()
            (folder / 'child.py').write_text('child\n')
            subprocess.run(['git', '-C', str(root), 'init'], check=True, capture_output=True)
            owner = qt.QWidget()
            owner.documents, owner.pending_opens, owner.error = {}, {}, Mock()
            layout = qt.QVBoxLayout(owner)
            browser = ProjectBrowser(Project('test', str(root), autosave='off'), owner)
            layout.addWidget(browser)
            owner.resize(640, 400)
            owner.show()
            owner.activateWindow()
            def inline_editor(name):
                return next((e for e in browser.tree.findChildren(qt.QLineEdit)
                             if e.isVisible() and e.text() == name), None)
            self.wait_until(lambda: path in browser.proxy.git_changes)
            browser.locate(path)
            browser.tree.setFocus()
            self.app.processEvents()
            QTest.keyClick(browser.tree, qt.Qt.Key.Key_F2)
            self.wait_until(lambda: inline_editor('file.py') is not None)
            editor = inline_editor('file.py')
            self.assertEqual(editor.text(), 'file.py')
            self.wait_until(lambda: editor.selectedText() == 'file')
            editor.setText('renamed.py')
            QTest.keyClick(editor, qt.Qt.Key.Key_Return)
            renamed = root / 'renamed.py'
            self.wait_until(renamed.exists)
            self.assertEqual(renamed.read_text(), 'content\n')
            self.assertFalse(path.exists())
            browser.rename(renamed)
            self.wait_until(lambda: inline_editor('renamed.py') is not None)
            editor = inline_editor('renamed.py')
            editor.setText('cancelled.py')
            QTest.keyClick(editor, qt.Qt.Key.Key_Escape)
            self.assertTrue(renamed.exists())
            self.assertFalse((root / 'cancelled.py').exists())
            folder_index = browser.proxy.mapFromSource(browser.model.index(str(folder)))
            browser.tree.expand(folder_index)
            browser.rename(folder)
            self.wait_until(lambda: inline_editor('folder') is not None)
            editor = inline_editor('folder')
            self.assertEqual(editor.text(), 'folder')
            editor.setText('renamed_folder')
            QTest.keyClick(editor, qt.Qt.Key.Key_Return)
            self.wait_until(lambda: (root / 'renamed_folder' / 'child.py').exists())
            self.assertNotIn(str(folder), browser.expanded_paths)
            self.assertIn(str(root / 'renamed_folder'), browser.expanded_paths)

    def test_inline_rename_rechecks_open_files_and_rejects_invalid_names_and_collisions(self):
        from unittest.mock import Mock
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            path = root / 'file.py'
            path.write_text('keep\n')
            (root / 'existing.py').write_text('existing\n')
            owner = qt.QWidget()
            owner.documents, owner.pending_opens, owner.error = {}, {}, Mock()
            browser = ProjectBrowser(Project('test', str(root), autosave='off'), owner)
            self.wait_for_names(browser, root, ['existing.py', 'file.py'])
            index = browser.proxy.mapFromSource(browser.model.index(str(path)))
            self.assertTrue(browser.proxy.flags(index) & qt.Qt.ItemFlag.ItemIsEditable)
            for name in ('../escape.py', 'existing.py'):
                self.assertFalse(browser.proxy.setData(index, name))
            owner.pending_opens[path] = 1
            self.assertFalse(browser.proxy.setData(index, 'renamed.py'))
            self.assertFalse(browser.proxy.flags(index) & qt.Qt.ItemFlag.ItemIsEditable)
            self.assertTrue(path.exists())
            self.assertEqual((root / 'existing.py').read_text(), 'existing\n')
            self.assertTrue(browser.model.isReadOnly())

    def test_dirty_submodule_reports_its_individual_files(self):
        from features.ide.ui.git_status import read_status
        from threading import Event
        with self.temporary_directory() as directory:
            base = Path(directory).resolve()
            root, child = base / 'main', base / 'child'
            root.mkdir(); child.mkdir()
            def git(path, *args):
                subprocess.run(['git', '-C', str(path), *args], check=True, capture_output=True)
            git(child, 'init')
            (child / '__init__.py').write_text('original\n')
            git(child, 'add', '.')
            git(child, '-c', 'user.name=Test', '-c', 'user.email=test@example.test', 'commit', '-m', 'initial')
            git(root, 'init')
            git(root, '-c', 'protocol.file.allow=always', 'submodule', 'add', str(child), 'lib')
            git(root, '-c', 'user.name=Test', '-c', 'user.email=test@example.test', 'commit', '-m', 'submodule')
            path = root / 'lib' / '__init__.py'
            path.write_text('edited\n')
            new = root / 'lib' / 'new.py'
            new.write_text('new\n')
            changes = read_status(root, Event())
            self.assertEqual(changes[path][0], 'modify')
            self.assertEqual(changes[new][0], 'add')
            self.assertNotIn(root, changes)
            self.assertNotIn(root / 'lib', changes)
            self.assertIn('untracked', changes[new][1])
            self.assertEqual(read_status(path.parent, Event())[path][0], 'modify')

    def test_ignored_project_root_and_tracked_exception_refresh(self):
        from features.ide.ui.git_status import read_status
        from threading import Event
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            def git(*args):
                subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
            git('init')
            (root / '.gitignore').write_text('ignored/\n')
            project_root = root / 'ignored' / 'project'
            project_root.mkdir(parents=True)
            tracked = project_root / 'tracked.py'
            tracked.write_text('tracked\n')
            ignored = project_root / 'ignored.py'
            ignored.write_text('ignored\n')
            self.assertEqual(read_status(project_root, Event()), {project_root: ('ignored', 'Ignored')})
            git('add', '-f', str(tracked))
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.test', 'commit', '-m', 'tracked exception')
            changes = read_status(project_root, Event())
            self.assertNotIn(project_root, changes)
            self.assertNotIn(tracked, changes)
            self.assertEqual(changes[ignored], ('ignored', 'Ignored'))
            tracked.write_text('modified\n')
            self.assertEqual(read_status(project_root, Event())[tracked][0], 'modify')
            (root / '.gitignore').write_text('')
            self.assertEqual(read_status(project_root, Event())[ignored][0], 'add')

    def test_modified_directory_symlink_keeps_file_status(self):
        from features.ide.ui.git_status import read_status
        from threading import Event
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            def git(*args):
                subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
            git('init')
            for name in ('first', 'second'):
                (root / name).mkdir()
            link = root / 'link'
            try:
                link.symlink_to('first', target_is_directory=True)
            except OSError as error:
                self.skipTest(f'Directory symlinks unavailable: {error}')
            git('add', str(link))
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.test', 'commit', '-m', 'symlink')
            link.unlink()
            link.symlink_to('second', target_is_directory=True)
            self.assertEqual(read_status(root, Event())[link][0], 'modify')
