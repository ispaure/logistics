from commonUtils.ui import pyside
import logisticsUtils.cbzUtils as cbzUtils


def ui_dir_batch_compress_cbz(convert_arg):

    # Translate the argument dict to arguments and execute the proper function.
    cbzUtils.batch_compress_cbz(target_dir=convert_arg['target_dir'].txt(), recursive=convert_arg['recursive'].isChecked(),
                                always_keep_compressed=convert_arg['always_keep_compressed'].isChecked())


class DirBatchCompressCBZWindow(pyside.Window):
    def __init__(self):
        super().__init__('Batch Compress .CBZ')

        # Set dimensions
        self.width = 490
        self.height = 140

        # CONVERT CBR TO CBZ UI COMPONENTS -----------------------------------------------------------------------------

        # --- OPTIONS ---
        # Arguments Dict
        convert_arg = {}

        # 1. Target Folder
        # Create Label
        pyside.Label('Target Folder: ', self.dlg, pyside.QRect(10, 12, 400, 20))
        # Create Argument
        convert_arg['target_dir'] = pyside.LineEdit(
            str(cbzUtils.default_path_to_convert_cbz), self.dlg, pyside.QRect(105, 10, 370, 25)
        )

        # 2. Recursive
        # Create Label
        pyside.Label('Recursive (Include Sub-folders): ', self.dlg, pyside.QRect(10, 43, 400, 20))
        # Create Argument
        convert_arg['recursive'] = pyside.create_checkbox(
            self.dlg, pyside.QRect(205, 28, 50, 50), default_state=True
        )
        pyside.Label('Always Keep Compressed: ', self.dlg, pyside.QRect(10, 63, 400, 20))
        convert_arg['always_keep_compressed'] = pyside.create_checkbox(
            self.dlg, pyside.QRect(205, 48, 50, 50), default_state=False
        )

        # --- BUTTON ---
        pyside.button(
            'Batch Compress', self.dlg, pyside.QRect(5, 105, 480, 30), ui_dir_batch_compress_cbz, convert_arg
        )

        # --------------------------------------------------------------------------------------------------------------