from commonUtils.ui import pyside

from features.comics import actions


show_verbose = True


def ui_move_cbz_to_new_created_dir(convert_arg) -> bool:
    return actions.move_cbz_to_individual_folders(convert_arg['target_dir'].txt())


class BatchIndividualFolderforCBZ(pyside.Window):
    def __init__(self):
        super().__init__('Create new folders for .CBZ and put then into it')
        self.__name__ = 'Logistics Main UI Window'

        self.width = 490
        self.height = 115

        convert_arg = {}

        pyside.Label('Target Folder: ', self.dlg, pyside.QRect(10, 12, 400, 20))
        convert_arg['target_dir'] = pyside.LineEdit('', self.dlg, pyside.QRect(105, 10, 370, 25))

        pyside.button(
            'Batch Create Folders',
            self.dlg,
            pyside.QRect(5, 80, 480, 30),
            ui_move_cbz_to_new_created_dir,
            convert_arg
        )
