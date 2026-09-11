from commonUtils.ui import pyside
from commonUtils.debugUtils import *
from commonUtils import dirUtils
from pathlib import Path

show_verbose = True


def bulk_delete_pyc_in_dir(convert_arg):

    directory = dirUtils.Directory(Path(convert_arg['target_dir'].txt()))
    recursive = convert_arg['recursive'].isChecked()
    file_lst = directory.list_files(recursive=recursive, filter_extension='pyc')

    for file in file_lst:
        file.delete_file()

    log(Severity.INFO, 'Bulk Delete PYC Files', f'Deleted PYC Files Recursively in "{directory.path}"')


class BulkDeletePYCInDir(pyside.Window):
    def __init__(self):
        super().__init__('Bulk Delete .PYC in Directory')

        # Set dimensions
        self.width = 490
        self.height = 115

        # CONVERT CBR TO CBZ UI COMPONENTS -----------------------------------------------------------------------------

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
        pyside.button('Bulk DELETE', self.dlg, pyside.QRect(5, 80, 480, 30), bulk_delete_pyc_in_dir, convert_arg)

        # --------------------------------------------------------------------------------------------------------------
