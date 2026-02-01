
import wrappers.rcloneWrapper as rcloneWrapper
from commonUtils.pySideUtils import *
import interactions


def display_remotes(dialog_obj, type):
    """
    Display remotes in the UI
    """

    # Get list of remotes
    remote_cls_lst = rcloneWrapper.get_all_remote_class()

    # Filter remotes by type (so you only show Local or Remote remotes since they each have their own tab)
    display_lst = []
    for remote_cls in remote_cls_lst:
        if remote_cls.type == type:
            display_lst.append(remote_cls)

    # Determine size of grid contents
    height_per_row = 30
    scroll_height = len(display_lst) * height_per_row + 50

    # Create grid layout contained in scroll area
    widget_content, grid_layout = create_scroll_area_grid(target=dialog_obj,
                                                          rect=QRect(0, 0, 700, 450),
                                                          rect_content=create_size(695, scroll_height))

    # Get interactions
    interactions_complete_lst, remote_amt = interactions.get_remote_cls_lst_interactions(display_lst)

    # Determine number of rows and columns
    positions = [(i, j) for i in range(len(display_lst)) for j in
                 range(len(interactions_complete_lst) // remote_amt)]

    # For each position (in order, from left to right, top to bottom) create a button with the correct thing
    for position, name in zip(positions, interactions_complete_lst):
        button_var = button(text=name[0](name[1])['Name'], target=widget_content, rect=QRect(0, 0, 120, 80), fn=name[0](name[1])['Action'], args=name[1])

        grid_layout.addWidget(button_var, *position)
