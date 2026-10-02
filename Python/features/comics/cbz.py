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
from commonUtils import fileUtils, dirUtils
from commonUtils.debugUtils import *
from features.images import processing as imageUtils
import os
import zipfile
from tempfile import TemporaryDirectory
from PIL import Image
from commonUtils.fileTypes import zipType
from .comicinfo import ComicInfoXML
from .compression_stats import CompressionStats, CompressionLog
from .sanitization import CBZSanitizationMixin
from .archive_io import replace_archive, validate_archive_members


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
temp_compression_path = Path(fileUtils.get_user_home_dir(), 'Temp_CBZ_Compression')
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


class CBZFile(CBZSanitizationMixin, zipType.ZIPFile):
    def __init__(self, path: Path):
        super().__init__(path)

        # Check if correct extension
        self.is_valid = self.ext == 'cbz'
        if not self.is_valid:
            log(Severity.CRITICAL, tool_name, f'This CBZFile is invalid: {self.path}')

        # Compression stats
        self.compression_stats: CompressionStats = CompressionStats()
        # Compression log
        self.compression_log: CompressionLog = CompressionLog(self.file_name)

    def is_already_compressed(self):
        with zipfile.ZipFile(self.path) as archive:
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
                         preserve_animated_and_multipage_originals: bool | None = None):
        """Compress in an isolated workspace; replace the original only on success."""
        self.compression_stats.reset()
        self.compression_log.reset()
        if preserve_animated_and_multipage_originals is None:
            preserve_animated_and_multipage_originals = not always_keep_compressed
        if not validate_compression_options(always_keep_compressed, preserve_animated_and_multipage_originals):
            return False
        try:
            original_stat = self.path.stat()
            with TemporaryDirectory(prefix='logistics-cbz-', ignore_cleanup_errors=True) as workspace:
                return self._compress_to_webp(Path(workspace), always_keep_compressed, original_stat,
                                              preserve_animated_and_multipage_originals)
        except Exception as error:
            log(Severity.ERROR, tool_name, f'Compression failed for "{self.path}": {error}')
            return False

    def _compress_to_webp(self, workspace: Path, always_keep_compressed: bool, original_stat,
                          preserve_animated_and_multipage_originals: bool):
        func_name = 'compress_to_webp'
        temp_dir_extracted_cbz = workspace / '1_Extracted_CBZ'
        temp_dir_compressed_imgs = workspace / '2_Compressed_Images'
        temp_dir_result = workspace / '3_Result'

        # START LOGS
        log(Severity.INFO, tool_name, f'Compressing "{self.file_name}"!')
        self.compression_log.append_msg_start(cbz_img_quality_grayscale, cbz_img_quality_color, always_keep_compressed)
        if preserve_animated_and_multipage_originals:
            self.compression_log.append('Parameter: Preserve animated and multipage originals')

        # --------------------------------------------------------------------------------------------------------------
        # STEP ONE : EXTRACTION OF .CBZ IN TEMP DIRECTORY
        temp_dir_extracted_cbz.mkdir()

        validate_archive_members(self.path)
        result = self.extract(temp_dir_extracted_cbz)
        if not result:
            msg = f'Unable to extract "{self.path}" properly!'
            log(Severity.ERROR, tool_name, msg)
            return False

        # --------------------------------------------------------------------------------------------------------------
        # STEP TWO: SANITIZE EXTRACTED DIRECTORY
        result = self.sanitize_extracted_cbz(temp_dir_extracted_cbz)
        if not result:
            msg = f'Unable to sanitize extracted archive "{self.path}" properly!'
            log(Severity.ERROR, tool_name, msg)
            return False

        # --------------------------------------------------------------------------------------------------------------
        # STEP THREE: GATHER LIST OF IMAGE FILES FROM EXTRACTED DIRECTORY
        img_file_cls_lst: List[CBZImageFile] = []
        preserved_paths = set()
        extracted_dir = dirUtils.Directory(temp_dir_extracted_cbz)
        extracted_file_lst: List[fileUtils.File] = extracted_dir.list_files(recursive=True)
        for extracted_file in extracted_file_lst:
            if (extracted_file.file_name == 'ComicInfo.xml'
                    and extracted_file.path.parent != temp_dir_extracted_cbz):
                raise ValueError(f'Nested ComicInfo.xml would be omitted: {extracted_file.path}')
            if extracted_file.ext in imageUtils.image_file_cls_supported_ext_lst:
                # Reject unreadable pages before ImageFile's interactive dimension error.
                with Image.open(extracted_file.path) as image:
                    if preserve_animated_and_multipage_originals and getattr(image, 'n_frames', 1) > 1:
                        preserved_paths.add(extracted_file.path)
                    image.verify()
                image_file_cls = CBZImageFile(extracted_file.path)
                self.compression_stats.original_images_size += image_file_cls.size  # Log Size in Stats
                img_file_cls_lst.append(image_file_cls)
            elif extracted_file.file_name not in ['ComicInfo.xml', 'CompressionLog.txt']:
                msg = (f'Unexpected File within "{self.path}" NOT CAUGHT OR '
                       f'CLEANED DURING SANITIZE: "{extracted_file.file_name}"')
                log(Severity.CRITICAL, f'cbzUtils.CBZFile.{func_name}', msg)
                return False

        # --------------------------------------------------------------------------------------------------------------
        # STEP FOUR: COMPRESS LIST OF IMAGES TO .WEBP
        temp_dir_compressed_imgs.mkdir()

        if not img_file_cls_lst:
            raise ValueError('Archive contains no image pages')
        output_paths = set()
        for image in img_file_cls_lst:
            relative = image.path.relative_to(temp_dir_extracted_cbz)
            if image.path not in preserved_paths:
                relative = relative.with_suffix('.webp')
            key = relative.as_posix().casefold()
            if key in output_paths:
                raise ValueError(f'Pages would overwrite the same WebP file: {relative}')
            output_paths.add(key)

        # Compress to WEBP
        for img_file_cls in img_file_cls_lst:
            if img_file_cls.path in preserved_paths:
                continue

            # Get output path
            # Doing this to account for potential sub folders.
            img_compress_file_path = temp_dir_compressed_imgs / img_file_cls.path.relative_to(
                temp_dir_extracted_cbz).with_suffix('.webp')

            result = img_file_cls.compress(dest_path=img_compress_file_path,
                                           quality_grayscale=cbz_img_quality_grayscale,
                                           quality_color=cbz_img_quality_color,
                                           max_long_edge=cbz_img_max_long_edge,
                                           max_height=cbz_img_max_height,
                                           preserve_alpha=False)
            if not result:
                msg = f'An error occurred whilst compressing {img_file_cls.file_name}!'
                log(Severity.ERROR, f'cbzUtils.CBZFile.{func_name}', msg)
                return False
            self.compression_stats.compressed_images_size += img_file_cls.compressed_image.size  # Log Size in Stats

        # --------------------------------------------------------------------------------------------------------------
        # STEP FIVE: SELECT IMAGES TO KEEP
        page_count = 0
        kept_image_cls_lst: List[CBZImageFile] = []
        for img_file_cls in img_file_cls_lst:
            page_count += 1
            # Select compressed image if at least smaller by specified amount, else keep original
            if img_file_cls.path in preserved_paths:
                kept_image_cls = img_file_cls
                self.compression_log.append(
                    f'Page #{page_count:04d}: {kept_image_cls.get_description()}, Verdict: Preserved animated/multipage original')
                self.compression_stats.kept_images_original_cnt += 1
            elif always_keep_compressed or img_file_cls.compressed_image.size < img_file_cls.size * cbz_img_min_allowed_compression_percentage / 100:
                if always_keep_compressed:
                    verdict = 'ALWAYS Compressed Image'
                else:
                    verdict = 'Compressed Image'
                kept_image_cls = img_file_cls.compressed_image
                self.compression_log.append(f'Page #{page_count:04d}: "{kept_image_cls.get_description()}, Verdict: {verdict}')
                self.compression_stats.kept_images_compressed_cnt += 1
            else:
                kept_image_cls = img_file_cls
                self.compression_log.append(f'Page #{page_count:04d}: {kept_image_cls.get_description()}, Verdict: Original Image')
                self.compression_stats.kept_images_original_cnt += 1
            self.compression_stats.kept_images_size += kept_image_cls.size
            kept_image_cls_lst.append(kept_image_cls)

        # --------------------------------------------------------------------------------------------------------------
        # STEP SIX: MOVE KEPT IMAGES TO RESULT DIRECTORY
        temp_dir_result.mkdir()

        # Move kept images to result folder
        for kept_image_cls in kept_image_cls_lst:
            source_root = (temp_dir_compressed_imgs if kept_image_cls.path.is_relative_to(
                temp_dir_compressed_imgs) else temp_dir_extracted_cbz)
            kept_img_result_file_path = temp_dir_result / kept_image_cls.path.relative_to(source_root)

            # Copy image in Result folder
            if not fileUtils.copy_file(kept_image_cls.path, kept_img_result_file_path):
                raise OSError(f'Could not copy page: {kept_image_cls.path}')

        # --------------------------------------------------------------------------------------------------------------
        # STEP SEVEN: WRAP-UP OTHER FILES
        # Export ComicInfo.xml (With Updated Pages List!) to Result Directory
        if not self.export_comicinfo_xml_with_updated_pages(
                cbz_img_cls_lst=kept_image_cls_lst,
                export_path=Path(temp_dir_result, 'ComicInfo.xml'),
                extracted_dir=temp_dir_extracted_cbz):
            raise ValueError('ComicInfo.xml page update failed')
        # Add summary to compression log
        self.compression_log.append_msg_end(self.compression_stats)
        # Dump Compression Log File on Disk
        self.compression_log.export(Path(temp_dir_result, 'CompressionLog.txt'))

        # --------------------------------------------------------------------------------------------------------------
        # STEP EIGHT: FROM CONTENTS OF THE RESULT DIRECTORY, BUILD ARCHIVE OVERWRITING THE ORIGINAL .CBZ
        replace_archive(temp_dir_result, self.path, expected_stat=original_stat)

        # --------------------------------------------------------------------------------------------------------------
        # END LOGS
        msg = (f'Completed Compression of "{self.file_name}" ({self.compression_stats.get_original_size_mb():.2f} MB '
               f'> {self.compression_stats.get_new_size_mb():.2f} MB)!')
        log(Severity.INFO, tool_name, msg)
        return True


def batch_compress_cbz(target_dir: Union[str, Path], recursive: bool = True, always_keep_compressed: bool = False,
                       preserve_animated_and_multipage_originals: bool | None = None) -> CompressionStats | None:
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

    # Stats
    compression_stats = CompressionStats()

    # Get list of .CBZ files
    target_dir = dirUtils.Directory(Path(target_dir) if isinstance(target_dir, str) else target_dir)
    cbz_file_lst: List[fileUtils.File] = target_dir.list_files(recursive=recursive, filter_extension='cbz')

    # Build list of CBZFile
    cbz_file_cls_lst: List[CBZFile] = []
    for cbz_file in cbz_file_lst:
        if cbz_file.file_name.startswith('._'):
            log(Severity.WARNING, tool_name, f'Skipping file {cbz_file.path} because it is a macOS metadata file!')
            continue
        cbz_file_cls = CBZFile(cbz_file.path)
        cbz_file_cls_lst.append(cbz_file_cls)

    # Filter for cbz files which need conversion
    cbz_file_cls_to_compress_lst: List[CBZFile] = []
    for cbz_file_cls in cbz_file_cls_lst:
        try:
            already_compressed = cbz_file_cls.is_already_compressed()
        except (OSError, zipfile.BadZipFile) as error:
            compression_stats.error_during_compression += 1
            log(Severity.ERROR, tool_name, f'Cannot read "{cbz_file_cls.path}": {error}')
            continue
        if already_compressed:
            compression_stats.already_compressed_file_count += 1
            log(Severity.WARNING, tool_name, f'Skipping "{cbz_file_cls.file_name}"; Already Compressed!')
        else:
            cbz_file_cls_to_compress_lst.append(cbz_file_cls)

    # Log number of files not yet compressed
    pending_percentage = len(cbz_file_cls_to_compress_lst) / len(cbz_file_cls_lst) * 100 if cbz_file_cls_lst else 0
    log(Severity.INFO, tool_name, f'{len(cbz_file_cls_to_compress_lst)}/{len(cbz_file_cls_lst)} ({pending_percentage}%) of CBZ Files Awaiting Compression!')

    # Compress CBZ
    compression_stats.total_file_count = len(cbz_file_cls_lst)
    for cbz_file in cbz_file_cls_to_compress_lst:
        result = cbz_file.compress_to_webp(
            always_keep_compressed=always_keep_compressed,
            preserve_animated_and_multipage_originals=preserve_animated_and_multipage_originals)
        if result:
            compression_stats.compressed_file_count += 1
            compression_stats += cbz_file.compression_stats
        else:
            log(Severity.ERROR, tool_name, f'Skipped compression of "{cbz_file.path}" because it encountered an unrecoverable error! See log for details')
            compression_stats.error_during_compression += 1

    compression_stats.print_summary()
    return compression_stats
