"""Review a dedicated book mirror before copying or deleting any files."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.runtime.operations import OperationCancelled, BatchResult
from features.calibre.export import build_export_plan, execute_export_plan
from desktop.dialogs.tool_dialog import ToolDialog


class ExportDialog(ToolDialog):
    def __init__(self, library, destination=None, parent=None):
        super().__init__('Export books', 'Choose a dedicated export folder. Review every copy and deletion before applying the mirror.',
                         'Review export', True, parent)
        self.library = library
        self.plan = None
        self.destination = self._add_directory_field('Export folder:', str(destination or ''))
        self.destination.textChanged.connect(self._invalidate)
        self.results = qt.QTreeWidget()
        self.results.setHeaderLabels(['Action', 'Destination'])
        self.results.setRootIsDecorated(False)
        self.root_layout.insertWidget(self.root_layout.count() - 2, self.results, 1)
        self.resize(900, 600)

    def _invalidate(self):
        self.plan = None
        self.results.clear()
        self.action_button.setText('Review export')

    def _execute(self):
        if self.busy:
            return
        if self.plan is None:
            target = self._require_directory(self.destination)
            if target is not None:
                self._run_background(lambda report, cancelled: build_export_plan(self.library.path, Path(target), ['epub'], cancelled=cancelled), self._reviewed)
        elif self._confirm():
            plan = self.plan
            def apply(report, cancelled):
                try:
                    return execute_export_plan(plan, cancelled=cancelled, report=report)
                except OperationCancelled:
                    return BatchResult(cancelled=True)
            self._run_background(apply, self._applied)

    def _reviewed(self, plan):
        self.plan = plan
        self.results.clear()
        for entry in plan.files:
            action = 'Copy' if entry.destination_signature is None else 'Update' if entry.needs_copy else 'Keep'
            self.results.addTopLevelItem(qt.QTreeWidgetItem([action, str(entry.destination)]))
        for path, signature in plan.obsolete:
            self.results.addTopLevelItem(qt.QTreeWidgetItem(['Delete', str(path)]))
        self.action_button.setText('Apply reviewed export')
        self.task.message.setText(f'{sum(entry.needs_copy for entry in plan.files)} copies; {len(plan.obsolete)} deletions. ' + '\n'.join(plan.warnings))

    def _applied(self, result):
        self.plan = None
        self.action_button.setText('Review export')
        if getattr(result, 'cancelled', False):
            self.task.message.setText('Cancelled. Completed changes remain; review again before retrying.')
        else:
            self.task.message.setText(f'Copied {result.copied}; updated {result.updated}; deleted {result.deleted}.')
