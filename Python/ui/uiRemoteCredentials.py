import wrappers.rcloneWrapper as rcloneWrapper
from commonUtils.pySideUtils import *
import sys
import ui.uiRemoteCredentialsPW as uiRemoteCredentialsPW
from commonUtils.osUtils import *
from commonUtils.debugUtils import *


def ui_load_credential_password_ui(arg):
    rem_cred_cls = uiRemoteCredentialsPW.RemoteCredentialsPW(arg['Path'])
    rem_cred_cls.display_ui()


class LoadRemoteCredentials(Window):
    def __init__(self):
        super().__init__('Load Remote Credentials')

        # Set dimensions
        self.width = 400
        self.height = 200

        # UNLOCK CREDENTIALS ZIP LIST ----------------------------------------------------------------------------------

        # Gather list of ZIP Items to create buttons for
        zip_file_lst = rcloneWrapper.get_logistics_remote_credentials_zip_lst()

        # Determine size of grid
        height_per_row = 30
        scroll_height = len(zip_file_lst) * height_per_row

        # Create grid layout contained in scroll area
        widget_content, grid_layout = create_scroll_area_grid(target=self.dlg,
                                                              rect=QRect(0, 0, 400, 200),
                                                              rect_content=create_size(395, scroll_height))

        # Determine number of rows and columns
        positions = [(i, j) for i in range(len(zip_file_lst)) for j in range(1)]

        # For each position, create a button
        for position, zip_file in zip(positions, zip_file_lst):
            # Find text for button's title
            match get_os():
                case OS.WIN:
                    button_text = zip_file.split('\\')[-1].replace('.zip', '')
                case _:
                    button_text = zip_file.split('/')[-1].replace('.zip', '')
            # Come up with argument list for function
            arg = {'Path': zip_file}

            button_var = button(text=button_text,
                                target=widget_content,
                                rect=QRect(0, 0, 120, 80),
                                fn=ui_load_credential_password_ui,
                                args=arg)

            # Add the button to the grid
            grid_layout.addWidget(button_var, *position)

        # --------------------------------------------------------------------------------------------------------------
