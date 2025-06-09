from commonUtils.pySideUtils import *
import logisticsUtils.convertUtils as convertUtils

show_verbose = True


def ui_dir_batch_convert_cbr_to_cbz(convert_arg):

    # Translate the argument dict to arguments and execute the proper function.
    convertUtils.dir_batch_convert_cbr_to_cbz(target_dir=convert_arg['target_dir'].txt(),
                                              recursive=convert_arg['recursive'].isChecked())


class DirBatchConvertCBRtoCBZ(Window):
    def __init__(self):
        super().__init__('Batch Convert ComicBook RAR (.cbr) to ComicBook ZIP (.cbz)')

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
        button('Batch Convert', self.dlg, QRect(5, 80, 480, 30), ui_dir_batch_convert_cbr_to_cbz, convert_arg)

        # --------------------------------------------------------------------------------------------------------------
