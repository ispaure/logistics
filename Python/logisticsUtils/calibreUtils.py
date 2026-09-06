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

    def __get_series_index(self, book_directory: dirUtils.Directory) -> Union[str, None]:
        """
        Retrieves the Calibre series index from metadata.opf for a book.
        Returns None if metadata.opf or calibre:series_index cannot be found.
        """
        metadata_path = book_directory.path / 'metadata.opf'

        if not metadata_path.is_file():
            return None

        metadata_file = fileUtils.TXTFile(metadata_path)

        for line in metadata_file.read_lines():
            if 'name="calibre:series_index"' not in line:
                continue

            match_result = re.search(r'content="([^"]+)"', line)

            if match_result:
                series_index = match_result.group(1)

                # Keep decimal series numbers intact, but simplify values such as 21.00 to 21.
                if '.' in series_index:
                    series_index = series_index.rstrip('0').rstrip('.')

                return series_index

        return None

    def echo_book_formats(self, destination: Path, extensions: List[str]):
        """
        Echoes supported book formats from this Calibre library to a flattened destination.

        Source:
            Author / Book / Book.epub
                            Book.pdf

        Destination:
            Author / Book.epub
                     Book.pdf

        When multiple Calibre books would produce the same destination filename, their
        Calibre series indexes are appended to distinguish them:
            Book [21].epub
            Book [65].epub

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

        candidate_files = {}
        expected_files = {}
        detected_count = 0
        missing_format_count = 0
        collision_count = 0
        copied_count = 0
        recopied_count = 0
        deleted_count = 0

        # ------------------------------------------------------------------------------------------------------------------
        # BUILD CANDIDATE BOOK FILE LIST

        for author_directory in self.list_directories():
            for book_directory in author_directory.list_directories():
                book_files = book_directory.list_files(recursive=False, filter_extension=extensions)

                if not book_files:
                    missing_format_count += 1
                    log(Severity.WARNING, tool_name, f'No supported format found for "{author_directory.name} / {book_directory.name}"')
                    continue

                for book_file in book_files:
                    detected_count += 1
                    destination_file_path = destination / author_directory.name / book_file.file_name

                    if destination_file_path not in candidate_files:
                        candidate_files[destination_file_path] = []

                    candidate_files[destination_file_path].append((book_file, book_directory))

        # ------------------------------------------------------------------------------------------------------------------
        # RESOLVE FILENAME COLLISIONS

        for destination_file_path, candidates in candidate_files.items():
            if len(candidates) == 1:
                expected_files[destination_file_path] = candidates[0][0]
                continue

            collision_count += 1
            log(Severity.WARNING, tool_name, f'Book filename collision detected for "{destination_file_path.name}". Using Calibre series indexes to distinguish files.')

            for book_file, book_directory in candidates:
                series_index = self.__get_series_index(book_directory)

                if series_index is None:
                    log(Severity.CRITICAL, tool_name, f'Could not resolve filename collision because no Calibre series index was found.\nBook: "{book_directory.path}"\nFile: "{book_file.path}"')

                collision_file_name = f'{book_file.name_without_ext} [{series_index}].{book_file.ext}'
                collision_destination_path = destination_file_path.parent / collision_file_name

                if collision_destination_path in expected_files:
                    log(Severity.CRITICAL, tool_name, f'Book filename collision still exists after adding Calibre series index.\nDestination: "{collision_destination_path}"\nSource 1: "{expected_files[collision_destination_path].path}"\nSource 2: "{book_file.path}"')

                expected_files[collision_destination_path] = book_file

        # ------------------------------------------------------------------------------------------------------------------
        # REMOVE FILES THAT SHOULD NO LONGER EXIST

        if destination.is_dir():
            destination_directory = dirUtils.Directory(destination)

            for destination_file in destination_directory.list_files(recursive=True):
                if destination_file.path not in expected_files:
                    log(Severity.DEBUG, tool_name, f'Deleting obsolete file "{destination_file.path}"')

                    if not destination_file.delete_file():
                        log(Severity.CRITICAL, tool_name, f'Could not delete obsolete file "{destination_file.path}"')

                    deleted_count += 1

        # ------------------------------------------------------------------------------------------------------------------
        # COPY NEW OR CHANGED BOOK FILES

        for destination_file_path, source_file in expected_files.items():
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

        log(Severity.INFO, tool_name, f'Detected {detected_count} supported file(s) | Missing format for {missing_format_count} book(s) | Resolved {collision_count} collision(s) | Copied {copied_count} new | Recopied {recopied_count} changed | Deleted {deleted_count} obsolete')
