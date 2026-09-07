"""
Hosts functions related to Calibre Book-Reading Software
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


from pathlib import Path
from typing import List, Union
from commonUtils import dirUtils, fileUtils
from commonUtils.osUtils import *
from commonUtils import zipUtils
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
import config
from commonUtils.wrappers import cmdShellWrapper
from commonUtils.debugUtils import *


class CalibreLibrary(dirUtils.Directory):
    def __init__(self, path: Path):
        super().__init__(path)

    def open_in_calibre(self):
        match get_os():
            case OS.WIN:
                software_exec_path: Path = Path(config.LogisticsConfig().path_logistics_software_win, 'Calibre2', 'calibre.exe')
                launch_cmd = '"{}" --with-library "{}"'.format(software_exec_path, self.path)
                cmdShellWrapper.exec_cmd(launch_cmd, wait_for_output=False)

            case OS.MAC:
                # Calibre location on macOS
                software_exec_path: Path = Path('/Applications', 'calibre.app', 'Contents', 'MacOS', 'calibre')

                # If macOS, calibre.app might not be installed yet (it doesn't come extracted in Logistics as it creates rclone
                # bug. So check if it is installed. If not extract to folder.
                if not os.path.exists(software_exec_path):
                    zipUtils.unzip_file(Path(config.LogisticsConfig().path_logistics_software_mac, 'calibre.app.zip'), Path('/Applications'))

                # Once it is known that calibre has been installed (or is there on macOS, can execute it.)
                launch_cmd = f'"{software_exec_path}" --with-library "{self.path}"'
                print(launch_cmd)
                cmdShellWrapper.exec_cmd(launch_cmd, wait_for_output=False)
                print('done')

            case OS.LINUX:
                # If Linux, calibre might not be installed yet
                if not os.path.isdir('/var/lib/flatpak/app/com.calibre_ebook.calibre'):
                    log(Severity.CRITICAL, 'Open Calibre', 'Cannot Open Calibre because it is not installed on the system. install using Bazaar on Bazzite', popup=True)
                else:
                    cmdShellWrapper.exec_cmd(f'flatpak run com.calibre_ebook.calibre --with-library "{self.path}"')

    def __get_clean_book_name(self, book_directory: dirUtils.Directory) -> str:
        """
        Returns the Calibre book folder name without its trailing internal Calibre ID.

        Example:
            "Book Title (1234)"
        becomes:
            "Book Title"
        """
        return re.sub(r'\s+\(\d+\)$', '', book_directory.name)

    def __normalize_series_index(self, series_index: str) -> str:
        """
        Simplifies Calibre series indexes such as 21.00 to 21 while preserving
        meaningful decimal values such as 21.5.
        """
        if '.' in series_index:
            series_index = series_index.rstrip('0').rstrip('.')

        return series_index

    def __normalize_path(self, path: Path) -> str:
        """
        Returns an NFC-normalized path string for reliable Unicode comparisons.

        Filesystems can represent accented characters using different Unicode
        compositions while displaying the same filename.
        """
        return unicodedata.normalize('NFC', str(path))

    def __sanitize_file_name(self, file_name: str) -> str:
        """
        Removes or replaces characters that are unsafe or undesirable in filenames.

        All dash variants and substituted characters use the standard ASCII dash (-).
        Unicode characters are normalized to NFC for consistent filesystem names.
        """
        file_name = unicodedata.normalize('NFC', file_name)
        file_name = re.sub(r'[‐-‒–—―]', '-', file_name)
        file_name = re.sub(r'[\\/:*?"<>|]+', ' - ', file_name)
        file_name = re.sub(r'\s*-\s*-\s*', ' - ', file_name)
        file_name = re.sub(r'\s*-\s*', ' - ', file_name)
        file_name = re.sub(r'\s+', ' ', file_name)
        file_name = file_name.strip(' .-')

        return file_name

    def __title_contains_series(self, title: str, series: str) -> bool:
        """
        Returns True when the title already starts with the series name.

        Punctuation between the series name and the rest of the title is allowed.
        """
        normalized_title = re.sub(r'\s+', ' ', title).strip().casefold()
        normalized_series = re.sub(r'\s+', ' ', series).strip().casefold()

        if normalized_title == normalized_series:
            return True

        if not normalized_title.startswith(normalized_series):
            return False

        remainder = normalized_title[len(normalized_series):]

        return not remainder or bool(re.match(r'^[\s,:;\-‐-‒–—―()\[\]]', remainder))

    def __title_contains_series_index(self, title: str, series_index: str) -> bool:
        """
        Returns True when the title already appears to contain the series index.

        Examples:
            "Book Volume 6" with index 6
            "Book Vol. 6" with index 6
            "Book Vol 6" with index 6
        """
        escaped_index = re.escape(series_index)

        patterns = [
            rf'\bvolume\s*0*{escaped_index}\b',
            rf'\bvol\.?\s*0*{escaped_index}\b',
        ]

        for pattern in patterns:
            if re.search(pattern, title, re.IGNORECASE):
                return True

        return False

    def __get_metadata_book_name(self, book_directory: dirUtils.Directory) -> Union[str, None]:
        """
        Builds a human-readable book name from Calibre's metadata.opf.

        Examples:
            Title
            Series - Title
            Series - Title - Vol 5
            Title Volume 5

        Duplicate information is avoided where possible:
        - The series is not prepended if the title already starts with it.
        - Punctuation after the series name is tolerated.
        - The series index is not appended if the title already contains the same volume.
        """
        metadata_path = book_directory.path / 'metadata.opf'

        if not metadata_path.is_file():
            return None

        try:
            root = ET.parse(metadata_path).getroot()
        except (ET.ParseError, OSError):
            return None

        title = None
        series = None
        series_index = None

        for element in root.iter():
            element_name = element.tag.split('}')[-1]

            if element_name == 'title' and element.text and title is None:
                title = element.text.strip()

            if element_name == 'meta':
                metadata_name = element.attrib.get('name')
                metadata_content = element.attrib.get('content')

                if metadata_name == 'calibre:series' and metadata_content:
                    series = metadata_content.strip()
                elif metadata_name == 'calibre:series_index' and metadata_content:
                    series_index = self.__normalize_series_index(metadata_content.strip())

        if not title and not series:
            return None

        if title:
            book_name = title

            if series and not self.__title_contains_series(title, series):
                book_name = f'{series} - {title}'
        else:
            book_name = series

        if series and series_index and not self.__title_contains_series_index(book_name, series_index):
            book_name = f'{book_name} - Vol {series_index}'

        return self.__sanitize_file_name(book_name)

    def __get_export_book_name(self, book_directory: dirUtils.Directory) -> str:
        """
        Returns the preferred exported book name.

        Calibre metadata is preferred. The cleaned Calibre folder name is used
        as a fallback when metadata.opf cannot provide a usable name.
        """
        metadata_book_name = self.__get_metadata_book_name(book_directory)

        if metadata_book_name:
            return metadata_book_name

        return self.__sanitize_file_name(self.__get_clean_book_name(book_directory))

    def echo_book_formats(self, destination: Path, extensions: List[str]):
        """
        Echoes supported book formats from this Calibre library to a flattened destination.

        Source:
            Author / Book Name (Calibre ID) / Book.epub
                                            Book.pdf

        Destination:
            Author / Metadata-based Book Name.epub
                     Metadata-based Book Name.pdf

        The destination filename is primarily built from metadata.opf.

        Examples:
            Title.epub
            Series - Title.epub
            Series - Title - Vol 5.epub

        Duplicate information is avoided where possible. If the title already starts
        with the series name, including when punctuation immediately follows it, the
        series is not repeated. If the title already contains its volume number, an
        additional "Vol X" suffix is not added.

        Unsafe filename characters are replaced using the standard ASCII dash (-).
        Unicode dash variants are also converted to the standard ASCII dash.

        Unicode paths are normalized to NFC when comparing expected files with files
        already present at the destination. This prevents visually identical accented
        filenames with different Unicode compositions from being treated as different files.

        If metadata cannot provide a usable name, the Calibre book folder name is used
        after removing its trailing internal Calibre ID.

        If multiple Calibre books would produce the same destination filename, a warning
        is logged and the first file encountered is kept.

        The destination is treated as a one-way mirror:
        - All files matching one of the requested extensions are copied.
        - Files with a different file size are recopied.
        - Files no longer present in the source are deleted.
        - Empty directories are removed.
        - Author directories are only created when they contain supported book files.
        - A warning is logged when a Calibre book contains none of the requested formats.
        """
        tool_name = 'Calibre Book Format Echo'

        source_resolved = self.path.resolve()
        destination_resolved = destination.resolve()

        if source_resolved == destination_resolved or source_resolved in destination_resolved.parents or destination_resolved in source_resolved.parents:
            log(Severity.CRITICAL, tool_name, f'Source and destination cannot overlap.\nSource: "{self.path}"\nDestination: "{destination}"')

        extensions = [extension.lower().lstrip('.') for extension in extensions]

        expected_files = {}
        detected_count = 0
        missing_format_count = 0
        collision_count = 0
        metadata_fallback_count = 0
        copied_count = 0
        recopied_count = 0
        deleted_count = 0

        # ------------------------------------------------------------------------------------------------------------------
        # BUILD EXPECTED BOOK FILE LIST

        for author_directory in self.list_directories():
            for book_directory in author_directory.list_directories():
                book_files = book_directory.list_files(recursive=False, filter_extension=extensions)

                if not book_files:
                    missing_format_count += 1
                    log(Severity.WARNING, tool_name, f'No supported format found for "{author_directory.name} / {book_directory.name}"')
                    continue

                metadata_book_name = self.__get_metadata_book_name(book_directory)

                if metadata_book_name:
                    export_book_name = metadata_book_name
                else:
                    metadata_fallback_count += 1
                    export_book_name = self.__sanitize_file_name(self.__get_clean_book_name(book_directory))
                    log(Severity.WARNING, tool_name, f'Could not retrieve usable metadata name for "{author_directory.name} / {book_directory.name}". Using Calibre folder name instead.')

                for book_file in book_files:
                    detected_count += 1
                    destination_file_path = destination / author_directory.name / f'{export_book_name}.{book_file.ext}'
                    destination_file_key = self.__normalize_path(destination_file_path)

                    if destination_file_key in expected_files:
                        collision_count += 1
                        log(Severity.WARNING, tool_name, f'Book filename collision detected. Keeping first file.\nDestination: "{destination_file_path}"\nKeeping: "{expected_files[destination_file_key][1].path}"\nSkipping: "{book_file.path}"')
                        continue

                    expected_files[destination_file_key] = (destination_file_path, book_file)

        # ------------------------------------------------------------------------------------------------------------------
        # REMOVE FILES THAT SHOULD NO LONGER EXIST

        if destination.is_dir():
            destination_directory = dirUtils.Directory(destination)

            for destination_file in destination_directory.list_files(recursive=True):
                destination_file_key = self.__normalize_path(destination_file.path)

                if destination_file_key not in expected_files:
                    log(Severity.DEBUG, tool_name, f'Deleting obsolete file "{destination_file.path}"')

                    if not destination_file.delete_file():
                        log(Severity.CRITICAL, tool_name, f'Could not delete obsolete file "{destination_file.path}"')

                    deleted_count += 1

        # ------------------------------------------------------------------------------------------------------------------
        # COPY NEW OR CHANGED BOOK FILES

        for destination_file_path, source_file in expected_files.values():
            if not destination_file_path.is_file():
                if not fileUtils.copy_file(source_file.path, destination_file_path):
                    log(Severity.CRITICAL, tool_name, f'Could not copy book file from "{source_file.path}" to "{destination_file_path}"')

                copied_count += 1
                continue

            destination_file = fileUtils.File(destination_file_path)

            if source_file.size != destination_file.size:
                if not fileUtils.copy_file(source_file.path, destination_file_path):
                    log(Severity.CRITICAL, tool_name, f'Could not recopy book file from "{source_file.path}" to "{destination_file_path}"')

                recopied_count += 1

        # ------------------------------------------------------------------------------------------------------------------
        # REMOVE EMPTY DIRECTORIES

        if destination.is_dir():
            for root, dirs, files in os.walk(destination, topdown=False):
                for directory_name in dirs:
                    directory_path = Path(root, directory_name)

                    if fileUtils.is_dir_empty(directory_path):
                        dirUtils.Directory(directory_path).delete()

        # ------------------------------------------------------------------------------------------------------------------
        # SUMMARY

        log(Severity.INFO, tool_name, f'Detected {detected_count} supported file(s) | Missing format for {missing_format_count} book(s) | Metadata fallbacks {metadata_fallback_count} | Collisions {collision_count} | Copied {copied_count} new | Recopied {recopied_count} changed | Deleted {deleted_count} obsolete')
