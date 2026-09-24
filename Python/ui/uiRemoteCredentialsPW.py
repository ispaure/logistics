from features.rclone import credentials as rclone_credentials
from commonUtils.ui import pyside


show_verbose = True


def ui_load_credentials(unlock_arg):

    # Load Credentials
    rclone_credentials.add_remote_from_zip_to_rclone_conf(
        zip_path=unlock_arg['Path'],
        zip_pw=unlock_arg['Password'].txt()
    )

    # Close Window
    # TODO Doesn't work anymore since the restructure
    # unlock_arg['UI-Window'].dlg.main_win.close()


class RemoteCredentialsPW(pyside.Window):
    def __init__(self, file_path):
        super().__init__('Enter Password for Credentials Archive')

        # Set dimensions
        self.width = 490
        self.height = 100

        # UNLOCK CREDENTIAL UI COMPONENTS ------------------------------------------------------------------------------

        # --- OPTIONS ---
        # Argument Dict
        unlock_arg = {'Path': file_path, 'UI-Window': self}

        # 1. Password Entry
        # Create Label
        pyside.Label('Password: ', self.dlg, pyside.QRect(10, 5, 400, 20))
        # Create Argument
        unlock_arg['Password'] = pyside.LineEdit('', self.dlg, pyside.QRect(100, 5, 380, 20), pw_field=True)

        # --- BUTTON ---
        pyside.button('Add Credentials to Rclone', self.dlg, pyside.QRect(0, 25, 490, 30),
                      ui_load_credentials, unlock_arg)

        # --------------------------------------------------------------------------------------------------------------