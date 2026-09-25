"""
ComicInfo.xml metadata operations for the Logistics Comics feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

import os
from pathlib import Path
from typing import List

import config

from commonUtils import dirUtils, fileUtils, zipUtils
from commonUtils.fileTypes import txtType


# ----------------------------------------------------------------------------------------------------------------------
# TEMP PATH

def get_temp_loc_edit_comicinfoxml() -> Path:
    """Return the temporary directory used when editing ComicInfo.xml files."""

    temp_convert_path = Path(config.LogisticsConfig().temp_path, 'Edit-ComicInfoXML')
    print('Convert path is: ' + str(temp_convert_path))
    return temp_convert_path


# ----------------------------------------------------------------------------------------------------------------------
# AUTHOR

def comic_info_xml_replace_author(file_path: Path, search: str):
    """
    Search and replace the Writer tag in ComicInfo.xml within a CBZ file.

    The replacement value is the name of the CBZ file's parent directory.
    """

    print(f'\nInitializing Batch Rename on File: {file_path}')

    replace = file_path.parent.name
    print(f'Author name: {replace}')

    temp_folder_path = get_temp_loc_edit_comicinfoxml()

    if not os.path.isdir(temp_folder_path):
        print('\nConvert path did not exist! Creating...')
        os.makedirs(temp_folder_path)
    else:
        print('Convert path existed! Proceeding...')

    temp_folder_directory = dirUtils.Directory(temp_folder_path)
    comicinfo_xml_path = Path(temp_folder_path, 'ComicInfo.xml')

    file_path_cbz = file_path
    file_path_zip = file_path.with_suffix('.zip')

    try:
        temp_folder_directory.delete_contents()

        zipUtils.unzip_file(file_path_cbz, temp_folder_path)

        search_string = f'<Writer>{search}</Writer>'
        replace_string = f'<Writer>{replace}</Writer>'

        xml_file = txtType.TXTFile(comicinfo_xml_path)
        xml_file.read_lines()

        xml_file.line_lst = [
            line.replace(search_string, replace_string)
            for line in xml_file.line_lst
        ]
        xml_file.write_lines()

        zipUtils.zip_file(temp_folder_path, file_path_zip, keep_root=False)

        fileUtils.rename_file(file_path_zip, file_path_cbz)

        temp_folder_directory.delete_contents()

        print('Finished renaming author!')

    except Exception:
        print(f'COULD NOT COMPLETE FILE SUCCESSFULLY!!!!{file_path_cbz}')

        if file_path_zip.exists():
            fileUtils.File(file_path_zip).delete_file()

        temp_folder_directory.delete_contents()


def batch_rename_author_to_dir_name(target_dir, author_tag_to_replace: str):
    """Batch replace ComicInfo Writer tags using each CBZ parent directory name."""

    print('Starting the Batch Rename of Author Name in ComicInfo.XML (based on folder name)')

    batch_target_folder = dirUtils.Directory(Path(target_dir))

    print(f'Target Folder: {batch_target_folder.path}')
    print('Tag to Replace: ' + author_tag_to_replace)

    cbz_file_lst: List[fileUtils.File] = batch_target_folder.list_files(
        recursive=True,
        filter_extension='cbz'
    )

    if len(cbz_file_lst) == 0:
        print('Did not find a .CBZ file')
        return False

    print('Found {} files to batch rename author:'.format(str(len(cbz_file_lst))))
    for file in cbz_file_lst:
        print(f' - {file.path}')

    for file in cbz_file_lst:
        comic_info_xml_replace_author(file.path, author_tag_to_replace)

    return True


# ----------------------------------------------------------------------------------------------------------------------
# SERIES

def comic_info_xml_replace_series(file_path: Path, search: str, suffix: str):
    """
    Search and replace the Series tag in ComicInfo.xml within a CBZ file.

    The replacement value is the supplied prefix followed by the CBZ file's parent directory name.
    """

    print(f'\nInitializing Batch Rename on File: {file_path}')

    replace = suffix + file_path.parent.name
    print(f'Series name: {replace}')

    temp_folder_path = get_temp_loc_edit_comicinfoxml()

    if not os.path.isdir(temp_folder_path):
        print('\nConvert path did not exist! Creating...')
        os.makedirs(temp_folder_path)
    else:
        print('Convert path existed! Proceeding...')

    temp_folder_directory = dirUtils.Directory(temp_folder_path)
    comicinfo_xml_path = Path(temp_folder_path, 'ComicInfo.xml')

    file_path_cbz = file_path
    file_path_zip = file_path.with_suffix('.zip')

    try:
        temp_folder_directory.delete_contents()

        zipUtils.unzip_file(file_path_cbz, temp_folder_path)

        search_string = f'<Series>{search}</Series>'
        replace_string = f'<Series>{replace}</Series>'

        xml_file = txtType.TXTFile(comicinfo_xml_path)
        xml_file.read_lines()

        xml_file.line_lst = [
            line.replace(search_string, replace_string)
            for line in xml_file.line_lst
        ]
        xml_file.write_lines()

        zipUtils.zip_file(temp_folder_path, file_path_zip, keep_root=False)

        fileUtils.rename_file(file_path_zip, file_path_cbz, force=True)

        temp_folder_directory.delete_contents()

        print('Finished renaming series!')

    except Exception:
        print(f'COULD NOT COMPLETE FILE SUCCESSFULLY!!!!{file_path_cbz}')

        if file_path_zip.exists():
            fileUtils.File(file_path_zip).delete_file()

        temp_folder_directory.delete_contents()


def batch_rename_series_to_dir_name(target_dir, series_tag_to_replace: str, suffix: str):
    """Batch replace ComicInfo Series tags using each CBZ parent directory name."""

    print('Starting the Batch Rename of Series Name in ComicInfo.XML (based on folder name and prefix)')

    batch_target_folder = dirUtils.Directory(Path(target_dir))

    print(f'Target Folder: {batch_target_folder.path}')
    print('Tag to Replace: ' + series_tag_to_replace)

    cbz_file_lst: List[fileUtils.File] = batch_target_folder.list_files(
        recursive=True,
        filter_extension='cbz'
    )

    if len(cbz_file_lst) == 0:
        print('Did not find a .CBZ file')
        return False

    print('Found {} files to batch rename series:'.format(str(len(cbz_file_lst))))
    for file in cbz_file_lst:
        print(f' - {file.path}')

    for file in cbz_file_lst:
        comic_info_xml_replace_series(file.path, series_tag_to_replace, suffix)

    return True
