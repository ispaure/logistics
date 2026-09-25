from commonUtils.ui import pyside

from features.comics import metadata


show_verbose = True


def ui_comicinfoxml_batch_rename_series_to_dir_name(convert_arg):
    metadata.batch_rename_series_to_dir_name(
        target_dir=convert_arg['target_dir'].txt(),
        series_tag_to_replace=convert_arg['target_existing_tag'].txt(),
        suffix=convert_arg['series_prefix'].txt()
    )


class ComicInfoBatchSeriesFromFolderName(pyside.Window):
    def __init__(self):
        super().__init__('ComicInfo.XML: Batch Set Series from Folder Name')

        self.width = 490
        self.height = 160

        convert_arg = {}

        pyside.Label('Target Folder: ', self.dlg, pyside.QRect(10, 12, 400, 20))
        convert_arg['target_dir'] = pyside.LineEdit('', self.dlg, pyside.QRect(105, 10, 370, 25))

        pyside.Label('Existing Series Tag to Replace: ', self.dlg, pyside.QRect(10, 43, 400, 20))
        convert_arg['target_existing_tag'] = pyside.LineEdit(
            'REPLACESERIESHERE',
            self.dlg,
            pyside.QRect(200, 43, 275, 25)
        )

        pyside.Label('Series Prefix to put in front: ', self.dlg, pyside.QRect(10, 80, 400, 20))
        convert_arg['series_prefix'] = pyside.LineEdit('', self.dlg, pyside.QRect(200, 80, 275, 25))

        pyside.button(
            'Batch Replace Series Tag',
            self.dlg,
            pyside.QRect(5, 125, 480, 30),
            ui_comicinfoxml_batch_rename_series_to_dir_name,
            convert_arg
        )
