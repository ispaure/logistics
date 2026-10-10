"""
MKA media file operations for the Logistics Media feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path
from typing import List

from commonUtils import dirUtils, fileUtils, spreadsheetUtils
from commonUtils.debugUtils import Severity, log
from commonUtils.fileTypes import csvType
from commonUtils.renameUtils import RenamePlan, plan_named_renames, apply_renames


TOOL_NAME = 'Batch Rename MKA from CSV'


# ----------------------------------------------------------------------------------------------------------------------
# RENAME PLAN

def _get_csv_file(target_dir: dirUtils.Directory) -> csvType.CSVFile | None:
    """Return the single CSV file in a directory, or None if the directory is not valid for this operation."""

    csv_file_lst: List[fileUtils.File] = target_dir.list_files(recursive=False, filter_extension='csv')

    if len(csv_file_lst) == 0:
        log(Severity.ERROR, TOOL_NAME, '.CSV file missing from root of directory')
        return None

    if len(csv_file_lst) > 1:
        log(Severity.ERROR, TOOL_NAME, 'More than one .CSV file in directory')
        return None

    csv_file = csv_file_lst[0]

    if not isinstance(csv_file, csvType.CSVFile):
        log(Severity.ERROR, TOOL_NAME, f'Expected CSVFile, got {type(csv_file).__name__}')
        return None

    return csv_file


def _get_chapter_rows(csv_file: csvType.CSVFile):
    """Load chapter-name rows from the CSV file."""

    chapter_name_sheet = spreadsheetUtils.Spreadsheet('Chapter Names')
    chapter_name_sheet.import_file(csv_file)
    return chapter_name_sheet.get_rows()


def _build_rename_plan(target_dir: dirUtils.Directory, row_lst) -> RenamePlan | None:
    """
    Validate all MKA files and return their destination paths.

    No files are renamed while the plan is being built.
    """

    mka_file_lst: List[fileUtils.File] = target_dir.list_files(recursive=False, filter_extension='mka')

    if not mka_file_lst:
        log(Severity.WARNING, TOOL_NAME, 'No .MKA files found in directory')
        return plan_named_renames([])

    rename_plan = []

    for mka_file in mka_file_lst:
        file_num_str = mka_file.name_without_ext.removeprefix('Chapter_')

        if not mka_file.name_without_ext.startswith('Chapter_') or not file_num_str.isdigit():
            log(
                Severity.ERROR,
                TOOL_NAME,
                f'File {mka_file.file_name} contains invalid naming (should be Chapter_XX.mka)'
            )
            return None

        file_num_int = int(file_num_str)

        if file_num_int < 1 or file_num_int > len(row_lst):
            log(
                Severity.ERROR,
                TOOL_NAME,
                f'File {mka_file.file_name} does not have a chapter name in rows of .CSV file'
            )
            return None

        row = row_lst[file_num_int - 1]
        cells = row.get_cells()

        if len(cells) < 2:
            log(
                Severity.ERROR,
                TOOL_NAME,
                f'CSV row {file_num_int} does not contain both a chapter number and chapter name'
            )
            return None

        if cells[0].txt != str(file_num_int):
            log(
                Severity.ERROR,
                TOOL_NAME,
                f'File {mka_file.file_name} does not have proper chapter markings in column A '
                f'(found {cells[0].txt} instead of {file_num_int})'
            )
            return None

        chapter_name = cells[1].txt
        log(Severity.INFO, TOOL_NAME, f'Chapter # {file_num_int} name is: "{chapter_name}"')

        chapter_name_sanitized = chapter_name.replace('"', '').strip()
        if not chapter_name_sanitized:
            log(Severity.ERROR, TOOL_NAME, f'CSV row {file_num_int} has an empty chapter name')
            return None
        rename_plan.append((mka_file.path, f'{file_num_int} - {chapter_name_sanitized}.mka'))

    plan = plan_named_renames(rename_plan)
    if not plan.valid:
        log(Severity.ERROR, TOOL_NAME, '\n'.join(entry.error for entry in plan.entries if entry.error))
        return None
    return plan



# ----------------------------------------------------------------------------------------------------------------------
# ACTION

def rename_from_csv(target_dir_path: str | Path) -> bool:
    """
    Rename top-level Chapter_XX.mka files using chapter names from the directory's single CSV file.

    The full batch is validated before any rename is performed.
    """

    target_dir = dirUtils.Directory(Path(target_dir_path))

    if not target_dir.is_dir():
        log(Severity.ERROR, TOOL_NAME, 'Invalid Directory Path')
        return False

    csv_file = _get_csv_file(target_dir)

    if csv_file is None:
        return False

    row_lst = _get_chapter_rows(csv_file)
    rename_plan = _build_rename_plan(target_dir, row_lst)

    if rename_plan is None:
        return False

    if not rename_plan.changes:
        return False

    result = apply_renames(rename_plan)
    if not result.success:
        detail = result.error
        if result.recovery:
            detail += '\nManual recovery needed:\n' + '\n'.join(
                f'{current} → {original}: {error}' for current, original, error in result.recovery)
        log(Severity.ERROR, TOOL_NAME, f'Rename failed: {detail}')
        return False
    log(Severity.INFO, TOOL_NAME, f'Successfully renamed {len(result.entries)} MKA files')
    return True
