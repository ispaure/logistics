import os
import sys
# This is needed even if greyed out!
# TODO Don't need this anymore
# import install.installPythonPackage
from PySide6.QtWidgets import *
import config as config
import wrappers.rcloneWrapper as rcloneWrapper
import ui.uiMain as uiMain
from commonUtils.debugUtils import *
from commonUtils import pySideUtils


def create_q_application():
    app = QApplication([])
    app.setStyle('Fusion')
    if sys.platform == 'win32':  # Windows
        os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
        palette_cls = pySideUtils.Palette()
        palette_cls.set_dark()
        app.setPalette(palette_cls.palette)


# Get Config Information
logistics_cfg = config.LogisticsConfig()

# Adds Remote Credentials saved within the Logistics Dir to rclone.conf (if they weren't there yet)
rcloneWrapper.add_logistics_remote_to_rclone_conf()

# Clear existing mounts (if symbolic links exist in mount folder, delete them)
# Only for Windows
if sys.platform == 'win32':
    rcloneWrapper.clear_mounts()

# Mount all remotes in mount folder
rcloneWrapper.mount_all_rclone_conf_remotes(timeout=2)

# Get All Remote Class
rcloneWrapper.get_all_remote_class()

# Create QApplication
create_q_application()

# Display UI
uiMain.display_main_menu()
