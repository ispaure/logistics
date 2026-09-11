import wrappers.rcloneWrapper as rcloneWrapper
from commonUtils.ui import pyside
from commonUtils.debugUtils import log, Severity
from commonUtils import fileUtils as fileUtils
import os


def push_to_cloud(remote_cls):
    source_path = remote_cls['remote_cls'].path
    destination_path = remote_cls['remote_cls'].name + ':'
    rcloneWrapper.rclone_sync(source_path, destination_path, track_renames=remote_cls['track_renames'].isChecked())


def push_specific_dir(data_to_exec):
    print('Initiating Push to Cloud (Specific Dir)')

    # Get important values
    directory_path_to_push = data_to_exec['Push Specific Directory'].txt()

    if not os.path.isdir(directory_path_to_push):
        msg = 'The path you have given is not a valid directory!'
        log(Severity.ERROR, 'Push Individual Folder', msg, popup=True)
        return False

    bandwidth_limit = data_to_exec['Bandwidth Limit'].txt()

    if bandwidth_limit == '':
        bandwidth_limit = None

    specific_dir_name = directory_path_to_push.split(fileUtils.get_split_character())[-1]
    cloud_remote_path = data_to_exec['Remote Class'].name + ':' + specific_dir_name

    # Execute specific dir sync
    rcloneWrapper.rclone_sync(directory_path_to_push, cloud_remote_path, bw_limit=bandwidth_limit)


class LocalPushUI(pyside.Window):
    def __init__(self, remote_cls):
        super().__init__('Local Push Options [{}]'.format(remote_cls.name))

        # Set dimensions
        self.width = 500
        self.height = 250

        # REGULAR PUSH -------------------------------------------------------------------------------------------------
        # ENTERTAINMENT
        panel = pyside.create_frame(self.dlg, pyside.QRect(5, 5, 490, 95))
        pyside.Label('REGULAR PUSH TO CLOUD: ', panel, pyside.QRect(10, 10, 200, 13))

        # Create Label
        pyside.Label('Track renames: ', panel, pyside.QRect(10, 35, 400, 20))

        # Create Argument
        convert_arg = {}
        convert_arg['track_renames'] = pyside.create_checkbox(
            panel, pyside.QRect(110, 35, 20, 20), default_state=False
        )
        convert_arg['remote_cls'] = remote_cls

        # Create regular push button
        pyside.button('PUSH [Regular]', panel, pyside.QRect(85, 65, 320, 25), push_to_cloud, convert_arg)
        # --------------------------------------------------------------------------------------------------------------

        # ADD FOLDER ---------------------------------------------------------------------------------------------------
        panel_add_dir = pyside.create_frame(self.dlg, pyside.QRect(5, 105, 490, 135))

        # Label: Add Folder to CLOUD
        pyside.Label('ADD FOLDER TO CLOUD:', panel_add_dir, pyside.QRect(10, 10, 400, 20))
        pyside.Label(
            'If folder with same name already exists on Cloud, it will get overwritten.',
            panel_add_dir,
            pyside.QRect(10, 30, 480, 20)
        )

        # Create argument dictionary
        arg_custom_dir = {'Remote Class': remote_cls}

        # Create file path label
        pyside.Label('Specific Folder Path: ', panel_add_dir, pyside.QRect(10, 55, 400, 20))

        # Create file path field
        path_textedit_specific_dir = pyside.LineEdit('', panel_add_dir, pyside.QRect(160, 55, 300, 20))
        arg_custom_dir['Push Specific Directory'] = path_textedit_specific_dir

        # Create bandwidth limit label
        pyside.Label('Bandwidth Limit: ', panel_add_dir, pyside.QRect(10, 80, 400, 20))
        textedit_bw_limit = pyside.LineEdit('', panel_add_dir, pyside.QRect(160, 80, 300, 20))
        arg_custom_dir['Bandwidth Limit'] = textedit_bw_limit

        # Create package for push to cloud
        pyside.button('PUSH [Specific Folder]', panel_add_dir, pyside.QRect(85, 105, 320, 25),
                      push_specific_dir, arg_custom_dir)
        # --------------------------------------------------------------------------------------------------------------