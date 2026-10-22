"""Review chapter names before applying a CSV rename."""
from commonUtils.ui import pyside as qt
from commonUtils.filesystem.rename import apply_renames
from features.media import mka
from desktop.dialogs.tool_dialog import ToolDialog, coerce_initial_path


class RenameMkaDialog(ToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__('Rename MKA from CSV',
                         'Review chapter names from the folder’s CSV before renaming files.',
                         'Review names', True, parent)
        self.plan = None
        self.target_dir = self._add_directory_field('Target folder:', coerce_initial_path(initial_path))
        self.target_dir.textChanged.connect(self._invalidate)
        self.results = qt.QTreeWidget()
        self.results.setHeaderLabels(['Current name', 'New name'])
        self.results.setRootIsDecorated(False)
        self.root_layout.insertWidget(self.root_layout.count() - 2, self.results, 1)

    def _invalidate(self):
        self.plan = None
        self.results.clear()
        self.action_button.setText('Review names')

    def _execute(self):
        if self.busy:
            return
        if self.plan is None:
            target = self._require_directory(self.target_dir)
            if target is not None:
                self._run_background(lambda report, cancelled: mka.plan_from_csv(target), self._reviewed)
        elif self._confirm():
            plan = self.plan
            self._run_background(lambda report, cancelled: apply_renames(plan, cancelled=cancelled), self._applied)

    def _reviewed(self, plan):
        if plan is None:
            self.task.message.setText('No valid rename plan. Check the CSV, chapter numbers and destination names.')
            return
        self.plan = plan
        for entry in plan.entries:
            self.results.addTopLevelItem(qt.QTreeWidgetItem([entry.source.name, entry.target.name]))
        self.action_button.setText('Apply reviewed names')
        self.task.message.setText(f'{len(plan.changes)} files to rename.')

    def _applied(self, result):
        self.plan = None
        self.action_button.setText('Review names')
        if result.success:
            self.task.message.setText(f'Renamed {len(result.entries)} files.')
        else:
            recovery = '\n'.join(f'{current} → {original}: {error}' for current, original, error in result.recovery)
            self.task.message.setText(f'Rename stopped: {result.error}\n{recovery}')
