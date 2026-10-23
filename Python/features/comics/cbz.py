"""CBZ compression orchestration and the established image-retention policy."""

from __future__ import annotations

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path
from typing import *
from commonUtils.filesystem import files as fileUtils, directories as dirUtils
from commonUtils.runtime.diagnostics import *
from features.images import processing as imageUtils
import os
import zipfile
from commonUtils.filesystem.storage import temporary_directory, temporary_workspace
from PIL import Image
from commonUtils.formats import zipType
from .comicinfo import ComicInfoXML
from .compression_stats import CompressionStats, CompressionLog
from .sanitization import CBZSanitizationMixin
from .browser_support import ComicBrowserMixin
from .archive_io import replace_archive, validate_archive_members
from services.documents.zip_passwords import resolve_password
from commonUtils.archives.zip_access import open_archive, authenticate


# User Defined Settings

# Default directory for conversion (What shows up as default in the UI)
default_path_to_convert_cbz = Path(fileUtils.get_user_home_dir(), 'Server', 'Local', 'Server-Lib-ComicRack')

# Compression 'quality' ranges from 1 (lowest, smallest size) to 95 (highest, biggest size)
# Should be higher for color than grayscale, else causes much-worse looking results

# # JPG Settings
# img_quality_color = 70  # Acceptable: 50, Good: 70, Overkill: 90
# img_quality_grayscale = 30  # Acceptable: 15, Good: 30, Overkill: 45
# max_long_edge: Union[None, int] = None
# max_height: Union[None, int] = 2560

# WEBP Settings
cbz_img_quality_color = 60  # Acceptable: 45, Good: 60, Overkill: 90
cbz_img_quality_grayscale = 35  # Acceptable: 25, Good: 35, Overkill: 45
cbz_img_max_long_edge: Union[None, int] = None
cbz_img_max_height: Union[None, int] = 2400

# Decide to keep the compressed image if its size is smaller than this percentage of the original.
cbz_img_min_allowed_compression_percentage = 75

# Legacy paths retained for callers of the ComicInfo export helper.
# Compression itself uses a private TemporaryDirectory for each archive.
temp_compression_path = temporary_directory(create=False) / 'CBZ_Compression'
temp_dir_extracted_cbz = Path(temp_compression_path, '1_Extracted_CBZ')
temp_dir_compressed_imgs = Path(temp_compression_path, '2_Compressed_Images')
temp_dir_result = Path(temp_compression_path, '3_Result')


tool_name = 'features.comics.cbz'


def validate_compression_options(always_keep_compressed: bool,
                                 preserve_animated_and_multipage_originals: bool) -> bool:
    if always_keep_compressed and preserve_animated_and_multipage_originals:
        log(Severity.ERROR, tool_name,
            'Preserve animated and multipage originals cannot be used at same time as always keep compressed images.')
        return False
    return True


class CBZImageFile(imageUtils.ImageFile):
    def __init__(self, path: Path):
        super().__init__(path)

    def get_comicinfo_xml_line(self, page_num: int):
        """
        Get the line for the image as it would appear in ComicInfo.XML
        """
        if page_num == 0:
            return f'    <Page Image="{page_num}" ImageSize="{self.size}" ImageWidth="{self.width}" ImageHeight="{self.height}" Type="FrontCover" />'
        else:
            return f'    <Page Image="{page_num}" ImageSize="{self.size}" ImageWidth="{self.width}" ImageHeight="{self.height}" />'


def _validate_compression_outputs(pages: list[CBZImageFile], preserved_paths: set[Path], source_dir: Path):
    """Reject empty archives and case-insensitive output collisions before encoding."""
    if not pages:
        raise ValueError('Archive contains no image pages')
    output_paths = set()
    for page in pages:
        relative = page.path.relative_to(source_dir)
        if page.path not in preserved_paths:
            relative = relative.with_suffix('.webp')
        key = relative.as_posix().casefold()
        if key in output_paths:
            raise ValueError(f'Pages would overwrite the same WebP file: {relative}')
        output_paths.add(key)


class CBZFile(ComicBrowserMixin, CBZSanitizationMixin, zipType.ZIPFile):
    def __init__(self, path: Path):
        super().__init__(path)

        # Check if correct extension
        self.is_valid = self.ext == 'cbz'
        if not self.is_valid:
            raise ValueError(f'This CBZFile is invalid: {self.path}')

        # Compression stats
        self.last_error = ''
        self.compression_stats: CompressionStats = CompressionStats()
        # Compression log
        self.compression_log: CompressionLog = CompressionLog(self.file_name)

    def is_already_compressed(self):
        password = resolve_password(self.path, configured_only=True)
        with open_archive(self.path, password=password) as archive:
            return 'CompressionLog.txt' in archive.namelist()

    def export_comicinfo_xml_with_updated_pages(self, cbz_img_cls_lst: List[CBZImageFile], export_path: Path, extracted_dir: Path | None = None):
        # Build ComicInfo.xml with updated pages list (If existing ComicInfo.xml found)
        comic_info_xml_path = Path(extracted_dir or temp_dir_extracted_cbz, 'ComicInfo.xml')
        if os.path.isfile(comic_info_xml_path):
            msg = 'ComicInfo.xml located! Rebuilding with updated pages list...'
            log(Severity.DEBUG, tool_name, msg)
            self.compression_stats.has_comicinfo_xml = True
            comic_info_xml = ComicInfoXML(comic_info_xml_path)
            comic_info_xml.read_lines()  # Import existing ComicInfo.xml
            result = comic_info_xml.update_pages_in_line_lst(cbz_img_cls_lst)  # Update pages to match provided cbz_img_cls_lst
            if not result:
                msg = 'ComicInfo.xml did not successfully update pages in line list!'
                log(Severity.ERROR, tool_name, msg)
                return False
            comic_info_xml.write_lines(export_path)  # Export in given folder
        else:
            msg = ('ComicInfo.xml unfortunately missing from original file! '
                   'Cannot rebuild updated pages list. Not a deal breaker.')
            log(Severity.WARNING, tool_name, msg)
            self.compression_stats.has_comicinfo_xml = False
        return True

    def compress_to_webp(self, always_keep_compressed: bool = False,
                         preserve_animated_and_multipage_originals: bool | None = None,
                         *, progress=lambda message: None):
        """Compress in an isolated workspace; replace the original only on success."""
        self.last_error = ''
        self.compression_stats.reset()
        self.compression_log.reset()
        if preserve_animated_and_multipage_originals is None:
            preserve_animated_and_multipage_originals = not always_keep_compressed
        if not validate_compression_options(always_keep_compressed, preserve_animated_and_multipage_originals):
            return False
        try:
            original_stat = self.path.stat()
            with temporary_workspace(prefix='logistics-cbz-', ignore_cleanup_errors=True) as workspace:
                return self._compress_to_webp(Path(workspace), always_keep_compressed, original_stat,
                                              preserve_animated_and_multipage_originals, progress)
        except Exception as error:
            self.last_error = str(error)
            log(Severity.ERROR, tool_name, f'Compression failed for "{self.path}": {error}')
            return False

    def _collect_compression_pages(self, source_dir: Path, preserve_originals: bool) -> tuple[list[CBZImageFile], set[Path]]:
        """Validate sanitized members and capture pages that must retain every frame."""
        pages: list[CBZImageFile] = []
        preserved_paths: set[Path] = set()
        directory = dirUtils.Directory(source_dir)
        for member in directory.list_files(recursive=True):
            if member.file_name == 'ComicInfo.xml' and member.path.parent != source_dir:
                raise ValueError(f'Nested ComicInfo.xml would be omitted: {member.path}')
            if member.ext in imageUtils.image_file_cls_supported_ext_lst:
                # Reject unreadable pages before ImageFile's interactive dimension error.
                with Image.open(member.path) as image:
                    if preserve_originals and getattr(image, 'n_frames', 1) > 1:
                        preserved_paths.add(member.path)
                    image.verify()
                page = CBZImageFile(member.path)
                self.compression_stats.original_images_size += page.size
                pages.append(page)
            elif member.file_name not in ['ComicInfo.xml', 'CompressionLog.txt']:
                raise ValueError(
                    f'Unexpected File within "{self.path}" NOT CAUGHT OR '
                    f'CLEANED DURING SANITIZE: "{member.file_name}"')
        return pages, preserved_paths

    def _encode_compression_pages(self, pages: list[CBZImageFile], preserved_paths: set[Path],
                                  source_dir: Path, compressed_dir: Path, progress: Callable[[str], None]) -> bool:
        """Encode static pages; preserved originals are neither decoded again nor counted as encoded."""
        for page_index, page in enumerate(pages, 1):
            progress(f'Compressing page {page_index}/{len(pages)}: {self.path}')
            if page.path in preserved_paths:
                continue
            output = compressed_dir / page.path.relative_to(source_dir).with_suffix('.webp')
            if not page.compress(dest_path=output,
                                 quality_grayscale=cbz_img_quality_grayscale,
                                 quality_color=cbz_img_quality_color,
                                 max_long_edge=cbz_img_max_long_edge,
                                 max_height=cbz_img_max_height,
                                 preserve_alpha=False):
                message = f'An error occurred whilst compressing {page.file_name}!'
                self.last_error = message
                log(Severity.ERROR, 'cbzUtils.CBZFile.compress_to_webp', message)
                return False
            self.compression_stats.compressed_images_size += page.compressed_image.size
        return True

    def _select_compression_pages(self, pages: list[CBZImageFile], preserved_paths: set[Path],
                                  always_keep_compressed: bool) -> list[CBZImageFile]:
        """Apply the existing strict size threshold and record each retained-page verdict."""
        kept_pages: list[CBZImageFile] = []
        for page_number, page in enumerate(pages, 1):
            if page.path in preserved_paths:
                kept = page
                self.compression_log.append(
                    f'Page #{page_number:04d}: {kept.get_description()}, Verdict: Preserved animated/multipage original')
                self.compression_stats.kept_images_original_cnt += 1
            elif always_keep_compressed or page.compressed_image.size < page.size * cbz_img_min_allowed_compression_percentage / 100:
                verdict = 'ALWAYS Compressed Image' if always_keep_compressed else 'Compressed Image'
                kept = page.compressed_image
                self.compression_log.append(f'Page #{page_number:04d}: "{kept.get_description()}, Verdict: {verdict}')
                self.compression_stats.kept_images_compressed_cnt += 1
            else:
                kept = page
                self.compression_log.append(f'Page #{page_number:04d}: {kept.get_description()}, Verdict: Original Image')
                self.compression_stats.kept_images_original_cnt += 1
            self.compression_stats.kept_images_size += kept.size
            kept_pages.append(kept)
        return kept_pages

    def _compress_to_webp(self, workspace: Path, always_keep_compressed: bool, original_stat,
                          preserve_animated_and_multipage_originals: bool, progress=lambda message: None):
        """Extract and validate, encode and choose pages, then publish one verified archive."""
        source_dir = workspace / '1_Extracted_CBZ'
        compressed_dir = workspace / '2_Compressed_Images'
        result_dir = workspace / '3_Result'
        log(Severity.INFO, tool_name, f'Compressing "{self.file_name}"!')
        self.compression_log.append_msg_start(cbz_img_quality_grayscale, cbz_img_quality_color, always_keep_compressed)
        if preserve_animated_and_multipage_originals:
            self.compression_log.append('Parameter: Preserve animated and multipage originals')

        progress(f'Extracting {self.path}')
        source_dir.mkdir()
        validate_archive_members(self.path)
        password = resolve_password(self.path, configured_only=True)
        if password is not None:
            authenticate(self.path, password, all_members=True, for_rewrite=True)
        if not self.extract(source_dir, password=password):
            message = f'Unable to extract "{self.path}" properly!'
            self.last_error = message
            log(Severity.ERROR, tool_name, message)
            return False
        progress(f'Sanitizing {self.path}')
        if not self.sanitize_extracted_cbz(source_dir):
            message = f'Unable to sanitize extracted archive "{self.path}" properly!'
            self.last_error = message
            log(Severity.ERROR, tool_name, message)
            return False
        pages, preserved_paths = self._collect_compression_pages(
            source_dir, preserve_animated_and_multipage_originals)

        compressed_dir.mkdir()
        _validate_compression_outputs(pages, preserved_paths, source_dir)
        if not self._encode_compression_pages(pages, preserved_paths, source_dir, compressed_dir, progress):
            return False
        kept_pages = self._select_compression_pages(pages, preserved_paths, always_keep_compressed)
        result_dir.mkdir()
        for page in kept_pages:
            source_root = compressed_dir if page.path.is_relative_to(compressed_dir) else source_dir
            page.copy_file(result_dir / page.path.relative_to(source_root))

        if not self.export_comicinfo_xml_with_updated_pages(
                cbz_img_cls_lst=kept_pages, export_path=result_dir / 'ComicInfo.xml', extracted_dir=source_dir):
            raise ValueError('ComicInfo.xml page update failed')
        self.compression_log.append_msg_end(self.compression_stats)
        self.compression_log.export(result_dir / 'CompressionLog.txt')
        progress(f'Building and verifying {self.path}')
        replace_archive(result_dir, self.path, expected_stat=original_stat, password=password)
        message = (f'Completed Compression of "{self.file_name}" ({self.compression_stats.get_original_size_mb():.2f} MB '
                   f'> {self.compression_stats.get_new_size_mb():.2f} MB)!')
        log(Severity.INFO, tool_name, message)
        return True


def batch_compress_cbz(target_dir: Union[str, Path], recursive: bool = True, always_keep_compressed: bool = False,
                       preserve_animated_and_multipage_originals: bool | None = None, *,
                       progress=lambda done, total, message: None, cancelled=lambda: False) -> CompressionStats | None:
    """Compress unmarked CBZs independently and return aggregate statistics.

    Preserve the established cleanup, ordering, padding, WebP settings and
    strict size-retention rule. A failed archive is kept intact and the batch
    continues with later files. Only successful results enter size totals.
    Conflicting options log an error and return None before accessing archives.
    """
    if preserve_animated_and_multipage_originals is None:
        preserve_animated_and_multipage_originals = not always_keep_compressed
    if not validate_compression_options(always_keep_compressed, preserve_animated_and_multipage_originals):
        return None

    # Display basic information in console
    log_message = f'Initialize Batch Compress .CBZ in {target_dir} '
    if recursive:
        log_message += '(Recursive)'
    else:
        log_message += '(Not Recursive)'
    log(Severity.INFO, tool_name, log_message)

    # Get list of .CBZ files
    target_dir = dirUtils.Directory(Path(target_dir) if isinstance(target_dir, str) else target_dir)
    cbz_file_lst: List[fileUtils.File] = target_dir.list_files(recursive=recursive, filter_extension='cbz')

    return _compress_cbz_paths([file.path for file in cbz_file_lst], always_keep_compressed,
                               preserve_animated_and_multipage_originals, progress=progress, cancelled=cancelled)


def compress_selected_cbz(targets, recursive=True, always_keep_compressed=False,
                          preserve_animated_and_multipage_originals=None, *,
                          progress=lambda done, total, message: None, cancelled=lambda: False):
    """Compress a file/folder selection once per CBZ using the batch skip policy."""
    from .selection import selected_comics
    if preserve_animated_and_multipage_originals is None:
        preserve_animated_and_multipage_originals = not always_keep_compressed
    if not validate_compression_options(always_keep_compressed, preserve_animated_and_multipage_originals):
        return None
    paths = selected_comics(targets, recursive=recursive)
    return _compress_cbz_paths(paths, always_keep_compressed, preserve_animated_and_multipage_originals,
                               progress=progress, cancelled=cancelled)


def _compress_cbz_paths(paths, always_keep_compressed, preserve_animated_and_multipage_originals,
                        *, progress=lambda done, total, message: None, cancelled=lambda: False):
    compression_stats = CompressionStats()
    paths = tuple(path for path in paths if not Path(path).name.startswith('._'))
    compression_stats.total_file_count = len(paths)
    for index, path in enumerate(paths):
        if cancelled():
            compression_stats.cancelled = True
            compression_stats.remaining = list(paths[index:])
            break
        progress(index, len(paths), f'Checking {path}')
        try:
            comic = CBZFile(path)
            if comic.is_already_compressed():
                compression_stats.already_compressed_file_count += 1
            elif comic.compress_to_webp(
                    always_keep_compressed=always_keep_compressed,
                    preserve_animated_and_multipage_originals=preserve_animated_and_multipage_originals,
                    progress=lambda message: progress(index, len(paths), message)):
                compression_stats.compressed_file_count += 1
                compression_stats += comic.compression_stats
            else:
                raise RuntimeError(comic.last_error or 'Compression failed; see the log for details')
        except Exception as error:
            compression_stats.error_during_compression += 1
            compression_stats.failed[path] = str(error)
            log(Severity.ERROR, tool_name, f'Cannot compress "{path}": {error}')
        compression_stats.processed_file_count += 1
        progress(index + 1, len(paths), f'{index + 1} / {len(paths)} comics processed')
    compression_stats.print_summary()
    return compression_stats
