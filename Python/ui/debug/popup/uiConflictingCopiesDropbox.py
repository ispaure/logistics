from commonUtils.pySideUtils import *
from commonUtils.debugUtils import *
from pathlib import Path
show_verbose = True


def print_conflicting_copies_dropbox(convert_arg):

    conflict_tool_name: str = 'Conflicting Copies Report'
    directory = convert_arg['target_dir'].txt()
    recursive = convert_arg['recursive'].isChecked()

    # Get list of Files
    file_lst = fileUtils.get_file_list_from_path(directory, recursive=recursive)

    # Conflicting file list
    conflicting_file_lst: List[fileUtils.File] = []

    for file in file_lst:
        name_no_ext = file.name_without_ext
        if ' conflicted copy ' in name_no_ext and ' (' in name_no_ext and ')' in name_no_ext:
            conflicting_file_lst.append(file)

    # Conflicting file without original
    conflict_file_no_original_lst: List[fileUtils.File] = []
    # Conflicting files with original
    conflict_file_with_original_lst: List[fileUtils.File] = []
    # Unsure how to process
    conflict_file_unsure_process_lst: List[fileUtils.File] = []

    for file in conflicting_file_lst:
        # Can we test for this file?
        if file.name_without_ext.count(' (') != 1:
            conflict_file_unsure_process_lst.append(file)
            continue

        # Expected OG file name
        og_name = file.name_without_ext.split(' (')[0]
        parent = file.path.parent
        og_path: Path = parent / f'{og_name}.{file.ext}'

        # OG file exists
        og_lower = str(og_path).lower()

        if os.path.isfile(og_lower):
            conflict_file_with_original_lst.append(file)
        else:
            conflict_file_no_original_lst.append(file)

    # Gather message

    # Has original
    conflict_has_original_msg = f'Conflict Files with Original ({len(conflict_file_with_original_lst)}):\n'
    for file in conflict_file_with_original_lst:
        conflict_has_original_msg += f' - {file.path}\n'
    log(Severity.INFO, conflict_tool_name, conflict_has_original_msg)

    # No original
    conflict_no_original_msg = f'Conflict Files without Original ({len(conflict_file_no_original_lst)})\n'
    for file in conflict_file_no_original_lst:
        conflict_no_original_msg += f' - {file.path}\n'
    if len(conflict_file_no_original_lst) == 0:
        severity = Severity.INFO
    else:
        severity = Severity.ERROR
    log(severity, conflict_tool_name, conflict_no_original_msg)

    # Could not evaluate properly
    conflict_unsure_process_msg = f'Conflict Files cannot process ({len(conflict_file_unsure_process_lst)})\n'
    for file in conflict_file_unsure_process_lst:
        conflict_unsure_process_msg += f' - {file.path}\n'
    if len(conflict_file_unsure_process_lst) == 0:
        severity = Severity.INFO
    else:
        severity = Severity.CRITICAL
    log(severity, conflict_tool_name, conflict_unsure_process_msg)


def delete_conflicting_copies_dropbox(convert_arg):
    pass


class ConflictingCopiesDropbox(Window):
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
        Label('Target Folder: ', self.dlg, QRect(10, 12, 400, 20))
        # Create Argument
        convert_arg['target_dir'] = LineEdit('', self.dlg, QRect(105, 10, 370, 25))

        # 2. Recursive
        # Create Label
        Label('Recursive (Include Subfolders): ', self.dlg, QRect(10, 43, 400, 20))
        # Create Argument
        convert_arg['recursive'] = create_checkbox(self.dlg, QRect(205, 28, 50, 50), default_state=True)

        # --- BUTTON ---
        button('Print Conflicting Copies', self.dlg, QRect(5, 80, 480, 30), print_conflicting_copies_dropbox, convert_arg)
        button('Delete Conflicting Copies', self.dlg, QRect(5, 115, 480, 30), delete_conflicting_copies_dropbox, convert_arg)

        # --------------------------------------------------------------------------------------------------------------
