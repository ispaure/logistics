from __future__ import annotations
"""
Hosts functions related to CBZ (ComicBook Zip) files
"""

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
from commonUtils import fileUtils, xmlUtils, zipUtils
from commonUtils.debugUtils import *
from . import imageUtils
from datetime import datetime


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

# Temporary Folders for Compression
temp_compression_path = Path(fileUtils.get_user_home_dir(), 'Temp_CBZ_Compression')
temp_dir_extracted_cbz = Path(temp_compression_path, '1_Extracted_CBZ')
temp_dir_compressed_imgs = Path(temp_compression_path, '2_Compressed_Images')
temp_dir_result = Path(temp_compression_path, '3_Result')


tool_name = 'commonUtils.cbzUtils'


class ComicInfoXML(xmlUtils.XMLFile):
    def __init__(self, path: Path):
        super().__init__(path)

    def update_pages_in_line_lst(self, cbz_image_file_lst: List[CBZImageFile]) -> bool:
        """
        Updates comic pages in the ComicInfo.xml line list, from the provided image list (Page count & information for each page)
        """

        # Local helper can directly access cbz_image_file_lst and updated_line_lst
        def append_pages_lines():
            for page_number, cbz_image_file in enumerate(cbz_image_file_lst):
                page_line = cbz_image_file.get_comicinfo_xml_line(page_number)
                updated_line_lst.append(page_line)

        # Check that the list of line isn't 0 lines long, which means the lines were not previously loaded!
        if len(self.line_lst) == 0:
            log(Severity.CRITICAL, tool_name, 'Cannot Update Pages in ComicInfo.xml line List as it is empty and not loaded!')
            return False

        went_through_pages_section = False  # Update once have written the page lines
        updated_line_lst = []
        in_page_section = False

        for line in self.line_lst:
            if line.startswith('  <PageCount>'):
                updated_line_lst.append(f'  <PageCount>{len(cbz_image_file_lst)}</PageCount>')
                continue
            if not in_page_section:
                if line == '  <Pages />':
                    log(Severity.WARNING, tool_name, 'ComicInfoXML.update_pages_in_line_lst: Hit the <Pages /> line, meaning no page information was previously registered. Repairing...')
                    updated_line_lst.append('  <Pages>')
                    append_pages_lines()
                    updated_line_lst.append('  </Pages>')
                    went_through_pages_section = True
                elif line == '  <Pages>':
                    updated_line_lst.append(line)
                    append_pages_lines()
                    in_page_section = True
                else:
                    updated_line_lst.append(line)
            else:
                if line == '  </Pages>':
                    updated_line_lst.append(line)
                    in_page_section = False
                    went_through_pages_section = True

        if not went_through_pages_section:
            log(Severity.CRITICAL, tool_name, f'Did not go through Pages Section of ComicInfo.XML! {self.line_lst}')
            return False

        self.line_lst = updated_line_lst
        return True


class CompressionStats:
    def __init__(self):
        self.has_comicinfo_xml: Optional[bool] = None
        self.original_images_size = 0
        self.compressed_images_size = 0
        self.kept_images_size = 0
        self.kept_images_compressed_cnt = 0
        self.kept_images_original_cnt = 0
        self.total_file_count = 0
        self.compressed_file_count = 0
        self.already_compressed_file_count = 0
        self.error_during_compression = 0

    def reset(self):
        for key in (
            "original_images_size", "compressed_images_size",
            "kept_images_size", "kept_images_compressed_cnt",
            "kept_images_original_cnt", "total_file_count",
            "compressed_file_count", "already_compressed_file_count",
            "error_during_compression"
        ):
            setattr(self, key, 0)
        self.has_comicinfo_xml = None

    def __add__(self, other: CompressionStats) -> CompressionStats:
        new = CompressionStats()
        for key in (
            "original_images_size", "compressed_images_size",
            "kept_images_size", "kept_images_compressed_cnt",
            "kept_images_original_cnt", "total_file_count",
            "compressed_file_count", "already_compressed_file_count",
            "error_during_compression"
        ):
            setattr(new, key, getattr(self, key) + getattr(other, key))
        return new

    def __iadd__(self, other: CompressionStats) -> CompressionStats:
        for key in (
            "original_images_size", "compressed_images_size",
            "kept_images_size", "kept_images_compressed_cnt",
            "kept_images_original_cnt", "total_file_count",
            "compressed_file_count", "already_compressed_file_count",
            "error_during_compression"
        ):
            setattr(self, key, getattr(self, key) + getattr(other, key))
        return self

    def __to_mb(self, value_bytes: int) -> float:
        return value_bytes / (1024 * 1024)

    def get_summary(self):

        summary = "||Compression Statistics||\n"

        # conversions and helpers

        reduction_bytes = self.original_images_size - self.kept_images_size
        new_size_mb = self.get_new_size_mb()
        orig_size_mb = self.get_original_size_mb()
        reduction_mb = self.__to_mb(reduction_bytes)

        if self.original_images_size == 0:
            reduction_pct = 'N/A'
            new_pct = 'N/A'
        else:
            reduction_pct = 100 - (self.kept_images_size / self.original_images_size * 100)
            reduction_pct = f'-{reduction_pct:.2f}'
            new_pct = self.kept_images_size / self.original_images_size * 100
            new_pct = f'{new_pct:.2f}'

        if getattr(self, "total_file_count", 0) > 0:
            summary += (
                "  |CBZ Files|\n"
                f"    Total File Count in Dir:    {self.total_file_count}\n"
                f"    Already Compressed:         {self.already_compressed_file_count}\n"
                f"    Error During Compression:   {self.error_during_compression}\n"
                f"    Successful Compression:     {self.compressed_file_count}\n"
            )

        summary += (
            f"  |Images|\n"
            f"    Original # Kept:            {self.kept_images_original_cnt}\n"
            f"    Compressed # Kept:          {self.kept_images_compressed_cnt}\n"
            f"  |Archive|\n"
            f"    Original Size:              {orig_size_mb:.2f} MB\n"
            f"    Reduction Size:             {reduction_mb:.2f} MB\n"
            f"    New Size:                   {new_size_mb:.2f} MB\n"
            f"    Reduction (%):              {reduction_pct}%\n"
            f"    New (%):                    {new_pct}%"
        )

        return summary

    def get_original_size_mb(self):
        return self.__to_mb(self.original_images_size)

    def get_new_size_mb(self):
        return self.__to_mb(self.kept_images_size)

    def print_summary(self):
        """Print only the integer stats in a clean format."""
        print(self.get_summary())


class CompressionLog:
    def __init__(self, name: str):
        self.name: str = name
        self.ext = 'cbz'
        self.__compression_log_line_lst: List[str] = []

    def append(self, string: str):
        self.__compression_log_line_lst.append(string)

    def append_skip_line(self):
        self.__compression_log_line_lst.append('')

    def append_msg_start(self, quality_grayscale, quality_color, always_keep_compressed):
        self.append(f'|| Compression Log "{self.name}" ||')
        self.append(f'Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        self.append(f'Quality Setting for WEBP Compression: Grayscale: "{quality_grayscale}", Color: "{quality_color}"')
        if always_keep_compressed:
            self.append(f'Parameter: Always Keep Compressed Image, Regardless if Smaller')
        self.append_skip_line()

    def append_msg_end(self, compression_stats: CompressionStats):
        self.append_skip_line()
        self.append(compression_stats.get_summary())

    def reset(self):
        self.__compression_log_line_lst = []

    def export(self, export_path: Path):
        txt_file = fileUtils.TXTFile(export_path)
        txt_file.line_lst = self.__compression_log_line_lst
        txt_file.write_lines()


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


class CBZFile(zipUtils.ZIPFile):
    # TODO: Test with a large comics folder and see if issues occur.
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
        self.__compression_log_line_lst: List[str] = []

    def is_already_compressed(self):
        return any(f == 'CompressionLog.txt' for f in self.get_root_file_lst())

    def sanitize_extracted_cbz(self, extracted_dir) -> bool:
        """
        Sanitize files of an extracted CBZ whenever possible. AKA clean up dirty files!
        If not possible, return an error.
        """
        sanitize_tool_name = 'cbzUtils.CBZFile.sanitize_extracted_cbz'
        expected_file_name_lst = ['ComicInfo.xml', 'CompressionLog.txt']
        to_delete_file_name_lst = ['.DS_Store', 'Thumbs.db', 'Thumbs1.db']

        # Delete __MACOSX directories if there are any. Before evaluating other stuff.
        dir_path_lst = fileUtils.get_dirs_path_list(extracted_dir)
        for dir_path in dir_path_lst:
            if Path(dir_path).name == '__MACOSX':
                result = fileUtils.delete_dir(dir_path)
                if result:
                    msg = 'Found rogue folder "__MACOSX" in archive, deleted!'
                    log(Severity.WARNING, sanitize_tool_name, msg)
                # Abort (critical) if it could not delete directory
                else:
                    msg = f'Could not delete __MACOSX directory in {self.path}!'
                    log(Severity.CRITICAL, sanitize_tool_name, msg)
                    return False

        # Delete files we know we must delete (incl. from subdirectories)
        extracted_file_lst = fileUtils.get_file_path_list(extracted_dir, recursive=True)
        for extracted_file in extracted_file_lst:
            file_cls = fileUtils.File(Path(extracted_file))
            # If File identified to DELETE
            if file_cls.file_name in to_delete_file_name_lst:
                msg = f'Deleting file from to-delete list: "{file_cls.file_name}"'
                log(Severity.WARNING, sanitize_tool_name, msg)
                result = file_cls.delete_file()
                if not result:
                    log(Severity.CRITICAL, sanitize_tool_name, f'Could not delete file "{file_cls.file_name}"')
                    return False
                continue
            # If File expected in archive, continue
            elif file_cls.file_name in expected_file_name_lst:
                continue
            # If File is of these file types, not expected in archive unless previous "continue"
            elif file_cls.ext in ['txt', 'url', 'nfo', 'html', 'sfv', 'rtf', 'ini', 'dat', 'css']:
                msg = f'Deleting unexpected file of extension .{file_cls.ext}: "{file_cls.file_name}"'
                log(Severity.WARNING, sanitize_tool_name, msg)
                result = file_cls.delete_file()
                if not result:
                    log(Severity.CRITICAL, sanitize_tool_name, f'Could not delete file "{file_cls.file_name}"')
                    return False
                continue
            elif file_cls.ext not in imageUtils.image_file_cls_supported_ext_lst:
                msg = (f'Found unexpected file in archive!: "{file_cls.file_name}" Manual cleanup in the original'
                       f'.CBZ file required!')
                log(Severity.ERROR, sanitize_tool_name, msg)
                return False

        # If there is any subdirectory, it could be unexpected
        if fileUtils.has_subdirectories(extracted_dir):
            dir_path_lst = fileUtils.get_dirs_path_list(extracted_dir)

            # Abort if root has subdir + any unsuspected file (including any image)
            root_file_lst = fileUtils.get_file_path_list(extracted_dir, recursive=False)
            for root_file in root_file_lst:
                file_cls = fileUtils.File(Path(root_file))
                if file_cls.file_name not in expected_file_name_lst:
                    msg = ('There is at least one subdirectory and at least one unsuspected file at the root: '
                           f'"{file_cls.file_name}", which is not supported. Manual cleanup in the original '
                           f'.CBZ file required!')
                    log(Severity.ERROR, sanitize_tool_name, msg)
                    return False

            # ----------------------------------------------------------------------------------------------------------
            # Weird Edge case I had to account for (else it's repetitive manual work)
            # If there is exactly one directory, which itself contains no files and exactly one subdirectory
            # And that subdirectory does not contain itself anymore subdirectories, move the files to the directory.
            if len(dir_path_lst) == 1:
                dir_path = dir_path_lst[0]
                dir_subdir_lst = fileUtils.get_dirs_path_list(dir_path)
                dir_file_path_lst = fileUtils.get_file_path_list(dir_path, recursive=False)
                if len(dir_subdir_lst) == 1 and len(dir_file_path_lst) == 0:
                    subdir_path = Path(dir_subdir_lst[0])
                    if not fileUtils.has_subdirectories(subdir_path):
                        subdir_file_path_lst = fileUtils.get_file_path_list(subdir_path, recursive=False)
                        if len(subdir_file_path_lst) > 0:
                            msg = ('Found only a single directory, which itself contains no files and exactly one '
                                   'subdirectory, which itself contains files but not any more directories. '
                                   'Moving files from the subdirectory to the directory.')
                            log(Severity.WARNING, tool_name, msg)
                            for subdir_file_path in subdir_file_path_lst:
                                destination_file_path = subdir_file_path.replace(str(subdir_path), str(dir_path))
                                result = fileUtils.move_file(Path(subdir_file_path), Path(destination_file_path))
                                if not result:
                                    msg = f'File move unsuccessful (source: "{subdir_file_path}", destination: "{destination_file_path}")!'
                                    log(Severity.CRITICAL, sanitize_tool_name, msg)
                                    return False
                            result = fileUtils.delete_dir(subdir_path)
                            if not result:
                                msg = f'Directory deletion was unsuccessful: "{subdir_path}"!'
                                log(Severity.CRITICAL, sanitize_tool_name, msg)
                                return False

            # Refresh dir_path_lst because it may have changed
            dir_path_lst = fileUtils.get_dirs_path_list(extracted_dir)
            # ----------------------------------------------------------------------------------------------------------

            # Abort if any directory itself has a subdirectory
            for dir_path in dir_path_lst:
                if fileUtils.has_subdirectories(Path(dir_path)):
                    msg = (f'The subdirectory "{Path(dir_path).name}" has at least one subdirectory itself, which is '
                           f'not supported. Manual cleanup in the original .CBZ file required!')
                    log(Severity.ERROR, sanitize_tool_name, msg)
                    return False

            # If there was just one directory, move the files in it to the root
            if len(dir_path_lst) == 1:
                dir_path = dir_path_lst[0]
                subdir_file_lst = fileUtils.get_file_path_list(dir_path, recursive=False)
                for subdir_file in subdir_file_lst:
                    file_cls = fileUtils.File(Path(subdir_file))
                    destination_path = Path(extracted_dir, file_cls.file_name)
                    result = fileUtils.move_file(file_cls.path, destination_path)
                    if not result:
                        msg = f'File move unsuccessful (source: "{file_cls.path}", destination: "{destination_path}")!'
                        log(Severity.CRITICAL, sanitize_tool_name, msg)
                        return False
                # Delete empty dir after everything has been moved to the root
                if not fileUtils.has_subdirectories(Path(dir_path)) and len(fileUtils.get_file_path_list(dir_path, recursive=True)) == 0:
                    result = fileUtils.delete_dir(dir_path)
                    if not result:
                        msg = f'Could not delete "{dir_path}"!'
                        log(Severity.CRITICAL, tool_name, msg)
                        return False
                else:
                    msg = f'Could not delete "{dir_path}" because it is not empty!'
                    log(Severity.CRITICAL, tool_name, msg)
                    return False

        # Get updated list of files (things may have been moved in previous step)
        extracted_file_lst = fileUtils.get_file_path_list(extracted_dir, recursive=True)
        need_padding_repair = False
        for extracted_file in extracted_file_lst:
            file_cls = fileUtils.File(Path(extracted_file))
            if len(file_cls.file_name) < 2:  # If file name is incredibly short, throw error
                msg = (f'File "{file_cls.file_name}" has unbelievably tiny name. Manual cleanup in '
                       f'the original .CBZ file required!')
                log(Severity.ERROR, sanitize_tool_name, msg)
                return False
            elif file_cls.file_name[1] == '.' and file_cls.file_name[0] in '0123456789':
                msg = (f'Page "{file_cls.file_name}" within archive are named without padding (ex. 1.jpg), which can lead to improper '
                       f'sorting in applications such as ComicRack. Renaming with padding...')
                log(Severity.WARNING, sanitize_tool_name, msg)
                need_padding_repair = True
                break  # Identified that we need padding repair, no need to process further in verifications.

        # Padding repair
        if need_padding_repair:  # When flagged previously as needed.
            result = self.repair_padding(file_lst=extracted_file_lst)
            if not result:
                msg = f'Error whilst applying padding! Manual cleanup in the original .CBZ file required!'
                log(Severity.ERROR, sanitize_tool_name, msg)
                return False

        # Everything went as expected
        return True

    def repair_padding(self, file_lst: List[str]) -> bool:
        """
        Repair padding on a list of files
        """
        padding_tool_name = 'Repair .CBZ File Padding'

        # Get padding length
        if len(file_lst) < 90:  # Could put 99, but being safer than sorry
            padding_num_dec: int = 2
        elif len(file_lst) < 950:  # Could put 999, but being safer than sorry
            padding_num_dec: int = 3
        else:
            padding_num_dec: int = 5

        for file_path in file_lst:
            file_cls = fileUtils.File(Path(file_path))

            # Skip padding on non-image files
            if file_cls.ext not in imageUtils.image_file_cls_supported_ext_lst:
                continue

            # If there is not a single dot in the file name, throw an error
            if file_cls.file_name.count('.') != 1:
                msg = (f'File has weird number of dots in file name (just expecting number + extension!) '
                       f'Manual cleanup in the original .CBZ file required!')
                log(Severity.ERROR, padding_tool_name, msg)
                return False

            # Check there are only characters in name without extension
            for char in file_cls.name_without_ext:
                if char not in '0123456789':
                    msg = (f'File naming makes padding repair impossible! Name: "{file_cls.file_name}".'
                           f'Manual cleanup in the original .CBZ file required!')
                    log(Severity.ERROR, padding_tool_name, msg)
                    return False

            # Determine padded name (without ext)
            padded_file_name_without_ext = file_cls.name_without_ext.zfill(padding_num_dec)
            # Determine padding path
            padded_path = Path(file_cls.path.parent, f'{padded_file_name_without_ext}.{file_cls.ext}')
            # If padded path is same as original (ex. 10.jpg with 2 of padding remains 10.jpg), no need to rename
            if str(file_cls.path) == str(padded_path):
                continue
            # Rename file
            result = fileUtils.rename_file(file_cls.path, padded_path)
            if not result:
                msg = f'File {file_path} could not be renamed!'
                log(Severity.CRITICAL, padding_tool_name, msg)
                return False

        # If got here, succeeded
        return True

    def export_comicinfo_xml_with_updated_pages(self, cbz_img_cls_lst: List[CBZImageFile], export_path: Path):
        # Build ComicInfo.xml with updated pages list (If existing ComicInfo.xml found)
        comic_info_xml_path = Path(temp_dir_extracted_cbz, 'ComicInfo.xml')
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

    def compress_to_webp(self, always_keep_compressed: bool = False):
        func_name = 'compress_to_webp'

        # --------------------------------------------------------------------------------------------------------------
        # RESET
        self.compression_stats.reset()  # Statistics
        self.compression_log.reset()  # Logs
        fileUtils.make_dir(temp_compression_path)  # Make directory (if it doesn't exist)
        fileUtils.delete_dir_contents(temp_compression_path)  # Delete directory contents

        # --------------------------------------------------------------------------------------------------------------
        # START LOGS
        log(Severity.INFO, tool_name, f'Compressing "{self.file_name}"!')
        self.compression_log.append_msg_start(cbz_img_quality_grayscale, cbz_img_quality_color, always_keep_compressed)

        # --------------------------------------------------------------------------------------------------------------
        # STEP ONE : EXTRACTION OF .CBZ IN TEMP DIRECTORY
        fileUtils.create_n_wipe_dir(temp_dir_extracted_cbz)  # Create Directory (If Needed) & Wipe

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
        extracted_file_path_lst = fileUtils.get_file_path_list(temp_dir_extracted_cbz, recursive=True)
        for extracted_file_path in extracted_file_path_lst:
            file_path = Path(extracted_file_path)
            file_cls = fileUtils.File(file_path)
            if file_cls.ext in imageUtils.image_file_cls_supported_ext_lst:
                image_file_cls = CBZImageFile(file_path)
                self.compression_stats.original_images_size += image_file_cls.size  # Log Size in Stats
                img_file_cls_lst.append(image_file_cls)
            elif file_cls.file_name not in ['ComicInfo.xml', 'CompressionLog.txt']:
                msg = (f'Unexpected File within "{self.path}" NOT CAUGHT OR '
                       f'CLEANED DURING SANITIZE: "{file_cls.file_name}"')
                log(Severity.CRITICAL, f'cbzUtils.CBZFile.{func_name}', msg)
                return False

        # --------------------------------------------------------------------------------------------------------------
        # STEP FOUR: COMPRESS LIST OF IMAGES TO .WEBP
        fileUtils.create_n_wipe_dir(temp_dir_compressed_imgs)  # Create Directory (If Needed) & Wipe
        # Compress to WEBP
        for img_file_cls in img_file_cls_lst:

            # Get output path
            # Doing this to account for potential sub folders.
            img_original_dir_path_str = str(img_file_cls.path.parent)
            img_compress_dir_path_str = img_original_dir_path_str.replace(str(temp_dir_extracted_cbz), str(temp_dir_compressed_imgs))
            img_compress_file_path = Path(img_compress_dir_path_str, f'{img_file_cls.name_without_ext}.webp')

            result = img_file_cls.compress(dest_path=img_compress_file_path,
                                           quality_grayscale=cbz_img_quality_grayscale,
                                           quality_color=cbz_img_quality_color,
                                           max_long_edge=cbz_img_max_long_edge,
                                           max_height=cbz_img_max_height)
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
            if always_keep_compressed or img_file_cls.compressed_image.size < img_file_cls.size * cbz_img_min_allowed_compression_percentage / 100:
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
        fileUtils.create_n_wipe_dir(temp_dir_result)  # Create Directory (If Needed) & Wipe
        # Move kept images to result folder
        for kept_image_cls in kept_image_cls_lst:
            kept_img_compress_dir_path_str = str(kept_image_cls.path.parent)

            # Attempt to replace paths, will replace whichever it can (if kept compressed or original image)
            # Doing this to account for potential sub folders.
            kept_img_result_dir_path_str = kept_img_compress_dir_path_str.replace(str(temp_dir_compressed_imgs), str(temp_dir_result))
            kept_img_result_dir_path_str = kept_img_result_dir_path_str.replace(str(temp_dir_extracted_cbz), str(temp_dir_result))
            kept_img_result_file_path = Path(kept_img_result_dir_path_str, kept_image_cls.file_name)

            # Copy image in Result folder
            fileUtils.copy_file(kept_image_cls.path, kept_img_result_file_path)

        # --------------------------------------------------------------------------------------------------------------
        # STEP SEVEN: WRAP-UP OTHER FILES
        # Export ComicInfo.xml (With Updated Pages List!) to Result Directory
        self.export_comicinfo_xml_with_updated_pages(cbz_img_cls_lst=kept_image_cls_lst,
                                                     export_path=Path(temp_dir_result, 'ComicInfo.xml'))
        # Add summary to compression log
        self.compression_log.append_msg_end(self.compression_stats)
        # Dump Compression Log File on Disk
        self.compression_log.export(Path(temp_dir_result, 'CompressionLog.txt'))

        # --------------------------------------------------------------------------------------------------------------
        # STEP EIGHT: FROM CONTENTS OF THE RESULT DIRECTORY, BUILD ARCHIVE OVERWRITING THE ORIGINAL .CBZ
        zipUtils.zip_file(temp_dir_result, self.path, keep_root=False)

        # --------------------------------------------------------------------------------------------------------------
        # STEP NINE: CLEAN TEMP DIRECTORIES
        # Wipe directories
        fileUtils.delete_dir_contents(temp_compression_path)

        # --------------------------------------------------------------------------------------------------------------
        # END LOGS
        msg = (f'Completed Compression of "{self.file_name}" ({self.compression_stats.get_original_size_mb():.2f} MB '
               f'> {self.compression_stats.get_new_size_mb():.2f} MB)!')
        log(Severity.INFO, tool_name, msg)
        return True


def batch_compress_cbz(target_dir: Union[str, Path], recursive: bool = True, always_keep_compressed: bool = False):
    """
    Tool to compress .CBZ files, so they take less space. Only tested on macOS for now.

    1. Builds up a list of all .CBZ files in a given directory (recursively)
    2. For each .CBZ file which does not contain a CompressionLog.txt file:
        a.) Wipe ~/Temp_CBZ_Compression (recursively). Confirm it worked.
        b.) Extract .CBZ in ~/Temp_CBZ_Compression/Extracted_CBZ
        c.) Get list of extracted image files (.BMP, .JPG, .JPEG, .PNG, .WEBM) <- Throw error if sub-folders or unexpected file types
        d.) Compress as .JPG format (using desired compression setting) in ~/Temp_CBZ_Compression/Compressed_JPGs
        For each compressed .JPG file:
            a.) If at least 25% smaller than the original, copy compressed (else, original) to ~/Temp_CBZ_Compression/Result
        e.) If ComicInfo.XML file in ~Temp_CBZ_Compression/Input, recreate using resulting images in Output dir
        f.) Write a CompressionLog.txt file in Output, logging if originals or compressed version is kept
        g.) Compress contents of ~/Temp_CBZ_Compression/Output to .CBZ, overwriting the original file
    3. Write to console that conversion is complete, giving a brief summary outlining the following:
        -Compressed Number of .CBZ Files / Total Number of .CBZ Files (Newly Compressed vs Already Compressed)
        -Amount of Images Compressed that were kept vs using original instead (Number & Percentage)
        -Space Savings (Before -> After) (Number & Percentage)
    :param target_dir:
    :param recursive: When True, compress .CBZ within subdirectories
    :param always_keep_compressed: When True, always take the compressed image in lieu of the original file.
    """

    # Display basic information in console
    log_message = f'Initialize Batch Compress .CBZ in {target_dir} '
    if recursive:
        log_message += '(Recursive)'
    else:
        log_message += '(Not Recursive)'
    log(Severity.INFO, tool_name, log_message)

    # Stats
    compression_stats = CompressionStats()

    # Get list of .CBZ Files (as strings)
    cbz_file_path_lst: List[str] = fileUtils.get_file_path_list(target_dir, recursive, filter_extension='cbz')

    # Build list of CBZFile
    cbz_file_cls_lst: List[CBZFile] = []
    for cbz_file_path in cbz_file_path_lst:
        if Path(cbz_file_path).name.startswith('._'):
            log(Severity.WARNING, tool_name, f'Skipping file {cbz_file_path} because it is a macOS metadata file!')
            continue
        cbz_file_cls = CBZFile(Path(cbz_file_path))
        cbz_file_cls_lst.append(cbz_file_cls)

    # Filter for cbz files which need conversion
    cbz_file_cls_to_compress_lst: List[CBZFile] = []
    for cbz_file_cls in cbz_file_cls_lst:
        if cbz_file_cls.is_already_compressed():
            compression_stats.already_compressed_file_count += 1
            log(Severity.WARNING, tool_name, f'Skipping "{cbz_file_cls.file_name}"; Already Compressed!')
        else:
            cbz_file_cls_to_compress_lst.append(cbz_file_cls)

    # Log number of files not yet compressed
    log(Severity.INFO, tool_name, f'{len(cbz_file_cls_to_compress_lst)}/{len(cbz_file_cls_lst)} ({len(cbz_file_cls_to_compress_lst)/len(cbz_file_cls_lst)*100}%) of CBZ Files Awaiting Compression!')

    # Compress CBZ
    compression_stats.total_file_count = len(cbz_file_cls_lst)
    for cbz_file in cbz_file_cls_to_compress_lst:
        result = cbz_file.compress_to_webp(always_keep_compressed=always_keep_compressed)
        if result:
            compression_stats.compressed_file_count += 1
            compression_stats += cbz_file.compression_stats
        else:
            log(Severity.ERROR, tool_name, f'Skipped compression of "{cbz_file.path}" because it encountered an unrecoverable error! See log for details')
            compression_stats.error_during_compression += 1

    compression_stats.print_summary()
