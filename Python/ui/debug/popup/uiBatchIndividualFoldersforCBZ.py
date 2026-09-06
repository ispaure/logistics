from commonUtils.pySideUtils import *
import commonUtils.fileUtils as fileUtils
from commonUtils import dirUtils
from commonUtils.debugUtils import *
from pathlib import Path
from commonUtils.osUtils import *

show_verbose = True


def ui_move_cbz_to_new_created_dir(convert_arg) -> bool:
    """
    Put each CBZ file in a folder with the same name as the CBZ.
    Useful for one-shots in Komga.
    """

    tool_name = 'Move CBZ to Individual Folders'
    log(Severity.INFO, tool_name, 'Starting the batch creation of individual folders and moving each .CBZ file into its new folder.')

    batch_target_folder = dirUtils.Directory(Path(convert_arg['target_dir'].txt()))
    log(Severity.INFO, tool_name, f'Target Folder: "{batch_target_folder.path}"')

    file_lst: List[fileUtils.File] = batch_target_folder.list_files(recursive=False, filter_extension='cbz')

    if not file_lst:
        log(Severity.WARNING, tool_name, 'Did not find a .CBZ file.')
        return False

    log(Severity.INFO, tool_name, f'Found {len(file_lst)} files to put in new folders:')
    for file in file_lst:
        log(Severity.INFO, tool_name, f' - "{file.path}"')

    for file in file_lst:
        dir_path = file.path.parent / file.name_without_ext
        new_path = dir_path / file.file_name

        log(Severity.INFO, tool_name, f'Make new directory: "{dir_path}"')
        log(Severity.INFO, tool_name, f'Move file to new location: "{new_path}"')

        fileUtils.make_dir(dir_path)

        if not fileUtils.copy_file(file.path, new_path):
            log(Severity.ERROR, tool_name, f'Failed to copy "{file.path}". The original was not deleted.')
            return False

        if not file.delete_file():
            log(Severity.ERROR, tool_name, f'Copied "{file.path}" successfully, but failed to delete the original file.')
            return False

    log(Severity.INFO, tool_name, 'Finished moving all .CBZ files into individual folders.')
    return True


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
