"""
Media workflow dialogs.
"""

from features.media import mka
from ui_new.dialogs.tool_dialog import ToolDialog, coerce_initial_path


class RenameMkaDialog(ToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'Rename MKA from CSV',
            'Rename Chapter_XX.mka files using chapter names from the directory CSV file.',
            'Batch Rename',
            True,
            parent
        )

        self.target_dir = self._add_directory_field('Target folder:', coerce_initial_path(initial_path))

    def _execute(self):
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        mka.rename_from_csv(target)
        self.accept()
