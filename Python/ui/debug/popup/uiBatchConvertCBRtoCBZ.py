from commonUtils.ui import pyside

from features.comics import conversion


show_verbose = True


def ui_dir_batch_convert_cbr_to_cbz(convert_arg):
    conversion.dir_batch_convert_cbr_to_cbz(
        target_dir=convert_arg['target_dir'].txt(),
        recursive=convert_arg['recursive'].isChecked()
    )


class DirBatchConvertCBRtoCBZ(pyside.Window):
    def __init__(self):
        super().__init__('Batch Convert ComicBook RAR (.cbr) to ComicBook ZIP (.cbz)')

        self.width = 490
        self.height = 115

        convert_arg = {}

        pyside.Label('Target Folder: ', self.dlg, pyside.QRect(10, 12, 400, 20))
        convert_arg['target_dir'] = pyside.LineEdit('', self.dlg, pyside.QRect(105, 10, 370, 25))

        pyside.Label('Recursive (Include Subfolders): ', self.dlg, pyside.QRect(10, 43, 400, 20))
        convert_arg['recursive'] = pyside.create_checkbox(
            self.dlg,
            pyside.QRect(205, 28, 50, 50),
            default_state=True
        )

        pyside.button(
            'Batch Convert',
            self.dlg,
            pyside.QRect(5, 80, 480, 30),
            ui_dir_batch_convert_cbr_to_cbz,
            convert_arg
        )
