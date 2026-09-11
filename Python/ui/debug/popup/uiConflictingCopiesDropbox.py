from commonUtils.ui import pyside
from commonUtils.debugUtils import *
from commonUtils import dirUtils, fileUtils
from pathlib import Path
from typing import List

show_verbose = True


def analyze_conflicting_copies(file_lst: List[fileUtils.File]):
    """
    Analyze Dropbox conflicting copies and classify them.

    Returns:
        (with_original, without_original, unsure)
    """

    conflicting_file_lst: List[fileUtils.File] = []

    # Step 1: detect conflicts
    for file in file_lst:
        name_no_ext = file.name_without_ext
        if ' conflicted copy ' in name_no_ext and ' (' in name_no_ext and ')' in name_no_ext:
            conflicting_file_lst.append(file)

    # Step 2: classify
    conflict_file_no_original_lst: List[fileUtils.File] = []
    conflict_file_with_original_lst: List[fileUtils.File] = []
    conflict_file_unsure_process_lst: List[fileUtils.File] = []

    for file in conflicting_file_lst:

        # Ambiguous naming
        if file.name_without_ext.count(' (') != 1:
            conflict_file_unsure_process_lst.append(file)
            continue

        og_name = file.name_without_ext.split(' (')[0]
        parent = file.path.parent

        if file.ext:
            og_path = parent / f"{og_name}.{file.ext}"
        else:
            og_path = parent / og_name

        if og_path.exists():
            conflict_file_with_original_lst.append(file)
        else:
            conflict_file_no_original_lst.append(file)

    return (
        conflict_file_with_original_lst,
        conflict_file_no_original_lst,
        conflict_file_unsure_process_lst
    )


def print_conflicting_copies_dropbox(convert_arg):

    conflict_tool_name = 'Conflicting Copies Report'
    directory = dirUtils.Directory(Path(convert_arg['target_dir'].txt()))
    recursive = convert_arg['recursive'].isChecked()

    file_lst = directory.list_files(recursive=recursive)

    with_original, no_original, unsure = analyze_conflicting_copies(file_lst)

    # With original
    msg = f'Conflict Files with Original ({len(with_original)}):\n'
    for file in with_original:
        msg += f' - {file.path}\n'
    log(Severity.INFO, conflict_tool_name, msg)

    # Without original
    msg = f'Conflict Files without Original ({len(no_original)}):\n'
    for file in no_original:
        msg += f' - {file.path}\n'
    severity = Severity.INFO if not no_original else Severity.ERROR
    log(severity, conflict_tool_name, msg)

    # Unsure
    msg = f'Conflict Files cannot process ({len(unsure)}):\n'
    for file in unsure:
        msg += f' - {file.path}\n'
    severity = Severity.INFO if not unsure else Severity.CRITICAL
    log(severity, conflict_tool_name, msg)


def delete_conflicting_copies_dropbox(convert_arg):

    conflict_tool_name = 'Delete Conflicting Copies'
    directory = dirUtils.Directory(Path(convert_arg['target_dir'].txt()))
    recursive = convert_arg['recursive'].isChecked()

    file_lst = directory.list_files(recursive=recursive)

    with_original, no_original, unsure = analyze_conflicting_copies(file_lst)

    # Safety check: abort if anything is not clean
    if no_original or unsure:
        msg = "Deletion aborted. Resolve conflicts before proceeding:\n"

        if no_original:
            msg += f'\nFiles WITHOUT original ({len(no_original)}):\n'
            for file in no_original:
                msg += f' - {file.path}\n'

        if unsure:
            msg += f'\nFiles that could NOT be processed safely ({len(unsure)}):\n'
            for file in unsure:
                msg += f' - {file.path}\n'

        log(Severity.CRITICAL, conflict_tool_name, msg)
        return

    # Safe to proceed (all have originals)
    deleted = []
    failed = []

    for file in with_original:
        try:
            result = file.delete_file()
            if result:
                deleted.append(file)
            else:
                failed.append(file)
        except Exception as e:
            failed.append(file)
            log(Severity.ERROR, conflict_tool_name, f'Error deleting {file.path}: {e}')

    # Report
    msg = f'Deleted {len(deleted)} conflicting files (all had originals):\n'
    for file in deleted:
        msg += f' - {file.path}\n'
    log(Severity.INFO, conflict_tool_name, msg)

    if failed:
        msg = f'Failed to delete {len(failed)} files:\n'
        for file in failed:
            msg += f' - {file.path}\n'
        log(Severity.ERROR, conflict_tool_name, msg)


class ConflictingCopiesDropbox(pyside.Window):
    def __init__(self):
        super().__init__('Conflicting Copies in Dropbox')

        # Set dimensions
        self.width = 500
        self.height = 150

        # CONFLICTING COPIES DROPBOX -----------------------------------------------------------------------------------

        # --- OPTIONS ---
        # Arguments Dict
        convert_arg = {}

        # 1. Target Folder
        # Create Label
        pyside.Label('Target Folder: ', self.dlg, pyside.QRect(10, 12, 400, 20))
        # Create Argument
        convert_arg['target_dir'] = pyside.LineEdit('', self.dlg, pyside.QRect(105, 10, 370, 25))

        # 2. Recursive
        # Create Label
        pyside.Label('Recursive (Include Subfolders): ', self.dlg, pyside.QRect(10, 43, 400, 20))
        # Create Argument
        convert_arg['recursive'] = pyside.create_checkbox(
            self.dlg, pyside.QRect(205, 28, 50, 50), default_state=True
        )

        # --- BUTTON ---
        pyside.button('Print Conflicting Copies', self.dlg, pyside.QRect(5, 80, 480, 30),
                      print_conflicting_copies_dropbox, convert_arg)
        pyside.button('Delete Conflicting Copies', self.dlg, pyside.QRect(5, 115, 480, 30),
                      delete_conflicting_copies_dropbox, convert_arg)

        # --------------------------------------------------------------------------------------------------------------