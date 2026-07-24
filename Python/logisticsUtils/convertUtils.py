import config
from pathlib import Path
import os
import commonUtils.fileUtils as fileUtils
from commonUtils import zipUtils
from typing import List


show_verbose = True


def get_temp_convert_path(convert_name):
    # Figure out the temporary convert directory
    temp_convert_path = str(Path(config.LogisticsConfig().temp_path, convert_name))
    print('Convert path is: ' + temp_convert_path)
    return temp_convert_path


def convert_cbr_to_cbz(target_file_path):

    # Simplify var name to file
    file = target_file_path
    filter_ext = '.cbz'

    # Get temp convert path
    temp_convert_path = get_temp_convert_path('CBRtoCRZ-Convert')

    # Make sure temp directory exists, if not create it
    if not os.path.isdir(temp_convert_path):
        print('\nConvert path did not exist! Creating...')
        os.makedirs(temp_convert_path)
    else:
        print('Convert path existed! Proceeding...')

    # Make sure temp directory is empty
    temp_dir_contents = os.listdir(temp_convert_path)
    if len(temp_dir_contents) != 0:
        print('Convert path contained some files. Obliterating...')
        fileUtils.delete_dir_contents(temp_convert_path)
    else:
        print('Convert path did not contain any files. Proceeding...')

    print('Starting conversion now!\n')

    # Determine new file name
    file_name_zip = file[:-len(filter_ext)] + '.zip'
    file_name_cbz = file[:-len(filter_ext)] + '.cbz'
    try:
        # In here is convert procedure for file from beginning to end.
        fileUtils.delete_dir_contents(temp_convert_path)
        # Uncompress RAR
        zipUtils.unrar_file(file, temp_convert_path, unrar_sw_path=str(Path(config.LogisticsConfig().path_logistics_software_win, 'unrar')))
        # Zip File
        zipUtils.zip_file(temp_convert_path, file_name_zip, keep_root=False)
        # Need to rename after file creation because it does .zip regardless of what I say
        fileUtils.rename_file(file_name_zip, file_name_cbz)
        # Clean convert dir
        fileUtils.delete_dir_contents(temp_convert_path)
        # Delete original file
        original_file = fileUtils.File(file)
        original_file.delete_file()
        # The conversion succeeded!
        return True

    except:
        # TRY TO RECUPERATE FROM ERROR. IF ERROR WHILST RECUPERATING, THROW ERROR

        # If corrupted or not properly done zip file is there, obliterate it.
        if os.path.exists(file_name_zip):
            zip_file = fileUtils.File(file_name_zip)
            zip_file.delete_file()
        elif os.path.exists(file_name_cbz):
            cbz_file = fileUtils.File(file_name_cbz)
            cbz_file.delete_file()
        # Clean convert dir
        fileUtils.delete_dir_contents(temp_convert_path)

    # The conversion failed!
    return False


def dir_batch_convert_cbr_to_cbz(target_dir, recursive):

    # Tell User Files are Being Converted
    print('Batch Convert .CBR to .CBZ in directory "{}" [Recursive]...'.format(target_dir))

    # Get list of .CBR files
    cbr_file_lst: List[fileUtils.File] = fileUtils.get_file_list_from_path(
        target_dir,
        recursive=recursive,
        filter_extension='cbr',
    )

    # Display to user the search results
    if len(cbr_file_lst) == 0:
        print('Did not find a .CBR file to convert')
        return False
    else:
        print('Found {} files to convert:'.format(str(len(cbr_file_lst))))
        for file in cbr_file_lst:
            print(f' - {file.path}')

    for file in cbr_file_lst:
        convert_cbr_to_cbz(file.path)

    # Finished Successfully
    print('Conversion of {} files completed (as much as possible)!'.format(str(len(cbr_file_lst))))
    return True
