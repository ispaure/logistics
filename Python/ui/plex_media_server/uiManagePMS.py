from commonUtils import ui
from commonUtils.debugUtils import Severity, log
from commonUtils.osUtils import OS, get_os

from features.plex import actions as plex_actions
from models.local_folder import LocalFolder
from models.remote_folder import RemoteFolder


class ManagePMS(ui.pyside.Window):
    def __init__(self, remote_cls):
        super().__init__('Manage PMS [{}]'.format(remote_cls.name))

        # Set dimensions
        self.width = 500
        self.height = 250

        # CREATE UI ELEMENTS FOR PMSDATA CONFIG WINDOW -----------------------------------------------------------------

        match get_os():
            case OS.WIN:
                os_pref_folder_name = 'AppData'
            case OS.MAC:
                os_pref_folder_name = 'Application Support'
            case _:
                log(Severity.CRITICAL, 'uiManagePMS', 'Unsupported Platform!')
                return

        if isinstance(remote_cls, LocalFolder):

            # Open PMSData (Local) button
            ui.pyside.button('Open Local -PMSDATA', self.dlg, ui.pyside.QRect(0, 3, 200, 30),
                             plex_actions.open_dir_local_cls_pmsdata, remote_cls)

            # Clear LocalPMS button
            ui.pyside.button('Clear Local -PMSDATA', self.dlg, ui.pyside.QRect(300, 3, 200, 30),
                             plex_actions.clear_local_pmsdata, remote_cls)

            # Label: Restore PLEX Media Server Data from Cloud
            ui.pyside.Label('Restore PLEX Media Server Data from Cloud:', self.dlg, ui.pyside.QRect(10, 43, 400, 20))

            # Buttons
            ui.pyside.button('1. Pull {}-PMSDATA from Remote to Local'.format(remote_cls.name), self.dlg,
                             ui.pyside.QRect(0, 65, 500, 30), plex_actions.pull_pms, remote_cls)
            ui.pyside.button('2. Unpackage Local {}-PMSDATA to {} PMS'.format(remote_cls.name, os_pref_folder_name),
                             self.dlg, ui.pyside.QRect(0, 95, 500, 30), plex_actions.unpackage_pms, remote_cls)

            # Label: Backup PLEX Media Server Data to Cloud
            ui.pyside.Label('Backup PLEX Media Server Data to Cloud:', self.dlg, ui.pyside.QRect(10, 150, 400, 20))

            # Buttons
            ui.pyside.button('1. Package {} PMS to Local {}-PMSDATA'.format(os_pref_folder_name, remote_cls.name),
                             self.dlg, ui.pyside.QRect(0, 172, 500, 30), plex_actions.package_pms, remote_cls)
            ui.pyside.button('2. PUSH {}-PMSDATA from Local to Remote'.format(remote_cls.name), self.dlg,
                             ui.pyside.QRect(0, 202, 500, 30), plex_actions.push_pms, remote_cls)

        elif isinstance(remote_cls, RemoteFolder):

            # Open PMSData (Remote) button
            ui.pyside.button('Open Remote -PMSDATA', self.dlg, ui.pyside.QRect(0, 3, 200, 30),
                             plex_actions.open_dir_remote_cls_pmsdata, remote_cls)

        # --------------------------------------------------------------------------------------------------------------