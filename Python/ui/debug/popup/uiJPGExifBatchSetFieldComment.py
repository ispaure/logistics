from commonUtils.ui import pyside

from features.images import actions


def ui_jpg_batch_set_exif_comments(convert_arg):
    actions.set_jpg_exif_comments(
        target_dir=convert_arg['target_dir'].txt(),
        recursive=convert_arg['recursive'].isChecked(),
        comments=convert_arg['comments_field'].txt()
    )


class JPGEXIFBatchSetFieldComment(pyside.Window):
    def __init__(self):
        super().__init__('.JPG: Batch Set EXIF "Comments" Field')
        self.__name__ = 'Logistics Main UI Window'

        self.width = 490
        self.height = 145

        convert_arg = {}

        pyside.Label('Target Folder: ', self.dlg, pyside.QRect(10, 12, 400, 20))
        convert_arg['target_dir'] = pyside.LineEdit('', self.dlg, pyside.QRect(105, 10, 370, 25))

        pyside.Label('Recursive (Include Subfolders): ', self.dlg, pyside.QRect(10, 43, 400, 20))
        convert_arg['recursive'] = pyside.create_checkbox(
            self.dlg,
            pyside.QRect(205, 28, 50, 50),
            default_state=True
        )

        pyside.Label(
            'Comments field input (only alphanumeric, no spaces allowed): ',
            self.dlg,
            pyside.QRect(10, 68, 400, 20)
        )
        convert_arg['comments_field'] = pyside.LineEdit('', self.dlg, pyside.QRect(380, 68, 90, 20))

        pyside.button(
            'Batch Set EXIF Comments',
            self.dlg,
            pyside.QRect(5, 105, 480, 30),
            ui_jpg_batch_set_exif_comments,
            convert_arg
        )
