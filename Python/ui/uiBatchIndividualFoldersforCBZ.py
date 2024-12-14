from commonUtils.pySideUtils import *
import commonUtils.fileUtils as fileUtils
from pathlib import Path

show_verbose = True


def ui_move_cbz_to_new_created_dir(convert_arg):
    """
    Put CBZ in a folder with the name of the CBZ (useful for oneshots for komga)
    """

    # Display initiating info
    print('Starting the Batch Creation of Individual Folders for .CBZ and putting them in')
    batch_target_folder = convert_arg['target_dir'].text()
    print('Target Folder: ' + batch_target_folder)

    # Get list of files (recursive)
    file_lst = fileUtils.get_file_path_list(batch_target_folder, recursive=False)

    # Filter by ext (.cbr)
    filter_ext = '.cbz'
    filter_file_lst = []
    for file in file_lst:
        if filter_ext.lower() == file[-len(filter_ext):].lower():
            filter_file_lst.append(file)

    # Display to user the search results
    if len(filter_file_lst) == 0:
        print('Did not find a .CBZ file')
        return False
    else:
        print('Found {} files to batch put in new folders:'.format(str(len(filter_file_lst))))
        for file in filter_file_lst:
            print(' - ' + file)

    for file in filter_file_lst:
        if sys.platform == 'win32':
            split_char = '\\'
        else:
            split_char = '/'
        print('This is what I will do')
        dir_name = file[:-len('.cbz')]
        print('Make new directory: ' + dir_name)
        fileUtils.make_dir(dir_name)
        new_loc = str(Path(dir_name, file.split(split_char)[-1]))
        print('Move file to new location: ' + new_loc)
        fileUtils.copy_file(file, new_loc)
        fileUtils.delete_file(file)


class BatchIndividualFolderforCBZ(Window):
    def __init__(self):
        super().__init__('Create new folders for .CBZ and put then into it')
        self.__name__ = 'Logistics Main UI Window'

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

        # --- BUTTON ---
        button('Batch Create Folders', self.dlg, QRect(5, 80, 480, 30), ui_move_cbz_to_new_created_dir, convert_arg)

        # --------------------------------------------------------------------------------------------------------------
