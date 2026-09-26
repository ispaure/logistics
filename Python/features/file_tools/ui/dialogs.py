"""
File Tools workflow dialogs.
"""

from pathlib import Path

from commonUtils.ui import pyside

from features.file_tools import filesystem
from ui_new.dialogs.tool_dialog import ToolDialog, coerce_initial_path


class WeirdCharactersDialog(ToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'List Files with Weird Characters',
            'Recursively list files whose paths contain configured problematic Unicode characters.',
            'List Files',
            False,
            parent
        )

        default_path = coerce_initial_path(initial_path)

        if default_path == '':
            default_path = str(Path.home() / 'Server' / 'Local')

        self.target_dir = self._add_directory_field('Target folder:', default_path)

    def _execute(self):
        target = self._require_directory(self.target_dir)

        if target is None:
            return

        filesystem.print_files_with_weird_characters(target, recursive=True)
        self.accept()

class DeletePycDialog(ToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'Bulk Delete PYC Files',
            'Delete .pyc files from the selected directory.',
            'Bulk DELETE',
            True,
            parent
        )

        self.target_dir = self._add_directory_field('Target folder:', coerce_initial_path(initial_path))
        self.recursive = pyside.QCheckBox('Include subfolders')
        self.recursive.setChecked(True)
        self.form.addRow('Recursive:', self.recursive)

    def _execute(self):
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        filesystem.delete_pyc_files(target, recursive=self.recursive.isChecked())
        self.accept()
