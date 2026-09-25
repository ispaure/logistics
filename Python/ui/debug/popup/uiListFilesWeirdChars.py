from commonUtils.ui import pyside

from features.file_tools import filesystem


def ui_list_files_weird_chars(convert_arg):
    filesystem.print_files_with_weird_characters(
        target_dir=convert_arg['target_dir'].txt(),
        recursive=True
    )


class ListFilesWeirdChars(pyside.Window):
    def __init__(self):
        super().__init__('List Files with weird characters')

        self.width = 490
        self.height = 115

        convert_arg = {}

        pyside.Label('Target Folder: ', self.dlg, pyside.QRect(10, 12, 400, 20))
        convert_arg['target_dir'] = pyside.LineEdit(
            'C:\\Server\\Local\\',
            self.dlg,
            pyside.QRect(105, 10, 370, 25)
        )

        pyside.button(
            'List Files',
            self.dlg,
            pyside.QRect(5, 80, 480, 30),
            ui_list_files_weird_chars,
            convert_arg
        )
