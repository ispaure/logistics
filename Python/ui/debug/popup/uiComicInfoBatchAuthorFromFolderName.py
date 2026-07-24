from commonUtils.pySideUtils import *
from commonUtils import fileUtils, zipUtils
from pathlib import Path
import config as config
from commonUtils.osUtils import *
from commonUtils.debugUtils import *
show_verbose = True


def get_temp_loc_edit_comicinfoxml():
    # Figure out the temporary convert directory
    temp_convert_path = str(Path(config.LogisticsConfig().temp_path, 'Edit-ComicInfoXML'))
    print('Convert path is: ' + temp_convert_path)
    return temp_convert_path


def comic_info_xml_replace_author(file_path: Path, search: str):
    """
    Search and replaces tag for author in ComicInfo.XML within a .CBZ file
    (Extracts the file, modifies the .XML, repackages and overwrites the original file)

    :param file_path: File path to the original .CBZ file
    :param search: What to search for when doing search/replace
    """
    print(f'\nInitializing Batch Rename on File: {file_path}')

    # Figure out the folder name
    replace = file_path.parent.name
    print(f'Author name: {replace}')

    # Figure out temporary folder path
    temp_folder_path = get_temp_loc_edit_comicinfoxml()

    # Make sure temp directory exists, if not create it
    if not os.path.isdir(temp_folder_path):
        print('\nConvert path did not exist! Creating...')
        os.makedirs(temp_folder_path)
    else:
        print('Convert path existed! Proceeding...')

    comicinfo_xml_path = Path(temp_folder_path, 'ComicInfo.xml')

    # Figure out zip name from file_path
    file_path_cbz = file_path
    file_path_zip = file_path.with_suffix('.zip')

    # Try from now on, if doesn't succeed, must be cautious about not losing files
    try:
        # Delete contents in dir
        fileUtils.delete_dir_contents(temp_folder_path)

        # Uncompress ZIP
        zipUtils.unzip_file(file_path_cbz, temp_folder_path)

        # Search and replace within XML
        search_string = f'<Writer>{search}</Writer>'
        replace_string = f'<Writer>{replace}</Writer>'

        # ----------------------------------------------------------------------------------
        # Untested change from sunsetting search_replace_xml
        xml_file = fileUtils.TXTFile(comicinfo_xml_path)
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
        fileUtils.rename_file(file_path_zip, file_path_cbz)

        # Clean convert dir
        fileUtils.delete_dir_contents(temp_folder_path)

        # Delete original file not needed because was overwritten
        # The rename author succeeded!
        print('Finished renaming author!')

    except Exception:
        print(f'COULD NOT COMPLETE FILE SUCCESSFULLY!!!!{file_path_cbz}')

        # If corrupted or not renamed to cbz, obliterate
        if file_path_zip.exists():
            fileUtils.File(file_path_zip).delete_file()

        # Never delete .cbz, always source of truth. If there's another error its fine but that file is the final
        # and should never be deleted

        # Clean convert dir
        fileUtils.delete_dir_contents(temp_folder_path)


def ui_comicinfoxml_batch_rename_author_to_dir_name(convert_arg):
    """
    Batch rename authors within the ComicInfo.XML to the directory name in which the .CBZ is located.
    NOTE: Author Tag must already be present in file and set to existing tag to replace.
    WHAT THE SCRIPT DOES: Extract the .CBZ, search and replace within XML, repacks and replaces original file.
    """

    # Display initiating info
    print('Starting the Batch Rename of Author Name in ComicInfo.XML (based on folder name)')
    batch_target_folder = convert_arg['target_dir'].txt()
    author_tag_to_replace = convert_arg['target_existing_tag'].txt()
    print('Target Folder: ' + batch_target_folder)
    print('Tag to Replace: ' + author_tag_to_replace)

    # Get list of .CBZ files recursively
    cbz_file_lst: List[fileUtils.File] = fileUtils.get_file_list_from_path(
        batch_target_folder,
        recursive=True,
        filter_extension='cbz',
    )

    # Display to user the search results
    if len(cbz_file_lst) == 0:
        print('Did not find a .CBZ file')
        return False
    else:
        print('Found {} files to batch rename author:'.format(str(len(cbz_file_lst))))
        for file in cbz_file_lst:
            print(f' - {file.path}')

    for file in cbz_file_lst:
        comic_info_xml_replace_author(file.path, author_tag_to_replace)


class ComicInfoBatchAuthorFromFolderName(Window):
    def __init__(self):
        super().__init__('ComicInfo.XML: Batch Set Author from Folder Name')
        self.__name__ = 'Logistics Main UI Window'

        # Set dimensions
        self.width = 490
        self.height = 115

        # CONVERT CBR TO CBZ UI COMPONENTS -----------------------------------------------------------------------------

        # --- OPTIONS ---
        # Arguments Dict
        convert_arg = {}

        # 1. Target Folder
        # Create Label
        Label('Target Folder: ', self.dlg, QRect(10, 12, 400, 20))
        # Create Argument
        convert_arg['target_dir'] = LineEdit('', self.dlg, QRect(105, 10, 370, 25))

        # 2. Recursive
        # Create Label
        Label('Existing Author Tag to Replace: ', self.dlg, QRect(10, 43, 400, 20))
        # Create Argument
        convert_arg['target_existing_tag'] = LineEdit('REPLACEAUTHORHERE', self.dlg, QRect(200, 43, 275, 25))

        # --- BUTTON ---
        button('Batch Replace Author Tag', self.dlg, QRect(5, 80, 480, 30), ui_comicinfoxml_batch_rename_author_to_dir_name, convert_arg)

        # --------------------------------------------------------------------------------------------------------------
