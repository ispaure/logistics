"""Transactional, line-preserving ComicInfo.xml author and series edits."""

from pathlib import Path
from commonUtils.storage import temporary_workspace
from xml.etree import ElementTree
from xml.sax.saxutils import escape

import config
from commonUtils import dirUtils, zipUtils
from commonUtils.debugUtils import Severity, log
from commonUtils.fileTypes import txtType
from .archive_io import replace_archive, validate_archive_members
from services.zip_passwords import resolve_password
from commonUtils.archives.zip_access import authenticate
from commonUtils.operations import BatchResult, run_batch


def get_temp_loc_edit_comicinfoxml() -> Path:
    """Legacy workspace location; edits now use isolated temporary directories."""
    return Path(config.LogisticsConfig().temp_path, 'Edit-ComicInfoXML')


def _replace_tag(file_path: Path, tag: str, search: str, replacement: str) -> bool:
    file_path = Path(file_path)
    try:
        original_stat = file_path.stat()
        validate_archive_members(file_path)
        password = resolve_password(file_path, configured_only=True)
        if password is not None:
            authenticate(file_path, password, all_members=True, for_rewrite=True)
        with temporary_workspace(prefix='logistics-comicinfo-', ignore_cleanup_errors=True) as workspace:
            extracted = Path(workspace)
            if not zipUtils.unzip_file(file_path, extracted, pwd=password):
                raise OSError(f'Could not extract {file_path}')
            xml_file = txtType.TXTFile(extracted / 'ComicInfo.xml')
            xml_file.read_lines()
            ElementTree.fromstring('\n'.join(xml_file.line_lst))
            search_string = f'<{tag}>{search}</{tag}>'
            replace_string = f'<{tag}>{escape(replacement)}</{tag}>'
            updated_lines = [line.replace(search_string, replace_string) for line in xml_file.line_lst]
            if updated_lines == xml_file.line_lst:
                return True
            ElementTree.fromstring('\n'.join(updated_lines))
            xml_file.line_lst = updated_lines
            xml_file.write_lines()
            replace_archive(extracted, file_path, expected_stat=original_stat, password=password)
        return True
    except Exception as error:
        log(Severity.ERROR, 'ComicInfo edit', f'Could not update "{file_path}": {error}')
        return False


def comic_info_xml_replace_author(file_path: Path, search: str) -> bool:
    """Replace the exact Writer tag with the CBZ parent directory name."""
    file_path = Path(file_path)
    return _replace_tag(file_path, 'Writer', search, file_path.parent.name)


def comic_info_xml_replace_series(file_path: Path, search: str, suffix: str) -> bool:
    """Replace the exact Series tag with the supplied prefix plus the parent name."""
    file_path = Path(file_path)
    return _replace_tag(file_path, 'Series', search, suffix + file_path.parent.name)


def _batch_replace(target_dir, operation, *, progress=lambda done, total, message: None,
                   cancelled=lambda: False, report=False):
    files = dirUtils.Directory(Path(target_dir)).list_files(recursive=True, filter_extension='cbz')
    if not files:
        log(Severity.WARNING, 'ComicInfo batch edit', 'Did not find a .CBZ file')
    result = run_batch([file.path for file in files], operation, progress=progress, cancelled=cancelled)
    return result if report else bool(result)


def batch_rename_author_to_dir_name(target_dir, author_tag_to_replace: str, **feedback) -> bool | BatchResult:
    return _batch_replace(target_dir, lambda path: comic_info_xml_replace_author(path, author_tag_to_replace), **feedback)


def batch_rename_series_to_dir_name(target_dir, series_tag_to_replace: str, suffix: str, **feedback) -> bool | BatchResult:
    return _batch_replace(target_dir, lambda path: comic_info_xml_replace_series(path, series_tag_to_replace, suffix), **feedback)
