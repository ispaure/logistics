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
from commonUtils import dirUtils, fileUtils
from commonUtils.osUtils import *
from commonUtils import zipUtils
import os
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

    def echo_epubs(self, destination: Path):
        """
        Echoes the EPUB contents of this Calibre library to a flattened destination.

        Source:
            Author / Book / Book.epub

        Destination:
            Author / Book.epub

        The destination is treated as a one-way mirror:
        - Missing EPUBs are copied.
        - EPUBs with a different file size are recopied.
        - Files no longer present in the source are deleted.
        - Empty directories are removed.
        - Author directories are only created when they contain EPUBs.
        """
        tool_name = 'Calibre EPUB Echo'

        source_resolved = self.path.resolve()
        destination_resolved = destination.resolve()

        if source_resolved == destination_resolved or source_resolved in destination_resolved.parents or destination_resolved in source_resolved.parents:
            log(Severity.CRITICAL, tool_name,
                f'Source and destination cannot overlap.\nSource: "{self.path}"\nDestination: "{destination}"')

        expected_files = {}
        detected_count = 0
        copied_count = 0
        recopied_count = 0
        deleted_count = 0

        # ------------------------------------------------------------------------------------------------------------------
        # BUILD EXPECTED EPUB LIST

        for author_directory in self.list_directories():
            for book_directory in author_directory.list_directories():
                epub_files = book_directory.list_files(recursive=False, filter_extension='epub')

                for epub_file in epub_files:
                    detected_count += 1
                    destination_file_path = destination / author_directory.name / epub_file.file_name

                    if destination_file_path in expected_files:
                        log(Severity.CRITICAL, tool_name,
                            f'EPUB filename collision detected at "{destination_file_path}"\nSource 1: "{expected_files[destination_file_path].path}"\nSource 2: "{epub_file.path}"')

                    expected_files[destination_file_path] = epub_file

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
        # COPY NEW OR CHANGED EPUBS

        for destination_file_path, source_file in expected_files.items():
            if not destination_file_path.is_file():
                if not fileUtils.copy_file(source_file.path, destination_file_path):
                    log(Severity.CRITICAL, tool_name,
                        f'Could not copy EPUB from "{source_file.path}" to "{destination_file_path}"')

                copied_count += 1
                continue

            destination_file = fileUtils.File(destination_file_path)

            if source_file.size != destination_file.size:
                if not fileUtils.copy_file(source_file.path, destination_file_path):
                    log(Severity.CRITICAL, tool_name,
                        f'Could not recopy EPUB from "{source_file.path}" to "{destination_file_path}"')

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

        log(Severity.INFO, tool_name,
            f'Detected {detected_count} EPUB(s) | Copied {copied_count} new | Recopied {recopied_count} changed | Deleted {deleted_count} obsolete')
