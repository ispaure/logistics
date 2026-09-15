from pathlib import Path
from typing import List

from commonUtils.ui import pyside
from commonUtils import fileUtils, dirUtils, spreadsheetUtils
from commonUtils.debugUtils import *

show_verbose = True
tool_name = 'Batch Rename MKA from CSV'


def ui_rename_mka_from_csv(convert_arg):
    target_dir = dirUtils.Directory(Path(convert_arg['target_dir'].txt()))

    # Make sure Target Dir is indeed a directory
    if not target_dir.is_dir():
        log(Severity.ERROR, tool_name, 'Invalid Directory Path')
        return

    # Load the CSV file
    csv_file_lst: List[fileUtils.File] = target_dir.list_files(recursive=False, filter_extension='csv')

    if len(csv_file_lst) == 0:
        log(Severity.ERROR, tool_name, '.CSV file missing from root of directory')
        return

    if len(csv_file_lst) > 1:
        log(Severity.ERROR, tool_name, 'More than one .CSV file in directory')
        return

    csv_file = csv_file_lst[0]

    if not isinstance(csv_file, fileUtils.CSVFile):
        log(Severity.ERROR, tool_name, f'Expected CSVFile, got {type(csv_file).__name__}')
        return

    chapter_name_sh = spreadsheetUtils.Spreadsheet('Chapter Names')
    chapter_name_sh.import_file(csv_file)
    row_lst = chapter_name_sh.get_rows()

    # List files in directory
    mka_file_lst: List[fileUtils.File] = target_dir.list_files(recursive=False, filter_extension='mka')

    for mka_file in mka_file_lst:

        # Get the Chapter Number, Throw Error if File Naming is not Perfectly Chapter_XX.mka
        file_num_str = mka_file.name_without_ext.replace('Chapter_', '')

        if not file_num_str.isdigit():
            log(Severity.ERROR, tool_name, f'File {mka_file.file_name} contains invalid naming (should be Chapter_XX.mka)')
            return

        file_num_int = int(file_num_str)

        if file_num_int > len(row_lst):
            log(Severity.ERROR, tool_name, f'File {mka_file.file_name} does not have a chapter name in rows of .CSV file')
            return

        row = row_lst[file_num_int - 1]

        if row.get_cell(0).txt != str(file_num_int):
            log(Severity.ERROR, tool_name, f'File {mka_file.file_name} does not have proper chapter markings in column A (found {row.get_cell(0).txt} instead of {file_num_int})')
            return

        chapter_name = row.get_cell(1).txt
        log(Severity.INFO, tool_name, f'Chapter # {file_num_int} \'s name is: "{chapter_name}"!')
        chapter_name_sanitized = chapter_name.replace('"', '')

        # Rename file
        destination_path = mka_file.path.parent / f'{file_num_int} - {chapter_name_sanitized}.mka'
        fileUtils.rename_file(mka_file.path, destination_path)


class BatchRenameMKAfromCSV(pyside.Window):
    def __init__(self):
        super().__init__('Batch Rename MKA from CSV')

        # Set dimensions
        self.width = 490
        self.height = 115

        # BATCH RENAME MKA UI COMPONENTS --------------------------------------------------------------------------------

        # --- OPTIONS ---
        # Arguments Dict
        convert_arg = {}

        # 1. Target Folder
        # Create Label
        pyside.Label('Target Folder: ', self.dlg, pyside.QRect(10, 12, 400, 20))
        # Create Argument
        convert_arg['target_dir'] = pyside.LineEdit('', self.dlg, pyside.QRect(105, 10, 370, 25))

        # --- BUTTON ---
        pyside.button('Batch Convert', self.dlg, pyside.QRect(5, 80, 480, 30), ui_rename_mka_from_csv, convert_arg)

        # --------------------------------------------------------------------------------------------------------------