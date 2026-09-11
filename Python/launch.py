import sys
import config
from wrappers import rcloneWrapper
import ui.uiMain as uiMain
from commonUtils.ui import pyside
from commonUtils.debugUtils import *
from commonUtils.osUtils import *

log(Severity.INFO, 'Logistics', 'Executing launch.py')

# Get Config Information
log(Severity.DEBUG, 'Logistics', 'Get config.LogisticsConfig()')
logistics_cfg = config.LogisticsConfig()

# Adds Remote Credentials saved within the Logistics Dir to rclone.conf (if they weren't there yet)
log(Severity.DEBUG, 'Logistics', 'Adds Remote Credentials to rclone.conf (if was not there yet')
rcloneWrapper.add_logistics_remote_to_rclone_conf()

# Clear existing mounts (if symbolic links exist in mount folder, delete them)
# Only for Windows
if get_os() == OS.WIN:
    log(Severity.DEBUG, 'rclone', 'Clear mounts on Windows')
    rcloneWrapper.clear_mounts()

# Mount all remotes in mount folder
log(Severity.DEBUG, 'rclone', 'Mount all remotes in mount folder')
rcloneWrapper.mount_all_rclone_conf_remotes(timeout=2)

# Get All Remote Class
log(Severity.DEBUG, 'rclone', 'Get all Remote Class')
rcloneWrapper.get_all_remote_class()

# Create QApplication
log(Severity.DEBUG, 'PySide6', 'Create QApplication')
app = pyside.initialize_q_app()

# Display UI
log(Severity.DEBUG, 'PySide6', 'Display Main UI Window')
main_menu = uiMain.display_main_menu()
sys.exit(app.exec())