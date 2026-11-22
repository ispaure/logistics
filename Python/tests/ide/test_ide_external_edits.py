"""IDE disk reconciliation through editor actions and native filesystem notifications."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path
from unittest.mock import patch

from commonUtils.persistence import atomic_write_bytes
from commonUtils.persistence.publication import rename_exclusive
from commonUtils.testing.stages import TestStage
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.ide.projects import Project
from features.ide.ui.workspace import ProjectWorkspace


TEST_STAGE = TestStage.REGRESSION


class ExternalEditsTests(QtTestCase):
    def wait(self, view):
        self.wait_until(lambda: not view.worker and not view.queue)

    def test_external_replace_at_save_publication_preserves_both_versions(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            path = root / 'a.py'
            path.write_text('original\n')
            view = ProjectWorkspace(Project('test', directory, autosave='off'))
            view.open_path(path)
            # Opening also queues a watcher read. Save should race only the
            # generated replacement, not an incidental initial reconciliation.
            self.wait_until(lambda: not view.disk_pending and not view.worker and not view.queue,
                            message='IDE did not finish opening and checking the test file')
            editor = view.current
            editor.insertPlainText('draft ')
            replaced = False

            def interleave(source, target):
                nonlocal replaced
                if Path(source) == path and Path(target).name == 'previous':
                    try:
                        # Keep the atomic replacement at the displacement
                        # boundary even if a Windows reader briefly holds it.
                        atomic_write_bytes(path, b'external\n', replace_timeout=1)
                    except OSError as error:
                        raise AssertionError('External replacement failed at Save displacement '
                                             f'(errno={error.errno}, winerror={getattr(error, "winerror", None)}).') from error
                    replaced = True
                return rename_exclusive(source, target)

            with (patch('commonUtils.persistence.publication.rename_exclusive', side_effect=interleave),
                  patch.object(qt.QMessageBox, 'exec', return_value=0) as conflict):
                saved = view.save_current()

            self.assertTrue(replaced, f'Save did not reach external replacement: {view.status.text()}')
            conflict.assert_called_once()
            self.assertEqual(path.read_text(), 'external\n')
            self.assertFalse(saved)
            self.assertEqual(editor.toPlainText(), 'draft original\n')
            self.assertTrue(editor.document().isModified())
            self.wait(view)
            self.assertTrue(view.prepare_close())
            view.close()

    def test_native_watcher_reloads_clean_splits_and_rearms_after_replacement(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            path = root / 'a.py'
            path.write_text('original source\n')
            view = ProjectWorkspace(Project('test', directory, autosave='off'))
            view.show()
            view.open_path(path)
            self.wait(view)
            left = view.current
            view.split_right()
            right = view.current
            for editor, anchor, position in ((left, 4, 2), (right, 6, 8)):
                cursor = editor.textCursor()
                cursor.setPosition(anchor)
                cursor.setPosition(position, qt.QTextCursor.MoveMode.KeepAnchor)
                editor.setTextCursor(cursor)
            right.setFocus()
            focus = qt.QApplication.focusWidget()
            path.write_text('in-place changed\n')
            self.wait_until(lambda: right.toPlainText() == 'in-place changed\n')
            self.assertIs(qt.QApplication.focusWidget(), focus)
            self.assertIs(view.current, right)
            self.assertEqual((left.textCursor().anchor(), left.textCursor().position()), (4, 2))
            self.assertEqual((right.textCursor().anchor(), right.textCursor().position()), (6, 8))

            view.hide()
            replacement = root / 'replacement'
            replacement.write_text('atomic replacement\n')
            replacement.replace(path)
            self.wait_until(lambda: right.toPlainText() == 'atomic replacement\n')
            view.show()
            path.write_text('second in-place edit\n')
            self.wait_until(lambda: left.toPlainText() == 'second in-place edit\n')
            self.assertFalse(left.document().isModified())
            self.assertFalse(left.document().isUndoAvailable())
            self.wait(view)
            self.assertTrue(view.prepare_close())
            view.close()

    def test_native_watcher_reports_dirty_rename_and_refreshes_recreated_path(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            parent = root / 'src'
            parent.mkdir()
            path, renamed = parent / 'a.py', root / 'renamed'
            path.write_text('original\n')
            view = ProjectWorkspace(Project('test', directory, autosave='after_delay'))
            view.open_path(path)
            self.wait(view)
            editor = view.current
            editor.insertPlainText('draft ')
            parent.rename(renamed)
            self.wait_until(lambda: 'removed or renamed' in view.autosave_notice.text())
            parent.mkdir()
            path.write_text('external\n')
            self.wait_until(lambda: 'changed on disk' in view.autosave_notice.text())
            self.assertEqual(editor.toPlainText(), 'draft original\n')
            self.assertEqual((renamed / path.name).read_text(), 'original\n')
            self.assertEqual(path.read_text(), 'external\n')

            def choose_save_as(dialog):
                self.assertEqual(dialog.defaultButton().text(), 'Cancel')
                next(button for button in dialog.buttons() if button.text() == 'Save As…').click()
                return 0

            copy = root / 'draft.py'
            with (patch.object(qt.QMessageBox, 'exec', choose_save_as),
                  patch.object(qt.QFileDialog, 'getSaveFileName', return_value=(str(copy), ''))):
                self.assertTrue(view.save_current())
            self.assertEqual(path.read_text(), 'external\n')
            self.assertEqual(copy.read_text(), 'draft original\n')
            self.assertFalse(editor.document().isModified())
            self.assertEqual(editor.path, copy)
            self.wait(view)
            self.assertTrue(view.prepare_close())
            view.close()

    def test_save_before_notification_can_discard_draft_and_reload(self):
        with self.temporary_directory() as directory:
            path = Path(directory).resolve() / 'a.md'
            path.write_text('original\n')
            view = ProjectWorkspace(Project('test', directory, autosave='off'))
            view.open_path(path)
            self.wait(view)
            editor = view.current
            editor.setPlainText('draft\n')
            editor.document().setModified(True)
            path.write_text('disk version\n')

            def reload_disk(dialog):
                next(button for button in dialog.buttons() if button.text() == 'Discard Draft and Reload').click()
                return 0

            with patch.object(qt.QMessageBox, 'exec', reload_disk):
                self.assertTrue(view.save_current())
            self.assertEqual(path.read_text(), 'disk version\n')
            self.assertEqual(editor.toPlainText(), 'disk version\n')
            self.assertFalse(editor.document().isModified())
            self.assertTrue(view.prepare_close())
            view.close()

    def test_native_project_tree_refresh_keeps_selection_and_filter(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            nested = root / 'src'
            nested.mkdir()
            selected = nested / 'selected.py'
            selected.write_text('original\n')
            view = ProjectWorkspace(Project('test', directory, autosave='off', source_paths=['src'],
                                            excluded_paths=['generated'], excluded_patterns=['*.cache']))
            view.show()
            browser = view.browser

            def index(path):
                return browser.proxy.mapFromSource(browser.model.index(str(path)))

            def names(parent):
                parent = index(parent)
                return [browser.proxy.index(i, 0, parent).data()
                        for i in range(browser.proxy.rowCount(parent))]

            self.wait_until(lambda: names(root) == ['src'])
            browser.tree.expand(index(nested))
            self.wait_until(lambda: names(nested) == ['selected.py'])
            browser.locate(selected)
            browser.filter.setText('py')
            self.assertEqual(browser.path(), selected)

            def tooltip_lines(path):
                return index(path).data(qt.Qt.ItemDataRole.ToolTipRole).splitlines()

            created, renamed = nested / 'created.py', nested / 'renamed.py'
            created.write_text('create\n')
            generated = nested / 'generated'
            generated.mkdir()
            (nested / 'hidden.py.cache').touch()
            self.wait_until(lambda: names(nested) == ['generated', 'created.py', 'selected.py'],
                            message=lambda: f'After creation: {names(nested)}')
            self.assertEqual(tooltip_lines(generated)[1], 'Excluded')
            # Control the snapshot only while reading the tooltip.
            with patch.object(browser.proxy, 'git_changes', {}):
                self.assertEqual(tooltip_lines(generated), [str(generated), 'Excluded'])
            with patch.object(browser.proxy, 'git_changes', {generated: ('ignored', 'Ignored')}):
                self.assertEqual(tooltip_lines(generated), [str(generated), 'Excluded', 'Git: Ignored'])
            self.assertEqual(browser.path(), selected)
            self.assertTrue(browser.tree.isExpanded(index(nested)))

            view.hide()
            created.rename(renamed)
            regular = nested / 'regular'
            generated.rename(regular)
            self.wait_until(lambda: names(nested) == ['regular', 'renamed.py', 'selected.py'])
            self.assertEqual(tooltip_lines(regular)[1], 'Source')
            replacement = nested / 'temporary.cache'
            replacement.write_text('replacement\n')
            replacement.replace(selected)
            renamed.unlink()
            view.show()
            self.wait_until(lambda: names(nested) == ['regular', 'selected.py'])
            self.assertEqual(browser.path(), selected)
            self.assertTrue(browser.tree.isExpanded(index(nested)))
            self.assertEqual(browser.filter.text(), 'py')
            self.wait(view)
            self.assertTrue(view.prepare_close())
            view.close()

    def test_autosave_keeps_recovery_when_another_writer_recreates_the_path(self):
        with self.temporary_directory() as directory:
            root = Path(directory).resolve()
            path = root / 'a.py'
            path.write_text('original\n')
            view = ProjectWorkspace(Project('test', directory, autosave='after_delay'))
            view.open_path(path)
            self.wait(view)
            editor = view.current
            editor.insertPlainText('draft ')

            def recreate_before_publishing(source, target):
                if Path(target) == path and Path(source).name == 'draft':
                    with path.open('x') as stream:
                        stream.write('external\n')
                return rename_exclusive(source, target)

            with patch('commonUtils.persistence.publication.rename_exclusive', recreate_before_publishing):
                editor.buffer.autosave.save()
                self.wait_until(lambda: bool(editor.buffer.autosave.error))
            self.assertTrue(editor.document().isModified())
            self.assertEqual(editor.toPlainText(), 'draft original\n')
            self.assertEqual(path.read_text(), 'external\n')
            recovery, = root.glob('.logistics-save-*/previous')
            self.assertEqual(recovery.read_text(), 'original\n')
            self.assertIn(str(recovery), view.autosave_notice.text())
            self.wait(view)
            self.assertTrue(view.prepare_close())
            view.close()

    def test_clean_markdown_keeps_read_mode_after_delete_and_recreation(self):
        with self.temporary_directory() as directory:
            path = Path(directory).resolve() / 'guide.md'
            path.write_text('# Original\n')
            view = ProjectWorkspace(Project('test', directory, autosave='off'))
            view.open_path(path)
            self.wait(view)
            editor = view.current
            editor.set_editing(False)
            path.unlink()
            self.wait_until(lambda: 'removed or renamed' in view.autosave_notice.text())
            self.assertIs(view.current, editor)
            self.assertIn('Original', editor.browser.toPlainText())
            path.write_bytes('# Recreated\n'.encode('utf-16'))
            self.wait_until(lambda: 'Recreated' in editor.browser.toPlainText())
            self.assertFalse(editor.edit_button.isChecked())
            self.assertEqual(editor.toPlainText(), '# Recreated\n')
            self.assertFalse(editor.document().isModified())
            self.assertFalse(view.autosave_notice.text())
            self.wait(view)
            self.assertTrue(view.prepare_close())
            view.close()
