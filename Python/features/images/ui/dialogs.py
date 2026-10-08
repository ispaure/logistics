"""
Images workflow dialogs.
"""

from commonUtils import ui
from commonUtils.ui import pyside

from features.images import actions as image_actions
from features.images import processing
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

        self.targets = tuple(initial_path) if isinstance(initial_path, (tuple, list)) else ()
        if len(self.targets) > 1:
            target_label = pyside.QLabel('\n'.join(str(path) for path in self.targets))
            target_label.setTextFormat(pyside.Qt.TextFormat.PlainText)
            self.form.addRow('Target folders:', target_label)
            self.target_dir = None
        else:
            default_path = str(self.targets[0]) if self.targets else default_path
            self.target_dir = self._add_directory_field('Target folder:', default_path)

        self.recursive = pyside.QCheckBox('Include subfolders')
        self.recursive.setChecked(True)

        self.exclude_webp = pyside.QCheckBox('Exclude existing WebP images')
        self.exclude_webp.setChecked(True)
        self.exclude_webp.setToolTip('Skip .webp inputs to avoid recompressing images on repeated runs.')

        self.always_keep = pyside.QCheckBox('Always keep compressed images')
        self.always_keep.setChecked(False)
        self.preserve_originals = pyside.QCheckBox('Preserve animated and multipage originals')
        self.preserve_originals.setChecked(True)
        preserve_help = pyside.QLabel('Cannot be used at same time as always keep compressed images.')
        preserve_help.setWordWrap(True)
        self.preserve_originals.setToolTip(preserve_help.text())

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
        self.form.addRow('Input files:', self.exclude_webp)
        self.form.addRow('Compression:', self.always_keep)
        self.form.addRow('', self.preserve_originals)
        self.form.addRow('', preserve_help)
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

        self.results = pyside.QTreeWidget()
        self.results.setHeaderLabels(['Image', 'Result', 'Details'])
        self.results.setRootIsDecorated(False)
        self.results.setColumnWidth(0, 420)
        self.results.setColumnWidth(1, 260)
        self.summary = pyside.QLabel('Results appear here after compression.')
        self.summary.setTextFormat(pyside.Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.root_layout.insertWidget(self.root_layout.count() - 2, self.results, 1)
        self.root_layout.insertWidget(self.root_layout.count() - 2, self.summary)
        self.task.completed.connect(lambda result, error: self.summary.setText(error) if error else None)
        self.cancel_button.setText('Close')
        self.resize(1000, 800)

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
        if not processing.validate_compression_options(
                self.always_keep.isChecked(), self.preserve_originals.isChecked()):
            ui.display_msg_box_ok(self.windowTitle(), self.preserve_originals.toolTip())
            return
        if self.busy:
            return
        if self.target_dir is None:
            targets = self.targets
        else:
            target = self._require_directory(self.target_dir)
            if target is None:
                return
            targets = (target,)
        from services.folder_safety import require_safe_folder
        try:
            targets = tuple(require_safe_folder(target, recursive=self.recursive.isChecked()) for target in targets)
        except (OSError, ValueError) as error:
            self.summary.setText(str(error))
            return

        if any(not field.hasAcceptableInput() for field in (
                self.quality_color, self.quality_grayscale,
                *([self.max_long_edge] if self.enable_max_long_edge.isChecked() else []),
                *([self.max_height] if self.enable_max_height.isChecked() else []))):
            ui.display_msg_box_ok(self.windowTitle(), 'Enter valid quality and size values.')
            return
        if not self._confirm():
            return
        options = dict(
            recursive=self.recursive.isChecked(),
            always_keep_compressed=self.always_keep.isChecked(),
            quality_color=int(self.quality_color.text()), quality_grayscale=int(self.quality_grayscale.text()),
            max_long_edge=int(self.max_long_edge.text()) if self.enable_max_long_edge.isChecked() else None,
            max_height=int(self.max_height.text()) if self.enable_max_height.isChecked() else None,
            preserve_animated_and_multipage_originals=self.preserve_originals.isChecked(),
            exclude_webp=self.exclude_webp.isChecked())
        self.results.clear()
        self.summary.setText('Compressing images…')
        self._run_background(lambda report, cancelled: image_actions.compress_folders(
            targets, report=report, cancelled=cancelled, **options), self._show_results,
            cancel_text='Cancel after current image',
            cancel_message='Finishing the current image before cancellation…')

    def _show_results(self, result):
        batch, outcomes = result
        rows = [(path, outcomes[path], '') for path in batch.completed]
        rows += [(path, 'Failed', str(error)) for path, error in batch.failed.items()]
        rows += [(path, 'Not processed', 'Cancelled') for path in batch.remaining]
        for path, status, detail in rows:
            row = pyside.QTreeWidgetItem([str(path), status, detail])
            row.setToolTip(0, str(path))
            row.setToolTip(2, detail)
            self.results.addTopLevelItem(row)
        self.summary.setText(f'{len(batch.completed)} processed · {len(batch.failed)} failed · '
                             f'{len(batch.remaining)} not processed.'
                             + (' Cancelled; completed conversions remain.' if batch.cancelled else ''))


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
