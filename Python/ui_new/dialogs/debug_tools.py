"""
Modern dialogs for feature-provided Debug workflows.
"""

from pathlib import Path

from commonUtils import ui
from commonUtils.ui import pyside

from features.comics import actions as comics_actions
from features.comics import cbz, conversion, metadata
from features.dropbox import conflicts
from features.file_tools import filesystem
from features.images import actions as image_actions
from features.media import mka


def _coerce_initial_path(initial_path) -> str:
    if initial_path is None:
        return ''

    if isinstance(initial_path, Path):
        return str(initial_path)

    return str(initial_path)


class _DebugToolDialog(pyside.QDialog):
    def __init__(self, title: str, description: str, action_text: str, destructive: bool, parent=None):
        super().__init__(parent)

        self.action_text = action_text
        self.destructive = destructive

        self.setWindowTitle(title)
        self.setMinimumWidth(620)

        self.root_layout = pyside.QVBoxLayout(self)
        self.root_layout.setContentsMargins(20, 20, 20, 20)
        self.root_layout.setSpacing(14)

        title_label = pyside.QLabel(title)
        title_font = title_label.font()
        title_font.setPointSize(title_font.pointSize() + 5)
        title_font.setBold(True)
        title_label.setFont(title_font)

        description_label = pyside.QLabel(description)
        description_label.setWordWrap(True)

        self.form = pyside.QFormLayout()
        self.form.setHorizontalSpacing(12)
        self.form.setVerticalSpacing(10)

        self.cancel_button = pyside.QPushButton('Cancel')
        self.action_button = pyside.QPushButton(action_text)

        self.root_layout.addWidget(title_label)
        self.root_layout.addWidget(description_label)
        self.root_layout.addLayout(self.form)

        button_layout = pyside.QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.action_button)
        self.root_layout.addLayout(button_layout)

        self.cancel_button.clicked.connect(self.reject)
        self.action_button.clicked.connect(self._execute)
        self.action_button.setDefault(True)

    def _add_directory_field(self, label: str, default: str = '') -> pyside.QLineEdit:
        line_edit = pyside.QLineEdit(default)
        browse = pyside.QPushButton('Browse...')

        row_widget = pyside.QWidget()
        row_layout = pyside.QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        row_layout.addWidget(line_edit, 1)
        row_layout.addWidget(browse)

        browse.clicked.connect(lambda _checked=False, line_edit=line_edit: self._browse_directory(line_edit))
        self.form.addRow(label, row_widget)

        return line_edit

    def _browse_directory(self, line_edit: pyside.QLineEdit):
        start_path = line_edit.text().strip()

        if start_path == '':
            start_path = str(Path.home())

        selected = pyside.QFileDialog.getExistingDirectory(
            self,
            'Select Directory',
            start_path
        )

        if selected:
            line_edit.setText(selected)

    def _require_directory(self, line_edit: pyside.QLineEdit) -> Path | None:
        value = line_edit.text().strip()

        if value == '':
            ui.display_msg_box_ok(
                self.windowTitle(),
                'Choose a target directory first.'
            )
            return None

        return Path(value)

    def _confirm(self) -> bool:
        if not self.destructive:
            return True

        return ui.display_msg_box_ok_cancel(
            self.windowTitle(),
            f'Run "{self.action_text}"?\n\nThis action may modify files.'
        )

    def _execute(self):
        raise NotImplementedError


class ConvertCbrDialog(_DebugToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'Batch Convert CBR to CBZ',
            'Convert CBR archives in a directory to CBZ. Successfully converted CBR files are replaced by CBZ files.',
            'Batch Convert',
            True,
            parent
        )

        self.target_dir = self._add_directory_field('Target folder:', _coerce_initial_path(initial_path))
        self.recursive = pyside.QCheckBox('Include subfolders')
        self.recursive.setChecked(True)
        self.form.addRow('Recursive:', self.recursive)

    def _execute(self):
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        conversion.dir_batch_convert_cbr_to_cbz(target, self.recursive.isChecked())
        self.accept()


class ComicAuthorDialog(_DebugToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'ComicInfo.xml - Set Author from Folder Name',
            'Replace a specific ComicInfo.xml Writer value using each CBZ parent folder name.',
            'Batch Replace Author',
            True,
            parent
        )

        self.target_dir = self._add_directory_field('Target folder:', _coerce_initial_path(initial_path))
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


class ComicSeriesDialog(_DebugToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'ComicInfo.xml - Set Series from Folder Name',
            'Replace a specific ComicInfo.xml Series value using each CBZ parent folder name and an optional prefix.',
            'Batch Replace Series',
            True,
            parent
        )

        self.target_dir = self._add_directory_field('Target folder:', _coerce_initial_path(initial_path))
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


class CbzIndividualFoldersDialog(_DebugToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'Move CBZ into Individual Folders',
            'Create one folder per top-level CBZ file and move each CBZ into its matching folder.',
            'Create Folders and Move',
            True,
            parent
        )

        self.target_dir = self._add_directory_field('Target folder:', _coerce_initial_path(initial_path))

    def _execute(self):
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        comics_actions.move_cbz_to_individual_folders(target)
        self.accept()


class CompressCbzDialog(_DebugToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'Batch Compress CBZ',
            'Compress images inside CBZ archives using the existing Comics compression pipeline.',
            'Batch Compress',
            True,
            parent
        )

        default_path = _coerce_initial_path(initial_path)

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


class WeirdCharactersDialog(_DebugToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'List Files with Weird Characters',
            'Recursively list files whose paths contain configured problematic Unicode characters.',
            'List Files',
            False,
            parent
        )

        default_path = _coerce_initial_path(initial_path)

        if default_path == '':
            default_path = str(Path.home() / 'Server' / 'Local')

        self.target_dir = self._add_directory_field('Target folder:', default_path)

    def _execute(self):
        target = self._require_directory(self.target_dir)

        if target is None:
            return

        filesystem.print_files_with_weird_characters(target, recursive=True)
        self.accept()


class DeletePycDialog(_DebugToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'Bulk Delete PYC Files',
            'Delete .pyc files from the selected directory.',
            'Bulk DELETE',
            True,
            parent
        )

        self.target_dir = self._add_directory_field('Target folder:', _coerce_initial_path(initial_path))
        self.recursive = pyside.QCheckBox('Include subfolders')
        self.recursive.setChecked(True)
        self.form.addRow('Recursive:', self.recursive)

    def _execute(self):
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        filesystem.delete_pyc_files(target, recursive=self.recursive.isChecked())
        self.accept()


class ImageCompressDialog(_DebugToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'Batch Compress Images to WEBP',
            'Compress supported images to WEBP using the existing Images pipeline.',
            'Batch Compress',
            True,
            parent
        )

        default_path = _coerce_initial_path(initial_path)

        if default_path == '':
            default_path = str(image_actions.get_default_compression_path())

        self.target_dir = self._add_directory_field('Target folder:', default_path)

        self.recursive = pyside.QCheckBox('Include subfolders')
        self.recursive.setChecked(True)

        self.always_keep = pyside.QCheckBox('Always keep compressed images')
        self.always_keep.setChecked(False)

        self.quality_color = pyside.QLineEdit('80')
        self.quality_color.setValidator(pyside.QIntValidator(1, 100, self))

        self.quality_grayscale = pyside.QLineEdit('45')
        self.quality_grayscale.setValidator(pyside.QIntValidator(1, 100, self))

        self.enable_max_long_edge = pyside.QCheckBox('Enable')
        self.enable_max_long_edge.setChecked(True)
        self.max_long_edge = pyside.QLineEdit('5120')
        self.max_long_edge.setValidator(pyside.QIntValidator(1, 100000, self))

        self.enable_max_height = pyside.QCheckBox('Enable')
        self.enable_max_height.setChecked(False)
        self.max_height = pyside.QLineEdit('5000')
        self.max_height.setValidator(pyside.QIntValidator(1, 100000, self))

        self.form.addRow('Recursive:', self.recursive)
        self.form.addRow('Compression:', self.always_keep)
        self.form.addRow('Color quality:', self.quality_color)
        self.form.addRow('Grayscale quality:', self.quality_grayscale)
        self.form.addRow('Limit max long edge:', self._create_enabled_value_row(
            self.enable_max_long_edge,
            self.max_long_edge
        ))
        self.form.addRow('Limit max height:', self._create_enabled_value_row(
            self.enable_max_height,
            self.max_height
        ))

    def _create_enabled_value_row(self, checkbox, line_edit):
        widget = pyside.QWidget()
        layout = pyside.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(checkbox)
        layout.addWidget(line_edit, 1)

        checkbox.toggled.connect(line_edit.setEnabled)
        line_edit.setEnabled(checkbox.isChecked())

        return widget

    def _execute(self):
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        max_long_edge = int(self.max_long_edge.text()) if self.enable_max_long_edge.isChecked() else None
        max_height = int(self.max_height.text()) if self.enable_max_height.isChecked() else None

        image_actions.batch_compress_to_webp(
            target_dir=target,
            recursive=self.recursive.isChecked(),
            always_keep_compressed=self.always_keep.isChecked(),
            quality_color=int(self.quality_color.text()),
            quality_grayscale=int(self.quality_grayscale.text()),
            max_long_edge=max_long_edge,
            max_height=max_height
        )
        self.accept()


class ExifCommentsDialog(_DebugToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'JPG EXIF - Batch Set Comments',
            'Set the EXIF Comments field on JPG files in the selected directory.',
            'Batch Set EXIF Comments',
            True,
            parent
        )

        self.target_dir = self._add_directory_field('Target folder:', _coerce_initial_path(initial_path))

        self.recursive = pyside.QCheckBox('Include subfolders')
        self.recursive.setChecked(True)

        self.comments = pyside.QLineEdit()

        self.form.addRow('Recursive:', self.recursive)
        self.form.addRow('Comments:', self.comments)

    def _execute(self):
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        image_actions.set_jpg_exif_comments(
            target_dir=target,
            recursive=self.recursive.isChecked(),
            comments=self.comments.text()
        )
        self.accept()


class RenameMkaDialog(_DebugToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'Rename MKA from CSV',
            'Rename Chapter_XX.mka files using chapter names from the directory CSV file.',
            'Batch Rename',
            True,
            parent
        )

        self.target_dir = self._add_directory_field('Target folder:', _coerce_initial_path(initial_path))

    def _execute(self):
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        mka.rename_from_csv(target)
        self.accept()


class DropboxConflictsDialog(pyside.QDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(parent)

        self.setWindowTitle('Dropbox Conflicting Copies')
        self.setMinimumWidth(620)

        root_layout = pyside.QVBoxLayout(self)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(14)

        title = pyside.QLabel('Dropbox Conflicting Copies')
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 5)
        title_font.setBold(True)
        title.setFont(title_font)

        description = pyside.QLabel(
            'Analyze Dropbox conflicted-copy files or delete them only when the existing safety checks confirm '
            'that every conflict still has its original.'
        )
        description.setWordWrap(True)

        form = pyside.QFormLayout()
        self.target_dir = pyside.QLineEdit(_coerce_initial_path(initial_path))

        browse_button = pyside.QPushButton('Browse...')
        target_widget = pyside.QWidget()
        target_layout = pyside.QHBoxLayout(target_widget)
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(8)
        target_layout.addWidget(self.target_dir, 1)
        target_layout.addWidget(browse_button)

        self.recursive = pyside.QCheckBox('Include subfolders')
        self.recursive.setChecked(True)

        form.addRow('Target folder:', target_widget)
        form.addRow('Recursive:', self.recursive)

        report_button = pyside.QPushButton('Print Conflicting Copies')
        delete_button = pyside.QPushButton('Delete Conflicting Copies')
        close_button = pyside.QPushButton('Close')

        action_layout = pyside.QHBoxLayout()
        action_layout.addWidget(report_button)
        action_layout.addWidget(delete_button)

        close_layout = pyside.QHBoxLayout()
        close_layout.addStretch()
        close_layout.addWidget(close_button)

        root_layout.addWidget(title)
        root_layout.addWidget(description)
        root_layout.addLayout(form)
        root_layout.addLayout(action_layout)
        root_layout.addLayout(close_layout)

        browse_button.clicked.connect(self._browse)
        report_button.clicked.connect(self._report)
        delete_button.clicked.connect(self._delete)
        close_button.clicked.connect(self.accept)

    def _browse(self):
        start_path = self.target_dir.text().strip() or str(Path.home())

        selected = pyside.QFileDialog.getExistingDirectory(
            self,
            'Select Directory',
            start_path
        )

        if selected:
            self.target_dir.setText(selected)

    def _get_target(self):
        value = self.target_dir.text().strip()

        if value == '':
            ui.display_msg_box_ok(
                'Dropbox Conflicting Copies',
                'Choose a target directory first.'
            )
            return None

        return Path(value)

    def _report(self):
        target = self._get_target()

        if target is None:
            return

        conflicts.print_conflicting_copies(
            target,
            recursive=self.recursive.isChecked()
        )

    def _delete(self):
        target = self._get_target()

        if target is None:
            return

        confirmed = ui.display_msg_box_ok_cancel(
            'Delete Conflicting Copies',
            'Delete Dropbox conflicting-copy files that pass the existing safety checks?'
        )

        if not confirmed:
            return

        conflicts.delete_conflicting_copies(
            target,
            recursive=self.recursive.isChecked()
        )


_DIALOGS = {
    'debug_comics_convert_cbr': ConvertCbrDialog,
    'debug_comics_author': ComicAuthorDialog,
    'debug_comics_series': ComicSeriesDialog,
    'debug_comics_individual_folders': CbzIndividualFoldersDialog,
    'debug_comics_compress_cbz': CompressCbzDialog,
    'debug_file_tools_weird_chars': WeirdCharactersDialog,
    'debug_file_tools_delete_pyc': DeletePycDialog,
    'debug_images_compress': ImageCompressDialog,
    'debug_images_exif_comments': ExifCommentsDialog,
    'debug_media_rename_mka': RenameMkaDialog,
    'debug_dropbox_conflicts': DropboxConflictsDialog,
}


def open_debug_tool(workflow_id: str, data=None, parent=None):
    """Open one registered Debug workflow dialog."""

    dialog_type = _DIALOGS.get(workflow_id)

    if dialog_type is None:
        raise ValueError(f'Unknown Debug workflow: {workflow_id}')

    dialog = dialog_type(initial_path=data, parent=parent)
    return dialog.exec()
