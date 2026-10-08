"""
Comics-specific workflow dialogs.
"""

from commonUtils import ui
from commonUtils.ui import pyside

from features.comics import actions as comics_actions
from features.comics import cbz, conversion, metadata
from ui_new.dialogs.tool_dialog import ToolDialog, coerce_initial_path


class ComicsToolDialog(ToolDialog):
    def _run_background(self, work, completed):
        super()._run_background(work, completed, cancel_text='Cancel after current comic',
            cancel_message='Cancellation requested. Finishing and verifying the current comic…')

    def _batch_completed(self, result):
        prefix = 'Cancelled. ' if result.cancelled else ''
        self.task.message.setText(prefix + f'{len(result.completed)} completed; {len(result.failed)} failed; '
                                  f'{len(result.remaining)} not processed.'
                                  + ''.join(f'\n{path}: {error}' for path, error in result.failed.items()))
        if result:
            self.accept()
        elif not result.completed and not result.failed and not result.cancelled:
            self.task.message.setText('No matching comics were found.')

    def _require_directory(self, line_edit):
        target = super()._require_directory(line_edit)
        if target is not None and not target.is_dir():
            ui.display_msg_box_ok(self.windowTitle(), 'Choose an existing directory.')
            return None
        return target


class ConvertCbrDialog(ComicsToolDialog):
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
        if self.busy:
            return
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        recursive = self.recursive.isChecked()
        self._run_background(lambda progress, cancelled: conversion.dir_batch_convert_cbr_to_cbz(
            target, recursive, progress=progress, cancelled=cancelled, report=True), self._batch_completed)

class ComicAuthorDialog(ComicsToolDialog):
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
        if self.busy:
            return
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        tag = self.existing_tag.text()
        self._run_background(lambda progress, cancelled: metadata.batch_rename_author_to_dir_name(
            target, tag, progress=progress, cancelled=cancelled, report=True), self._batch_completed)

class ComicSeriesDialog(ComicsToolDialog):
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
        if self.busy:
            return
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        tag, prefix = self.existing_tag.text(), self.prefix.text()
        self._run_background(lambda progress, cancelled: metadata.batch_rename_series_to_dir_name(
            target, tag, prefix, progress=progress, cancelled=cancelled, report=True), self._batch_completed)

class CbzIndividualFoldersDialog(ComicsToolDialog):
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
        if self.busy:
            return
        target = self._require_directory(self.target_dir)

        if target is None or not self._confirm():
            return

        self._run_background(lambda progress, cancelled: comics_actions.move_cbz_to_individual_folders(
            target, progress=progress, cancelled=cancelled, report=True), self._batch_completed)

class CompressCbzDialog(ComicsToolDialog):
    def __init__(self, initial_path=None, parent=None, *, targets=None):
        super().__init__(
            'Batch Compress CBZ',
            'Compress images inside CBZ archives using the existing Comics compression pipeline.',
            'Batch Compress',
            True,
            parent
        )

        from features.comics.selection import normalize_targets
        self.targets = normalize_targets(targets) if targets is not None else None
        self.target_dir = None
        if self.targets is None:
            default_path = coerce_initial_path(initial_path) or str(cbz.default_path_to_convert_cbz)
            self.target_dir = self._add_directory_field('Target folder:', default_path)
        else:
            summary = pyside.QLabel(f'{len(self.targets)} selected file(s)/folder(s)')
            summary.setToolTip('\n'.join(str(path) for path in self.targets))
            if len(self.targets) == 1:
                summary.setText(str(self.targets[0]))
            summary.setWordWrap(True)
            summary.setTextFormat(pyside.Qt.TextFormat.PlainText)
            self.form.addRow('Selection:', summary)

        self.recursive = pyside.QCheckBox('Include subfolders')
        self.recursive.setChecked(True)

        self.always_keep = pyside.QCheckBox('Always keep compressed images')
        self.always_keep.setChecked(False)

        self.preserve_originals = pyside.QCheckBox('Preserve animated and multipage originals')
        self.preserve_originals.setChecked(True)
        preserve_help = pyside.QLabel('Cannot be used at same time as always keep compressed images.')
        preserve_help.setWordWrap(True)
        self.preserve_originals.setToolTip(preserve_help.text())

        self.form.addRow('Recursive:', self.recursive)
        self.form.addRow('Compression:', self.always_keep)
        self.form.addRow('', self.preserve_originals)
        self.form.addRow('', preserve_help)

    def _execute(self):
        if self.busy:
            return
        if not cbz.validate_compression_options(
                self.always_keep.isChecked(), self.preserve_originals.isChecked()):
            ui.display_msg_box_ok(self.windowTitle(), self.preserve_originals.toolTip())
            return
        target = self._require_directory(self.target_dir) if self.targets is None else self.targets
        if target is None or not self._confirm():
            return

        options = dict(recursive=self.recursive.isChecked(),
                       always_keep_compressed=self.always_keep.isChecked(),
                       preserve_animated_and_multipage_originals=self.preserve_originals.isChecked())
        compress = cbz.batch_compress_cbz if self.targets is None else cbz.compress_selected_cbz
        self._run_background(lambda progress, cancelled: compress(
            target, **options, progress=progress, cancelled=cancelled), self._compressed)

    def _compressed(self, stats):
        if stats is None:
            self.task.message.setText('Compression could not start. Check the selected options and log.')
            return
        prefix = 'Cancelled. ' if stats.cancelled else ''
        self.task.message.setText(prefix +
            f'{stats.compressed_file_count} compressed; {stats.already_compressed_file_count} already compressed; '
            f'{stats.error_during_compression} failed; {len(stats.remaining)} not processed.'
            + ''.join(f'\n{path}: {error}' for path, error in stats.failed.items()))
        if not stats.cancelled and not stats.error_during_compression:
            self.accept()
