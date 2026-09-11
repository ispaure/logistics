from commonUtils.ui import pyside
from commonUtils.debugUtils import *
from commonUtils.dirUtils import Directory
from logisticsUtils.calibreUtils import CalibreLibrary
from wrappers.rcloneWrapper import Remote
from pathlib import Path
from typing import List


def inter_open_calibre_dir(calibre_lib: CalibreLibrary):
    interaction_dict = {}
    interaction_dict['Name'] = calibre_lib.name
    interaction_dict['Action'] = inter_open_calibre_dir_action
    return interaction_dict


def inter_open_calibre_dir_action(calibre_lib: CalibreLibrary):
    calibre_lib.open()


def inter_launch_calibre(calibre_lib: CalibreLibrary):
    interaction_dict = {}
    interaction_dict['Name'] = 'Launch Calibre'
    interaction_dict['Action'] = inter_launch_calibre_action
    return interaction_dict


def inter_launch_calibre_action(calibre_lib: CalibreLibrary):
    calibre_lib.open_in_calibre()


def inter_echo_calibre_epubs_to_boox_sd(calibre_lib: CalibreLibrary):
    interaction_dict = {}
    interaction_dict['Name'] = 'Echo to BOOX-SD'
    interaction_dict['Action'] = inter_echo_calibre_epubs_to_boox_sd_action
    return interaction_dict


def inter_echo_calibre_epubs_to_boox_sd_action(calibre_lib: CalibreLibrary):
    dest_pth: Path = Path('/Volumes', 'BOOX-SD', 'Calibre [EPUBs]', calibre_lib.name)
    calibre_lib.echo_book_formats(dest_pth, ['epub'])


calibre_interaction_lst = [inter_open_calibre_dir,
                           inter_launch_calibre,
                           inter_echo_calibre_epubs_to_boox_sd]


def get_calibre_library_interactions(calibre_library_lst: List[CalibreLibrary]):
    interaction_complete_lst = []

    for calibre_library in calibre_library_lst:
        for interaction in calibre_interaction_lst:
            interaction_complete_lst.append([interaction, calibre_library])

    return interaction_complete_lst, len(calibre_library_lst)


class ManageCalibre(pyside.Window):
    def __init__(self, remote_cls: Remote):
        super().__init__('Manage Calibre [{}]'.format(remote_cls.name))

        # Set dimensions
        self.width = 500
        self.height = 250

        match remote_cls.type:
            case 'Local':
                # Get Calibre libraries from the remote
                calibre_lib_cls_lst: List[CalibreLibrary] = []
                remote_subdir_lst: List[Directory] = remote_cls.list_directories()

                for remote_subdir in remote_subdir_lst:
                    db_file_lst = remote_subdir.list_files(recursive=False, filter_extension='db')
                    if len(db_file_lst) > 0:
                        calibre_lib_cls_lst.append(CalibreLibrary(remote_subdir.path))

                # Create interaction grid
                if len(calibre_lib_cls_lst) > 0:
                    height_per_row = 30
                    scroll_height = len(calibre_lib_cls_lst) * height_per_row + 50

                    widget_content, grid_layout = pyside.create_scroll_area_grid(
                        target=self.dlg,
                        rect=pyside.QRect(0, 0, self.width, self.height),
                        rect_content=pyside.create_size(self.width - 5, scroll_height)
                    )

                    interactions_complete_lst, calibre_lib_amt = get_calibre_library_interactions(calibre_lib_cls_lst)

                    # One row per Calibre library, one column per interaction
                    positions = [(i, j) for i in range(calibre_lib_amt) for j in range(len(calibre_interaction_lst))]

                    for position, interaction in zip(positions, interactions_complete_lst):
                        interaction_dict = interaction[0](interaction[1])
                        button_var = pyside.button(
                            text=interaction_dict['Name'], target=widget_content,
                            rect=pyside.QRect(0, 0, 120, 80), fn=interaction_dict['Action'], args=interaction[1]
                        )
                        grid_layout.addWidget(button_var, *position)

                else:
                    pyside.Label('No Calibre libraries found', self.dlg, pyside.QRect(5, 5, 400, 25))

            case 'Remote':
                pyside.Label(
                    'Manage Calibre tools are only supported for local remotes',
                    self.dlg, pyside.QRect(5, 5, 400, 25)
                )

        # --------------------------------------------------------------------------------------------------------------