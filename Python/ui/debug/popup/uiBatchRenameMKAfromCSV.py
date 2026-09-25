from commonUtils.ui import pyside

from features.media import mka


def ui_rename_mka_from_csv(convert_arg):
    mka.rename_from_csv(convert_arg['target_dir'].txt())


class BatchRenameMKAfromCSV(pyside.Window):
    def __init__(self):
        super().__init__('Batch Rename MKA from CSV')

        self.width = 490
        self.height = 115

        convert_arg = {}

        pyside.Label('Target Folder: ', self.dlg, pyside.QRect(10, 12, 400, 20))
        convert_arg['target_dir'] = pyside.LineEdit('', self.dlg, pyside.QRect(105, 10, 370, 25))

        pyside.button(
            'Batch Rename',
            self.dlg,
            pyside.QRect(5, 80, 480, 30),
            ui_rename_mka_from_csv,
            convert_arg
        )
