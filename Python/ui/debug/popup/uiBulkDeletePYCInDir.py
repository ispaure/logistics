from commonUtils.ui import pyside

from features.file_tools import filesystem


def bulk_delete_pyc_in_dir(convert_arg):
    filesystem.delete_pyc_files(
        target_dir=convert_arg['target_dir'].txt(),
        recursive=convert_arg['recursive'].isChecked()
    )


class BulkDeletePYCInDir(pyside.Window):
    def __init__(self):
        super().__init__('Bulk Delete .PYC in Directory')

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
            'Bulk DELETE',
            self.dlg,
            pyside.QRect(5, 80, 480, 30),
            bulk_delete_pyc_in_dir,
            convert_arg
        )
