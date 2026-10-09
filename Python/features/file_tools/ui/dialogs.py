"""Folder diagnostics and cleanup windows with background work and visible results."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from features.file_tools import filesystem
from ui_new.dialogs.tool_dialog import ToolDialog, coerce_initial_path


class _ResultsDialog(ToolDialog):
    def __init__(self, title, description, action, destructive, initial_path, parent):
        super().__init__(title, description, action, destructive, parent)
        self.targets = tuple(Path(path) for path in initial_path) if isinstance(initial_path, (tuple, list)) else ()
        if len(self.targets) > 1:
            target_label = qt.QLabel('\n'.join(str(path) for path in self.targets))
            target_label.setTextFormat(qt.Qt.TextFormat.PlainText)
            target_label.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
            self.form.addRow('Target folders:', target_label)
            self.target_dir = None
        else:
            default = self.targets[0] if self.targets else initial_path
            self.target_dir = self._add_directory_field('Target folder:', coerce_initial_path(default))
        self.recursive = qt.QCheckBox('Include subfolders')
        self.recursive.setChecked(True)
        self.form.addRow(self.recursive)
        self.results = qt.QTreeWidget()
        self.results.setRootIsDecorated(False)
        self.results.setUniformRowHeights(True)
        self.results.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.results.setAccessibleName(f'{title} results')
        self.summary = qt.QLabel('Choose a folder and run the tool to see results here.')
        self.summary.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.root_layout.insertWidget(self.root_layout.count() - 2, self.results, 1)
        self.root_layout.insertWidget(self.root_layout.count() - 2, self.summary)
        self.resize(950, 600)
        self.cancel_button.setText('Close')
        self.task.completed.connect(self._show_error)

    def _targets(self):
        if self.target_dir is None:
            return self.targets
        target = self._require_directory(self.target_dir)
        return (target,) if target is not None else None

    def _show_error(self, result, error):
        if error:
            self.summary.setText(f'Operation stopped: {error}')

    def _begin(self):
        self.results.clear()
        self.summary.setText('Working…')

    def _row(self, *columns):
        row = qt.QTreeWidgetItem([str(value) for value in columns])
        for index, value in enumerate(columns):
            row.setToolTip(index, str(value))
        self.results.addTopLevelItem(row)


class WeirdCharactersDialog(_ResultsDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__('List Files with Weird Characters',
                         'Find files whose paths contain the configured Unicode characters. This scan is read-only.',
                         'Scan files', False, initial_path, parent)
        self.results.setHeaderLabels(['Path', 'Characters', 'Unicode code points'])
        self.results.setColumnWidth(0, 550)
        self.results.setColumnWidth(1, 130)

    def _execute(self):
        if self.busy:
            return
        target = self._targets()
        if target is None:
            return
        recursive = self.recursive.isChecked()
        self._begin()
        self._run_background(lambda report, cancelled: filesystem.scan_weird_characters(
            target, recursive, report=report, cancelled=cancelled), self._show_results,
            cancel_text='Cancel scan', cancel_message='Cancelling scan…')

    def _show_results(self, matches):
        for path, characters in matches:
            codes = '; '.join(' '.join(f'U+{ord(char):04X}' for char in character) for character in characters)
            self._row(path, ', '.join(characters), codes)
        self.summary.setText(f'Found {len(matches)} files with configured characters in their paths. No files changed.')


class DeletePycDialog(_ResultsDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__('Bulk Delete PYC Files',
                         'Delete Python bytecode (.pyc) files. Python source files and links are preserved. '
                         'Completed deletions cannot be undone.',
                         'Scan PYC files', True, initial_path, parent)
        self.results.setHeaderLabels(['Path', 'Result', 'Details'])
        self.results.setColumnWidth(0, 550)
        self.results.setColumnWidth(1, 130)

        self._pending = None
        self.recursive.toggled.connect(self._invalidate_preview)
        if self.target_dir is not None:
            self.target_dir.textChanged.connect(self._invalidate_preview)
        self.task.completed.connect(lambda result, error: self._invalidate_preview() if error else None)

    def _invalidate_preview(self, *args):
        self._pending = None
        self.action_button.setText('Scan PYC files')

    def _execute(self):
        if self.busy:
            return
        target = self._targets()
        if target is None:
            return
        recursive = self.recursive.isChecked()
        if self._pending is None:
            self._begin()
            self._run_background(lambda report, cancelled: filesystem.scan_pyc_files(
                target, recursive, report=report, cancelled=cancelled), self._show_preview,
                cancel_text='Cancel scan', cancel_message='Cancelling scan…')
            return
        choice = qt.QMessageBox.question(self, self.windowTitle(),
            f'Delete the {len(self._pending)} reviewed .pyc files?\n\n'
            'New or changed files are preserved. Deletions cannot be undone.',
            qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.No,
            qt.QMessageBox.StandardButton.No)
        if choice != qt.QMessageBox.StandardButton.Yes:
            return
        candidates = self._pending
        self._invalidate_preview()
        self._begin()
        self._run_background(lambda report, cancelled: filesystem.cleanup_pyc_files(
            target, recursive, report=report, cancelled=cancelled, candidates=candidates), self._show_results)

    def _show_preview(self, candidates):
        self._pending = candidates or None
        for path, identity in candidates:
            self._row(path, 'Pending deletion', f'{identity[2]:,} bytes')
        self.summary.setText(f'{len(candidates)} bytecode files found · '
                             f'{sum(identity[2] for _, identity in candidates):,} bytes. No files deleted. '
                             'Review these results before confirming deletion.')
        self.action_button.setText('Delete reviewed files…' if candidates else 'Scan PYC files')

    def _show_results(self, result):
        for path in result.completed:
            self._row(path, 'Deleted', '')
        for path, error in result.failed.items():
            self._row(path, 'Failed', str(error))
        for path in result.remaining:
            self._row(path, 'Not deleted', 'Cancelled before processing')
        self.summary.setText(f'{len(result.completed)} deleted · {len(result.failed)} failed · '
                             f'{len(result.remaining)} not deleted.'
                             + (' Cleanup cancelled; completed deletions remain.' if result.cancelled else ''))
