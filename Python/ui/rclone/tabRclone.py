import interactions
import wrappers.rcloneWrapper as rcloneWrapper

from commonUtils.ui import pyside
from models.local_folder import LocalFolder
from models.remote_folder import RemoteFolder


def display_remotes(dialog_obj, type):
    """
    Display remotes in the UI.
    """

    # Get list of Logistics folders
    remote_cls_lst = rcloneWrapper.get_all_remote_class()

    # Filter folders by model type.
    display_lst = []

    for remote_cls in remote_cls_lst:
        if type == 'Local' and isinstance(remote_cls, LocalFolder):
            display_lst.append(remote_cls)

        elif type == 'Remote' and isinstance(remote_cls, RemoteFolder):
            display_lst.append(remote_cls)

    # Determine size of grid contents
    height_per_row = 30
    scroll_height = len(display_lst) * height_per_row + 50

    # Create grid layout contained in scroll area
    widget_content, grid_layout = pyside.create_scroll_area_grid(
        target=dialog_obj,
        rect=pyside.QRect(0, 0, 700, 450),
        rect_content=pyside.create_size(695, scroll_height)
    )

    # Get interactions
    interactions_complete_lst, remote_amt = interactions.get_remote_cls_lst_interactions(display_lst)

    # Determine number of rows and columns
    positions = [(i, j) for i in range(len(display_lst)) for j in range(len(interactions_complete_lst) // remote_amt)]

    # For each position (in order, from left to right, top to bottom) create a button with the correct thing
    for position, name in zip(positions, interactions_complete_lst):
        button_var = pyside.button(
            text=name[0](name[1])['Name'],
            target=widget_content,
            rect=pyside.QRect(0, 0, 120, 80),
            fn=name[0](name[1])['Action'],
            args=name[1]
        )

        grid_layout.addWidget(button_var, *position)