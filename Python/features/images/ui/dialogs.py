"""
Images workflow dialogs.
"""

from commonUtils.ui import pyside

from features.images import actions as image_actions
from ui_new.dialogs.tool_dialog import ToolDialog, coerce_initial_path


class ImageCompressDialog(ToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'Batch Compress Images to WEBP',
            'Compress supported images to WEBP using the existing Images pipeline.',
            'Batch Compress',
            True,
            parent
        )

        default_path = coerce_initial_path(initial_path)

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

class ExifCommentsDialog(ToolDialog):
    def __init__(self, initial_path=None, parent=None):
        super().__init__(
            'JPG EXIF - Batch Set Comments',
            'Set the EXIF Comments field on JPG files in the selected directory.',
            'Batch Set EXIF Comments',
            True,
            parent
        )

        self.target_dir = self._add_directory_field('Target folder:', coerce_initial_path(initial_path))

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
