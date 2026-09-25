from commonUtils.ui import pyside

from features.dropbox import conflicts


show_verbose = True


def print_conflicting_copies_dropbox(convert_arg):
    conflicts.print_conflicting_copies(
        target_dir=convert_arg['target_dir'].txt(),
        recursive=convert_arg['recursive'].isChecked()
    )


def delete_conflicting_copies_dropbox(convert_arg):
    conflicts.delete_conflicting_copies(
        target_dir=convert_arg['target_dir'].txt(),
        recursive=convert_arg['recursive'].isChecked()
    )


class ConflictingCopiesDropbox(pyside.Window):
    def __init__(self):
        super().__init__('Conflicting Copies in Dropbox')

        self.width = 500
        self.height = 150

        convert_arg = {}

        # Target Folder
        pyside.Label('Target Folder: ', self.dlg, pyside.QRect(10, 12, 400, 20))
        convert_arg['target_dir'] = pyside.LineEdit('', self.dlg, pyside.QRect(105, 10, 370, 25))

        # Recursive
        pyside.Label('Recursive (Include Subfolders): ', self.dlg, pyside.QRect(10, 43, 400, 20))
        convert_arg['recursive'] = pyside.create_checkbox(
            self.dlg,
            pyside.QRect(205, 28, 50, 50),
            default_state=True
        )

        pyside.button(
            'Print Conflicting Copies',
            self.dlg,
            pyside.QRect(5, 80, 480, 30),
            print_conflicting_copies_dropbox,
            convert_arg
        )

        pyside.button(
            'Delete Conflicting Copies',
            self.dlg,
            pyside.QRect(5, 115, 480, 30),
            delete_conflicting_copies_dropbox,
            convert_arg
        )
