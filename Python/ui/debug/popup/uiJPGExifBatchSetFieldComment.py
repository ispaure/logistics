from commonUtils.pySideUtils import *
import wrappers.piexifWrapper as piexifWrapper

show_verbose = True


def ui_jpg_batch_set_exif_comments(convert_arg):

    # Translate the argument dict to arguments and execute the proper function.
    piexifWrapper.jpg_batch_set_exif_comments(target_dir=convert_arg['target_dir'].txt(),
                                              recursive=convert_arg['recursive'].isChecked(),
                                              comments=convert_arg['comments_field'].txt())


class JPGEXIFBatchSetFieldComment(Window):
    def __init__(self):
        super().__init__('.JPG: Batch Set EXIF "Comments" Field')
        self.__name__ = 'Logistics Main UI Window'

        # Set dimensions
        self.width = 490
        self.height = 145

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

        # 3. Comments field data
        # Create Label
        Label('Comments field input (only alphanumeric, no spaces allowed): ', self.dlg, QRect(10, 68, 400, 20))
        # Create Argument
        convert_arg['comments_field'] = LineEdit('', self.dlg, QRect(380, 68, 90, 20))

        # --- BUTTON ---
        button('Batch Convert', self.dlg, QRect(5, 105, 480, 30), ui_jpg_batch_set_exif_comments, convert_arg)

        # --------------------------------------------------------------------------------------------------------------
