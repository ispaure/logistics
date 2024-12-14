from commonUtils.pySideUtils import *
import commonUtils.fileUtils as fileUtils

show_verbose = True


def ui_list_files_weird_chars(convert_arg):
    """
    List files with weird characters in dir (recursive)
    """

    # Display initiating info
    print('Starting the printing of files with weird characters in their name in dir (recursive)')
    batch_target_folder = convert_arg['target_dir'].text()
    print('Target Folder: ' + batch_target_folder)

    # Get list of files (recursive)
    file_lst = fileUtils.get_file_path_list(batch_target_folder, recursive=True)

    # Weird characters list (some appear the same here (duplicates) but are in fact different characters, its tricky!)
    weird_char_lst = ['é', 'É', 'è', 'È', 'ê', 'Ê', 'ë', 'Ë',
                      'é', 'É', 'è', 'È', 'ê', 'Ê', 'ë', 'Ë',
                      'à', 'À', 'â', 'Â', 'ä', 'Ä',
                      'à', 'À', 'â', 'Â', 'ä', 'Ä',
                      'î', 'Î', 'ï', 'Ï',
                      'î', 'Î', 'ï', 'Ï',
                      'ù', 'Ù', 'û', 'Û',
                      'ù', 'Ù', 'û', 'Û',
                      'ç', 'Ç',
                      'ç', 'Ç',
                      'ô', 'Ô',
                      'ô', 'Ô']

    for file in file_lst:
        for char in weird_char_lst:
            if char in file:
                print(' - ' + file)

    # Done going through list
    print('\n\nDone going through files list!')


class ListFilesWeirdChars(Window):
    def __init__(self):
        super().__init__('List Files with weird characters')

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
        convert_arg['target_dir'] = LineEdit('C:\\Server\\Local\\', self.dlg, QRect(105, 10, 370, 25))

        # --- BUTTON ---
        button('List Files', self.dlg, QRect(5, 80, 480, 30), ui_list_files_weird_chars, convert_arg)

        # --------------------------------------------------------------------------------------------------------------
