from commonUtils.pySideUtils import *
import logisticsUtils.imageUtils as imageUtils


def ui_dir_batch_compress_image(convert_arg):

    # Get the arguments from the dictionary
    target_dir: str = convert_arg['target_dir'].txt()
    recursive: bool = convert_arg['recursive'].isChecked()
    always_keep_compressed: bool = convert_arg['always_keep_compressed'].isChecked()
    img_quality_color: int = int(convert_arg['quality_color'].txt())
    img_quality_grayscale: int = int(convert_arg['quality_grayscale'].txt())
    if convert_arg['enable_max_long_edge'].isChecked():
        img_max_long_edge = int(convert_arg['max_long_edge'].txt())
    else:
        img_max_long_edge = None
    if convert_arg['enable_max_height'].isChecked():
        img_max_height = int(convert_arg['max_height'].txt())
    else:
        img_max_height = None

    # Translate the argument dict to arguments and execute the proper function.
    imageUtils.batch_compress_image(target_dir=target_dir,
                                    recursive=recursive,
                                    always_keep_compressed=always_keep_compressed,
                                    img_quality_color=img_quality_color,
                                    img_quality_grayscale=img_quality_grayscale,
                                    img_max_long_edge=img_max_long_edge,
                                    img_max_height=img_max_height)


class DirBatchCompressImageWindow(Window):
    def __init__(self):
        super().__init__('Batch Compress Images to WEBP')

        # Set dimensions (taller to fit compression settings)
        self.width = 490
        self.height = 305

        # --- OPTIONS ---
        # Arguments Dict
        convert_arg = {}

        # 1. Target Directory
        Label('Target Folder: ', self.dlg, QRect(10, 12, 400, 20))
        convert_arg['target_dir'] = LineEdit(
            str(imageUtils.default_path_to_convert_img),
            self.dlg,
            QRect(105, 10, 370, 25)
        )

        # 2. Recursive
        Label('Recursive (Include Sub-folders): ', self.dlg, QRect(10, 43, 400, 20))
        convert_arg['recursive'] = create_checkbox(self.dlg, QRect(205, 28, 50, 50), default_state=True)

        # 3. Always Keep Compressed Image ?
        Label('Always Keep Compressed: ', self.dlg, QRect(10, 68, 400, 20))
        convert_arg['always_keep_compressed'] = create_checkbox(self.dlg, QRect(205, 53, 50, 50), default_state=False)

        # 4. Compression Parameters
        Label('Compression Settings', self.dlg, QRect(10, 98, 400, 20))

        # --- Quality fields ---
        Label('Image Quality (Color):', self.dlg, QRect(10, 123, 200, 20))
        convert_arg['quality_color'] = LineEdit('80', self.dlg, QRect(205, 120, 70, 25))

        Label('Image Quality (Grayscale):', self.dlg, QRect(10, 153, 200, 20))
        convert_arg['quality_grayscale'] = LineEdit('45', self.dlg, QRect(205, 150, 70, 25))

        # --- Max Long Edge (toggle + value) ---
        Label('Limit Max Long Edge:', self.dlg, QRect(10, 183, 200, 20))
        convert_arg['enable_max_long_edge'] = create_checkbox(
            self.dlg,
            QRect(205, 168, 50, 50),
            default_state=True
        )
        convert_arg['max_long_edge'] = LineEdit('5120', self.dlg, QRect(265, 180, 70, 25))

        # --- Max Height (toggle + value) ---
        Label('Limit Max Height:', self.dlg, QRect(10, 213, 200, 20))
        convert_arg['enable_max_height'] = create_checkbox(
            self.dlg,
            QRect(205, 198, 50, 50),
            default_state=False
        )
        convert_arg['max_height'] = LineEdit('5000', self.dlg, QRect(265, 210, 70, 25))

        # --- BUTTON ---
        button('Batch Compress', self.dlg, QRect(5, 265, 480, 30), ui_dir_batch_compress_image, convert_arg)
