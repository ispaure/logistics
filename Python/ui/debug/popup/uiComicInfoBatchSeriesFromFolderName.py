from commonUtils.pySideUtils import *
from commonUtils import fileUtils, zipUtils
import ui.debug.popup.uiComicInfoBatchAuthorFromFolderName as uiComicInfoBatchAuthorFromFolderName
from pathlib import Path
from commonUtils.osUtils import *
from commonUtils.debugUtils import *

show_verbose = True


def comic_info_xml_replace_series(file_path, search, suffix):
    """
    Search and replaces tag for author in ComicInfo.XML within a .cbz file
    (Extracts the file, modifies the .XML, repackages and overwrites the original file)
    :param file_path: File path to the original .CBZ file
    :type file_path: str
    :param search: What to search for when doing search/replace
    :type search: str
    :param replace: What to replace by when doing a search/replace
    :type replace: str
    """
    print('\nInitializing Batch Rename on File: ' + file_path)

    # Figure out the folder name
    match get_os():
        case OS.WIN:
            replace = suffix + file_path.split('\\')[-2]
        case OS.MAC:
            replace = suffix + file_path.split('/')[-2]
        case _:
            log(Severity.CRITICAL, 'uiComicInfoBatchSeriesFromFolderName', 'Platform unsupported!')
            return

    print('Series name: ' + replace)

    # Figure out temporary folder path
    temp_folder_path = uiComicInfoBatchAuthorFromFolderName.get_temp_loc_edit_comicinfoxml()
    # Make sure temp directory exists, if not create it
    if not os.path.isdir(temp_folder_path):
        print('\nConvert path did not exist! Creating...')
        os.makedirs(temp_folder_path)
    else:
        print('Convert path existed! Proceeding...')

    comicinfo_xml_path = str(Path(temp_folder_path, 'ComicInfo.xml'))
    # Figure out zip name from file_path
    file_path_cbz = file_path
    file_path_zip = file_path[:-len('.zip')] + '.zip'

    # Try from now on, if doesn't succeed, must be cautious about not losing files
    try:

        # Delete contents in dir
        fileUtils.delete_dir_contents(temp_folder_path)
        # Uncompress ZIP
        zipUtils.unzip_file(file_path_cbz, temp_folder_path)

        # ----------------------------------------------------------------------------------
        # Untested change from sunsetting search_replace_xml
        search_string = '<Series>' + search + '</Series>'
        replace_string = '<Series>' + replace + '</Series>'
        xml_file = fileUtils.TXTFile(Path(comicinfo_xml_path))
        xml_file.read_lines()

        xml_file.line_lst = [
            line.replace(search_string, replace_string)
            for line in xml_file.line_lst
        ]
        xml_file.write_lines()
        # ----------------------------------------------------------------------------------

        # ZIP File
        zipUtils.zip_file(temp_folder_path, file_path_zip, keep_root=False)
        # Rename to .CBZ (overwriting the previous file)
        fileUtils.rename_file(Path(file_path_zip), Path(file_path_cbz), force=True)
        # Clean convert dir
        fileUtils.delete_dir_contents(temp_folder_path)
        # Delete original file not needed because was overwritten
        # The rename author succeeded!
        print('Finished renaming author!')

    except:
        print('COULD NOT COMPLETE FILE SUCCESSFULLY!!!!' + file_path_cbz)
        # If corrupted or not renamed to cbz, obliterate
        if os.path.exists(file_path_zip):
            zip_file = fileUtils.File(Path(file_path_zip))
            zip_file.delete_file()
        # Never delete .cbz, always source of truth. If there's another error its fine but that file is the final
        # and should never be deleted
        # Clean convert dir
        fileUtils.delete_dir_contents(temp_folder_path)


def ui_comicinfoxml_batch_rename_series_to_dir_name(convert_arg):
    """
    Batch rename authors within the ComicInfo.XML to the directory name in which the .CBZ is located
    NOTE: Author Tag must already be present in file and set to existing tag to replace.
    WHAT THE SCRIPT DOES: Extract the .CBZ, search and replace within XML, repacks and replaces original file
    """

    # Display initiating info
    print('Starting the Batch Rename of Series Name in ComicInfo.XML (based on folder name and prefix)')
    batch_target_folder = convert_arg['target_dir'].txt()
    series_tag_to_replace = convert_arg['target_existing_tag'].txt()
    suffix = convert_arg['series_prefix'].txt()
    print('Target Folder: ' + batch_target_folder)
    print('Tag to Replace: ' + series_tag_to_replace)

    # Get list of files (recursive)
    file_lst = fileUtils.get_file_path_list(batch_target_folder, recursive=True)

    # Filter by ext (.cbr)
    filter_ext = '.cbz'
    filter_file_lst = []
    for file in file_lst:
        if filter_ext.lower() == file[-len(filter_ext):].lower():
            filter_file_lst.append(file)

    # Display to user the search results
    if len(filter_file_lst) == 0:
        print('Did not find a .CBZ file')
        return False
    else:
        print('Found {} files to batch rename author:'.format(str(len(filter_file_lst))))
        for file in filter_file_lst:
            print(' - ' + file)

    for file in filter_file_lst:
        comic_info_xml_replace_series(file, series_tag_to_replace, suffix)


class ComicInfoBatchSeriesFromFolderName(Window):
    def __init__(self):
        super().__init__('ComicInfo.XML: Batch Set Series from Folder Name')

        # Set dimensions
        self.width = 490
        self.height = 160

        # CONVERT CBR TO CBZ UI COMPONENTS -----------------------------------------------------------------------------

        # --- OPTIONS ---
        # Arguments Dict
        convert_arg = {}

        # 1. Target Folder
        # Create Label
        Label('Target Folder: ', self.dlg, QRect(10, 12, 400, 20))
        # Create Argument
        convert_arg['target_dir'] = LineEdit('', self.dlg, QRect(105, 10, 370, 25))

        # SERIES TAG TO REPLACE: Create Label and input field
        Label('Existing Series Tag to Replace: ', self.dlg, QRect(10, 43, 400, 20))
        convert_arg['target_existing_tag'] = LineEdit('REPLACESERIESHERE', self.dlg, QRect(200, 43, 275, 25))

        # SERIES PREFIX: Create Label and input field
        Label('Series Prefix to put in front: ', self.dlg, QRect(10, 80, 400, 20))
        convert_arg['series_prefix'] = LineEdit('', self.dlg, QRect(200, 80, 275, 25))

        # --- BUTTON ---
        button('Batch Replace Series Tag', self.dlg, QRect(5, 125, 480, 30), ui_comicinfoxml_batch_rename_series_to_dir_name, convert_arg)

        # --------------------------------------------------------------------------------------------------------------
