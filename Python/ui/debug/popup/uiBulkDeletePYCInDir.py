from commonUtils.pySideUtils import *
from commonUtils.debugUtils import *
show_verbose = True


def bulk_delete_pyc_in_dir(convert_arg):

    directory = convert_arg['target_dir'].txt()
    recursive = convert_arg['recursive'].isChecked()
    file_lst = fileUtils.get_file_list_from_path(directory, recursive=recursive, filter_extension='pyc')
    for file in file_lst:
        file.delete_file()
    log(Severity.INFO, 'Bulk Delete PYC Files', f'Deleted PYC Files Recursively in "{directory}"')


class BulkDeletePYCInDir(Window):
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
        Label('Target Folder: ', self.dlg, QRect(10, 12, 400, 20))
        # Create Argument
        convert_arg['target_dir'] = LineEdit('', self.dlg, QRect(105, 10, 370, 25))

        # 2. Recursive
        # Create Label
        Label('Recursive (Include Subfolders): ', self.dlg, QRect(10, 43, 400, 20))
        # Create Argument
        convert_arg['recursive'] = create_checkbox(self.dlg, QRect(205, 28, 50, 50), default_state=True)

        # --- BUTTON ---
        button('Bulk DELETE', self.dlg, QRect(5, 80, 480, 30), bulk_delete_pyc_in_dir, convert_arg)

        # --------------------------------------------------------------------------------------------------------------
