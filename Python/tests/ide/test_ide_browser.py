"""Project tree ordering through the real asynchronous filesystem model."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import subprocess

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.ide.ui.browser import ProjectBrowser
from features.ide.projects import Project


class ProjectBrowserTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def wait_for_names(self, browser, path, expected):
        def matches():
            parent = browser.proxy.mapFromSource(browser.model.index(str(path)))
            names = [browser.proxy.data(browser.proxy.index(row, 0, parent))
                     for row in range(browser.proxy.rowCount(parent))]
            return names == expected
        self.wait_until(matches, message=f'Project browser did not display {expected}')

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
            browser = ProjectBrowser(Project('test', str(root)), owner)
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
            browser = ProjectBrowser(Project('test', str(root)), owner)
            self.wait_until(lambda: root / 'edited.py' in browser.proxy.git_changes)
            names = ['deleted_folder', 'ignored_folder', 'new_folder', 'clean.py', 'edited.py', 'ignored.py']
            if browser.model.index(str(root / '.gitignore')).isValid():
                # Match the filesystem model's platform-specific hidden-file policy.
                source = browser.model.index(str(root))
                if any(browser.model.fileName(browser.model.index(row, 0, source)) == '.gitignore'
                       for row in range(browser.model.rowCount(source))):
                    names.insert(3, '.gitignore')
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
            browser = ProjectBrowser(Project('test', str(root)), owner)
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
            (root / 'file.py').touch()
            owner = qt.QWidget()
            browser = ProjectBrowser(Project('test', str(root)), owner)
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
            browser = ProjectBrowser(Project('test', str(root)), owner)
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
            browser = ProjectBrowser(Project('test', str(root)), owner)
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
