from commonUtils.pySideUtils import *
import commonUtils.imageUtils as imageUtils


def ui_dir_batch_compress_image(convert_arg):

    # Translate the argument dict to arguments and execute the proper function.
    imageUtils.batch_compress_image(target_dir=convert_arg['target_dir'].txt(), recursive=convert_arg['recursive'].isChecked(), always_keep_compressed=convert_arg['always_keep_compressed'].isChecked())


class DirBatchCompressImageWindow(Window):
    def __init__(self):
        super().__init__('Batch Compress Images to WEBP')

        # Set dimensions
        self.width = 490
        self.height = 140

        # CONVERT CBR TO CBZ UI COMPONENTS -----------------------------------------------------------------------------

        # --- OPTIONS ---
        # Arguments Dict
        convert_arg = {}

        # 1. Target Folder
        # Create Label
        Label('Target Folder: ', self.dlg, QRect(10, 12, 400, 20))
        # Create Argument
        convert_arg['target_dir'] = LineEdit(str(imageUtils.default_path_to_convert_img), self.dlg, QRect(105, 10, 370, 25))

        # 2. Recursive
        # Create Label
        Label('Recursive (Include Sub-folders): ', self.dlg, QRect(10, 43, 400, 20))
        # Create Argument
        convert_arg['recursive'] = create_checkbox(self.dlg, QRect(205, 28, 50, 50), default_state=True)
        Label('Always Keep Compressed: ', self.dlg, QRect(10, 63, 400, 20))
        convert_arg['always_keep_compressed'] = create_checkbox(self.dlg, QRect(205, 48, 50, 50), default_state=False)

        # --- BUTTON ---
        button('Batch Compress', self.dlg, QRect(5, 105, 480, 30), ui_dir_batch_compress_image, convert_arg)

        # --------------------------------------------------------------------------------------------------------------
