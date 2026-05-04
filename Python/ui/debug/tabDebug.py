
from commonUtils.pySideUtils import *
import commands
import wrappers.plex.plexDatabaseReader as plexDatabaseReader
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
import ui.debug.popup.uiConflictingCopiesDropbox as uiConflictingCopiesDropbox


def display_debug(dialog_obj):
    # Repair Windows Script
    button('Windows System Files Repair', dialog_obj, QRect(10, 10, 250, 30), commands.run_repair_windows_script)
    button('Repair NTFS on D:/', dialog_obj, QRect(10, 40, 250, 30), dialog_obj, commands.run_repair_ntfs_on_d)

    # PLEX Database Script
    button('PLEXDB - Parse Database test', dialog_obj, QRect(10, 70, 250, 30), plexDatabaseReader.test_script)

    # Batch Convert .CBR to .CBZ
    button_open_win('Batch Convert .CBR to .CBZ', dialog_obj, QRect(10, 100, 250, 30), uiBatchConvertCBRtoCBZ.DirBatchConvertCBRtoCBZ)
    # Batch ComicInfo.XML Folder name to Author Label
    button_open_win('ComicInfo.XML: Batch Set Author from Folder Name', dialog_obj, QRect(10, 130, 350, 30), uiComicInfoBatchAuthorFromFolderName.ComicInfoBatchAuthorFromFolderName)
    button_open_win('ComicInfo.XML: Batch Set Series from Folder Name', dialog_obj, QRect(10, 160, 350, 30), uiComicInfoBatchSeriesFromFolderName.ComicInfoBatchSeriesFromFolderName)
    button_open_win('.CBZ move in folder with name of file', dialog_obj, QRect(10, 190, 300, 30), uiBatchIndividualFoldersforCBZ.BatchIndividualFolderforCBZ)
    # List weird chars in dir (recursive)
    button_open_win('List Weird Chars in Dir', dialog_obj, QRect(10, 220, 200, 30), uiListFilesWeirdChars.ListFilesWeirdChars)
    # Rename MKA from CSV in Directory
    button_open_win('Rename MKA from CSV', dialog_obj, QRect(10, 250, 200, 30), uiBatchRenameMKAfromCSV.BatchRenameMKAfromCSV)

    # Hash change
    button_open_win('.JPG: EXIF Batch Set Comments Field', dialog_obj, QRect(260, 10, 250, 30), uiJPGExifBatchSetFieldComment.JPGEXIFBatchSetFieldComment)

    # MacOS Sleep
    button('Disable macOS Lid Sleep', dialog_obj, QRect(260, 40, 250, 30), commands.disable_macos_lid_sleep)
    button('Enable macOS Lid Sleep', dialog_obj, QRect(260, 70, 250, 30), commands.enable_macos_lid_sleep)

    # Bulk Delete .PYC in Dir
    button_open_win('Bulk Delete .PYC in Dir', dialog_obj, QRect(10, 280, 200, 30), uiBulkDeletePYCInDir.BulkDeletePYCInDir)

    # Batch Compress .CBZ in Dir
    button_open_win('Batch Compress .CBZ in Dir', dialog_obj, QRect(10, 310, 200, 30), uiBatchCompressCBZ.DirBatchCompressCBZWindow)

    # Batch Compress Image to WEBP in Dir
    button_open_win('Batch Compress Images in Dir', dialog_obj, QRect(10, 340, 200, 30), uiBatchCompressImageToWEBP.DirBatchCompressImageWindow)

    # Conflicting Copies dropbox
    button_open_win('Conflicting Copies (Dropbox)', dialog_obj, QRect(10, 370, 200, 30), uiConflictingCopiesDropbox.ConflictingCopiesDropbox)
