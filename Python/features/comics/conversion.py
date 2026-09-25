"""
CBR to CBZ conversion helpers for the Logistics Comics feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

import os
from pathlib import Path
from typing import List

import config

from commonUtils import dirUtils, fileUtils, zipUtils


show_verbose = True


# ----------------------------------------------------------------------------------------------------------------------
# CONVERSION HELPERS

def get_temp_convert_path(convert_name) -> Path:
    """Return the temporary conversion directory used by a Comics conversion."""

    temp_convert_path = Path(config.LogisticsConfig().temp_path, convert_name)
    print('Convert path is: ' + str(temp_convert_path))
    return temp_convert_path


def convert_cbr_to_cbz(target_file_path: Path):
    """Convert one CBR archive to CBZ, replacing the original CBR on success."""

    file = target_file_path

    temp_convert_path = get_temp_convert_path('CBRtoCRZ-Convert')

    if not os.path.isdir(temp_convert_path):
        print('\nConvert path did not exist! Creating...')
        os.makedirs(temp_convert_path)
    else:
        print('Convert path existed! Proceeding...')

    temp_convert_directory = dirUtils.Directory(temp_convert_path)

    temp_dir_contents = os.listdir(temp_convert_path)
    if len(temp_dir_contents) != 0:
        print('Convert path contained some files. Obliterating...')
        temp_convert_directory.delete_contents()
    else:
        print('Convert path did not contain any files. Proceeding...')

    print('Starting conversion now!\n')

    file_name_zip = file.with_suffix('.zip')
    file_name_cbz = file.with_suffix('.cbz')

    try:
        temp_convert_directory.delete_contents()

        zipUtils.unrar_file(
            file,
            temp_convert_path,
            unrar_sw_path=Path(config.LogisticsConfig().path_logistics_software_win, 'unrar')
        )

        zipUtils.zip_file(temp_convert_path, file_name_zip, keep_root=False)

        fileUtils.rename_file(file_name_zip, file_name_cbz)

        temp_convert_directory.delete_contents()

        original_file = fileUtils.File(file)
        original_file.delete_file()

        return True

    except:
        if os.path.exists(file_name_zip):
            zip_file = fileUtils.File(file_name_zip)
            zip_file.delete_file()
        elif os.path.exists(file_name_cbz):
            cbz_file = fileUtils.File(file_name_cbz)
            cbz_file.delete_file()

        temp_convert_directory.delete_contents()

    return False


def dir_batch_convert_cbr_to_cbz(target_dir, recursive):
    """Convert all CBR files in a directory to CBZ."""

    print('Batch Convert .CBR to .CBZ in directory "{}" [Recursive]...'.format(target_dir))

    target_directory = dirUtils.Directory(target_dir)
    cbr_file_lst: List[fileUtils.File] = target_directory.list_files(
        recursive=recursive,
        filter_extension='cbr'
    )

    if len(cbr_file_lst) == 0:
        print('Did not find a .CBR file to convert')
        return False

    print('Found {} files to convert:'.format(str(len(cbr_file_lst))))
    for file in cbr_file_lst:
        print(f' - {file.path}')

    for file in cbr_file_lst:
        convert_cbr_to_cbz(file.path)

    print('Conversion of {} files completed (as much as possible)!'.format(str(len(cbr_file_lst))))
    return True
