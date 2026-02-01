
import wrappers.rcloneWrapper as rcloneWrapper
from commonUtils.pySideUtils import *
import interactions
import commands
import wrappers.plex.plexDatabaseReader as plexDatabaseReader
import ui.uiRemoteCredentials as uiRemoteCredentials
import ui.debug.popup.uiBatchConvertCBRtoCBZ as uiBatchConvertCBRtoCBZ
import ui.debug.popup.uiComicInfoBatchAuthorFromFolderName as uiComicInfoBatchAuthorFromFolderName
import ui.debug.popup.uiComicInfoBatchSeriesFromFolderName as uiComicInfoBatchSeriesFromFolderName
import ui.debug.popup.uiBatchIndividualFoldersforCBZ as uiBatchIndividualFoldersforCBZ
import ui.debug.popup.uiJPGExifBatchSetFieldComment as uiJPGExifBatchSetFieldComment
import ui.debug.popup.uiListFilesWeirdChars as uiListFilesWeirdChars
import ui.debug.popup.uiBatchRenameMKAfromCSV as uiBatchRenameMKAfromCSV
import ui.debug.popup.uiBulkDeletePYCInDir as uiBulkDeletePYCInDir
import ui.debug.popup.uiBatchCompressCBZ as uiBatchCompressCBZ
import ui.debug.popup.uiBatchCompressImageToWEBP as uiBatchCompressImageToWEBP
import wrappers.philipsHueWrapper as philipsHueWrapper
from flightSim import flightSimUtils
from commonUtils.osUtils import *
from commonUtils.debugUtils import *


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
