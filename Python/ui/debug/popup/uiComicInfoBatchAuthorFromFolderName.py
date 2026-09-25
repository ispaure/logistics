from commonUtils.ui import pyside

from features.comics import metadata


show_verbose = True


def ui_comicinfoxml_batch_rename_author_to_dir_name(convert_arg):
    metadata.batch_rename_author_to_dir_name(
        target_dir=convert_arg['target_dir'].txt(),
        author_tag_to_replace=convert_arg['target_existing_tag'].txt()
    )


class ComicInfoBatchAuthorFromFolderName(pyside.Window):
    def __init__(self):
        super().__init__('ComicInfo.XML: Batch Set Author from Folder Name')
        self.__name__ = 'Logistics Main UI Window'

        self.width = 490
        self.height = 115

        convert_arg = {}

        pyside.Label('Target Folder: ', self.dlg, pyside.QRect(10, 12, 400, 20))
        convert_arg['target_dir'] = pyside.LineEdit('', self.dlg, pyside.QRect(105, 10, 370, 25))

        pyside.Label('Existing Author Tag to Replace: ', self.dlg, pyside.QRect(10, 43, 400, 20))
        convert_arg['target_existing_tag'] = pyside.LineEdit(
            'REPLACEAUTHORHERE',
            self.dlg,
            pyside.QRect(200, 43, 275, 25)
        )

        pyside.button(
            'Batch Replace Author Tag',
            self.dlg,
            pyside.QRect(5, 80, 480, 30),
            ui_comicinfoxml_batch_rename_author_to_dir_name,
            convert_arg
        )
