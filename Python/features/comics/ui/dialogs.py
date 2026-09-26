"""
Comics-specific workflow dialogs.
"""

from commonUtils.ui import pyside

from features.comics import actions as comics_actions
from features.comics import cbz, conversion, metadata
from ui_new.dialogs.tool_dialog import ToolDialog, coerce_initial_path


class ConvertCbrDialog(ToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'Batch Convert CBR to CBZ',
            'Convert CBR archives in a directory to CBZ. Successfully converted CBR files are replaced by CBZ files.',
            'Batch Convert',
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

        conversion.dir_batch_convert_cbr_to_cbz(target, self.recursive.isChecked())
        self.accept()

class ComicAuthorDialog(ToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'ComicInfo.xml - Set Author from Folder Name',
            'Replace a specific ComicInfo.xml Writer value using each CBZ parent folder name.',
            'Batch Replace Author',
            True,
            parent
        )

        self.target_dir = self._add_directory_field('Target folder:', coerce_initial_path(initial_path))
        self.existing_tag = pyside.QLineEdit('REPLACEAUTHORHERE')
        self.form.addRow('Existing author tag:', self.existing_tag)

    def _execute(self):
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        metadata.batch_rename_author_to_dir_name(
            target_dir=target,
            author_tag_to_replace=self.existing_tag.text()
        )
        self.accept()

class ComicSeriesDialog(ToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'ComicInfo.xml - Set Series from Folder Name',
            'Replace a specific ComicInfo.xml Series value using each CBZ parent folder name and an optional prefix.',
            'Batch Replace Series',
            True,
            parent
        )

        self.target_dir = self._add_directory_field('Target folder:', coerce_initial_path(initial_path))
        self.existing_tag = pyside.QLineEdit('REPLACESERIESHERE')
        self.prefix = pyside.QLineEdit()

        self.form.addRow('Existing series tag:', self.existing_tag)
        self.form.addRow('Series prefix:', self.prefix)

    def _execute(self):
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        metadata.batch_rename_series_to_dir_name(
            target_dir=target,
            series_tag_to_replace=self.existing_tag.text(),
            suffix=self.prefix.text()
        )
        self.accept()

class CbzIndividualFoldersDialog(ToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'Move CBZ into Individual Folders',
            'Create one folder per top-level CBZ file and move each CBZ into its matching folder.',
            'Create Folders and Move',
            True,
            parent
        )

        self.target_dir = self._add_directory_field('Target folder:', coerce_initial_path(initial_path))

    def _execute(self):
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        comics_actions.move_cbz_to_individual_folders(target)
        self.accept()

class CompressCbzDialog(ToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'Batch Compress CBZ',
            'Compress images inside CBZ archives using the existing Comics compression pipeline.',
            'Batch Compress',
            True,
            parent
        )

        default_path = coerce_initial_path(initial_path)

        if default_path == '':
            default_path = str(cbz.default_path_to_convert_cbz)

        self.target_dir = self._add_directory_field('Target folder:', default_path)

        self.recursive = pyside.QCheckBox('Include subfolders')
        self.recursive.setChecked(True)

        self.always_keep = pyside.QCheckBox('Always keep compressed images')
        self.always_keep.setChecked(False)

        self.form.addRow('Recursive:', self.recursive)
        self.form.addRow('Compression:', self.always_keep)

    def _execute(self):
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        cbz.batch_compress_cbz(
            target_dir=target,
            recursive=self.recursive.isChecked(),
            always_keep_compressed=self.always_keep.isChecked()
        )
        self.accept()
