"""
CBR to CBZ conversion helpers for the Logistics Comics feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path
from typing import List
from tempfile import TemporaryDirectory

import config

from commonUtils import dirUtils, fileUtils, zipUtils
from commonUtils.debugUtils import Severity, log
from .archive_io import replace_archive, archive_unchanged


show_verbose = True


# ----------------------------------------------------------------------------------------------------------------------
# CONVERSION HELPERS

def get_temp_convert_path(convert_name) -> Path:
    """Return the temporary conversion directory used by a Comics conversion."""

    temp_convert_path = Path(config.LogisticsConfig().temp_path, convert_name)
    print('Convert path is: ' + str(temp_convert_path))
    return temp_convert_path


def convert_cbr_to_cbz(target_file_path: Path) -> bool:
    """Delete a CBR only after its CBZ has been built and verified successfully."""
    source = Path(target_file_path)
    destination = source.with_suffix('.cbz')
    if destination.exists() or destination.is_symlink():
        log(Severity.ERROR, 'CBR conversion', f'Destination already exists: {destination}')
        return False
    try:
        original_stat = source.stat()
        with TemporaryDirectory(prefix='logistics-cbr-', ignore_cleanup_errors=True) as workspace:
            extracted = Path(workspace)
            # Let patool discover an installed extractor on the current platform.
            # The old Windows software path was also passed on macOS/Linux.
            result = zipUtils.unrar_file(source, extracted)
            # unrar_file returns None on success; an explicit False is a failure.
            if result is False:
                raise OSError(f'Could not extract {source}')
            if not archive_unchanged(source, original_stat):
                raise RuntimeError(f'CBR changed while extracting: {source}')
            replace_archive(extracted, destination, overwrite=False)
        if not archive_unchanged(source, original_stat):
            raise RuntimeError(f'CBR changed while creating CBZ: {source}')
        if not fileUtils.File(source).delete_file():
            raise OSError(f'CBZ created, but original CBR could not be deleted: {source}')
        return True
    except Exception as error:
        log(Severity.ERROR, 'CBR conversion', f'Could not convert "{source}": {error}')
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

    successful = True
    for file in cbr_file_lst:
        if not convert_cbr_to_cbz(file.path):
            successful = False

    print('Conversion of {} files completed (as much as possible)!'.format(str(len(cbr_file_lst))))
    return successful
