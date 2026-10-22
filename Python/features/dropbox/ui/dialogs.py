"""Review content before removing identical Dropbox conflict copies."""
from commonUtils.ui import pyside as qt
from features.dropbox import conflicts
from desktop.dialogs.tool_dialog import ToolDialog, coerce_initial_path


class DropboxConflictsDialog(ToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__('Dropbox conflicting copies',
                         'Only byte-identical copies can be removed. Copies with unique edits or missing originals are kept.',
                         'Review conflicting copies', True, parent)
        self.candidates = None
        self.target_dir = self._add_directory_field('Folder:', coerce_initial_path(initial_path))
        self.recursive = qt.QCheckBox('Include subfolders'); self.recursive.setChecked(True)
        self.form.addRow(self.recursive)
        self.results = qt.QTreeWidget()
        self.results.setHeaderLabels(['Conflicting copy', 'Original', 'Result'])
        self.results.setRootIsDecorated(False)
        self.root_layout.insertWidget(self.root_layout.count() - 2, self.results, 1)
        self.target_dir.textChanged.connect(self._invalidate)
        self.recursive.toggled.connect(self._invalidate)
        self.resize(1000, 600)

    def _invalidate(self):
        self.candidates = None
        self.results.clear()
        self.action_button.setText('Review conflicting copies')
        self.action_button.setEnabled(not self.busy)

    def _execute(self):
        if self.busy:
            return
        if self.candidates is None:
            target = self._require_directory(self.target_dir)
            recursive = self.recursive.isChecked()
            if target is not None:
                self._run_background(lambda report, cancelled: conflicts.review_conflicts(target, recursive, cancelled=cancelled), self._reviewed)
        elif self._confirm():
            candidates = self.candidates
            self._run_background(lambda report, cancelled: conflicts.delete_reviewed_conflicts(candidates, report=report, cancelled=cancelled), self._deleted)

    def _reviewed(self, candidates):
        self.candidates = candidates
        self.results.clear()
        for item in candidates:
            self.results.addTopLevelItem(qt.QTreeWidgetItem([
                str(item.path), str(item.original or ''), 'Identical; removable' if item.identical else 'Kept; unique or unknown contents']))
        self.action_button.setText('Delete reviewed identical copies')
        self.action_button.setEnabled(any(item.identical for item in candidates))
        self.task.message.setText(f'{len(candidates)} conflicts; {sum(item.identical for item in candidates)} identical copies.')

    def _deleted(self, result):
        self.candidates = None
        self.action_button.setText('Review conflicting copies')
        self.action_button.setEnabled(not self.busy)
        self.task.message.setText(f'Deleted {len(result.completed)}; failed {len(result.failed)}; unprocessed {len(result.remaining)}. '
                                  + '; '.join(str(error) for error in result.failed.values()))
