"""Established CBZ cleanup and numeric page-padding rules."""

from pathlib import Path
from typing import List
from commonUtils.filesystem import files as fileUtils, directories as dirUtils
from commonUtils.runtime.diagnostics import Severity, log
from features.images import processing as imageUtils

tool_name = "features.comics.cbz"


class CBZSanitizationMixin:
    def sanitize_extracted_cbz(self, extracted_dir) -> bool:
        """Apply established cleanup phases in order, stopping at the first failure.

        Earlier cleanup remains applied if a later phase fails. This is not a
        transaction: changing that order would change accepted layouts and moves.
        """
        sanitize_tool_name = "cbzUtils.CBZFile.sanitize_extracted_cbz"
        expected_names = ["ComicInfo.xml", "CompressionLog.txt"]
        discard_names = [".DS_Store", "Thumbs.db", "Thumbs1.db"]
        extracted_directory = dirUtils.Directory(extracted_dir)
        if not self._remove_macos_folders(extracted_directory, sanitize_tool_name):
            return False
        if not self._clean_extracted_files(
            extracted_directory, sanitize_tool_name, expected_names, discard_names
        ):
            return False
        if not self._normalize_extracted_layout(
            extracted_directory, sanitize_tool_name, expected_names
        ):
            return False
        return self._repair_extracted_padding(extracted_directory, sanitize_tool_name)

    def _remove_macos_folders(self, extracted_directory, sanitize_tool_name) -> bool:
        directories: List[dirUtils.Directory] = extracted_directory.list_directories()
        for directory in directories:
            if directory.name == "__MACOSX":
                result = directory.delete()
                if result:
                    msg = 'Found rogue folder "__MACOSX" in archive, deleted!'
                    log(Severity.WARNING, sanitize_tool_name, msg)
                # Abort (critical) if it could not delete directory
                else:
                    msg = f"Could not delete __MACOSX directory in {self.path}!"
                    log(Severity.ERROR, sanitize_tool_name, msg)
                    return False
        return True

    def _clean_extracted_files(
        self, extracted_directory, sanitize_tool_name, expected_names, discard_names
    ) -> bool:
        extracted_files: List[fileUtils.File] = extracted_directory.list_files(
            recursive=True
        )
        for extracted_file in extracted_files:
            # If File identified to DELETE
            if extracted_file.file_name in discard_names:
                msg = f'Deleting file from to-delete list: "{extracted_file.file_name}"'
                log(Severity.WARNING, sanitize_tool_name, msg)
                result = extracted_file.delete_file()
                if not result:
                    log(
                        Severity.ERROR,
                        sanitize_tool_name,
                        f'Could not delete file "{extracted_file.file_name}"',
                    )
                    return False
                continue
            # If File expected in archive, continue
            elif extracted_file.file_name in expected_names:
                continue
            # If File is of these file types, not expected in archive unless previous "continue"
            elif extracted_file.ext in [
                "txt",
                "url",
                "nfo",
                "html",
                "sfv",
                "rtf",
                "ini",
                "dat",
                "css",
            ]:
                msg = f'Deleting unexpected file of extension .{extracted_file.ext}: "{extracted_file.file_name}"'
                log(Severity.WARNING, sanitize_tool_name, msg)
                result = extracted_file.delete_file()
                if not result:
                    log(
                        Severity.ERROR,
                        sanitize_tool_name,
                        f'Could not delete file "{extracted_file.file_name}"',
                    )
                    return False
                continue
            elif extracted_file.ext not in imageUtils.image_file_cls_supported_ext_lst:
                msg = (
                    f'Found unexpected file in archive!: "{extracted_file.file_name}" Manual cleanup in the original'
                    f".CBZ file required!"
                )
                log(Severity.ERROR, sanitize_tool_name, msg)
                return False
        return True

    def _repair_extracted_padding(
        self, extracted_directory, sanitize_tool_name
    ) -> bool:
        extracted_files = extracted_directory.list_files(recursive=True)
        need_padding_repair = False
        for extracted_file in extracted_files:
            if (
                len(extracted_file.file_name) < 2
            ):  # If file name is incredibly short, throw error
                msg = (
                    f'File "{extracted_file.file_name}" has unbelievably tiny name. Manual cleanup in '
                    f"the original .CBZ file required!"
                )
                log(Severity.ERROR, sanitize_tool_name, msg)
                return False
            elif (
                extracted_file.file_name[1] == "."
                and extracted_file.file_name[0] in "0123456789"
            ):
                msg = (
                    f'Page "{extracted_file.file_name}" within archive are named without padding (ex. 1.jpg), which can lead to improper '
                    f"sorting in applications such as ComicRack. Renaming with padding..."
                )
                log(Severity.WARNING, sanitize_tool_name, msg)
                need_padding_repair = True
                break  # Identified that we need padding repair, no need to process further in verifications.

        # Padding repair
        if need_padding_repair:  # When flagged previously as needed.
            result = self.repair_padding(files=extracted_files)
            if not result:
                msg = f"Error whilst applying padding! Manual cleanup in the original .CBZ file required!"
                log(Severity.ERROR, sanitize_tool_name, msg)
                return False
        return True

    def _flatten_nested_wrapper(self, directories, sanitize_tool_name) -> bool:
        if len(directories) == 1:
            directory = directories[0]
            subdirectories: List[dirUtils.Directory] = directory.list_directories()
            directory_files: List[fileUtils.File] = directory.list_files(
                recursive=False
            )
            if len(subdirectories) == 1 and len(directory_files) == 0:
                subdirectory = subdirectories[0]
                if not fileUtils.has_subdirectories(subdirectory.path):
                    subdirectory_files: List[fileUtils.File] = subdirectory.list_files(
                        recursive=False
                    )
                    if len(subdirectory_files) > 0:
                        msg = (
                            "Found only a single directory, which itself contains no files and exactly one "
                            "subdirectory, which itself contains files but not any more directories. "
                            "Moving files from the subdirectory to the directory."
                        )
                        log(Severity.WARNING, tool_name, msg)
                        for subdir_file in subdirectory_files:
                            destination_file_path = (
                                directory.path / subdir_file.file_name
                            )
                            if destination_file_path.exists():
                                log(
                                    Severity.ERROR,
                                    sanitize_tool_name,
                                    f"Flattening would overwrite {destination_file_path}",
                                )
                                return False
                            try:
                                subdir_file.move_file(destination_file_path)
                            except OSError:
                                msg = (
                                    f'File move unsuccessful (source: "{subdir_file.path}", '
                                    f'destination: "{destination_file_path}")!'
                                )
                                log(Severity.ERROR, sanitize_tool_name, msg)
                                return False
                        result = subdirectory.delete()
                        if not result:
                            msg = f'Directory deletion was unsuccessful: "{subdirectory.path}"!'
                            log(Severity.ERROR, sanitize_tool_name, msg)
                            return False
        return True

    def _flatten_single_wrapper(
        self, directories, extracted_directory, sanitize_tool_name
    ) -> bool:
        if len(directories) == 1:
            directory = directories[0]
            subdirectory_files: List[fileUtils.File] = directory.list_files(
                recursive=False
            )
            for subdir_file in subdirectory_files:
                destination_path = Path(extracted_directory.path, subdir_file.file_name)
                if destination_path.exists():
                    log(
                        Severity.ERROR,
                        sanitize_tool_name,
                        f"Flattening would overwrite {destination_path}",
                    )
                    return False
                try:
                    subdir_file.move_file(destination_path)
                except OSError:
                    msg = (
                        f'File move unsuccessful (source: "{subdir_file.path}", '
                        f'destination: "{destination_path}")!'
                    )
                    log(Severity.ERROR, sanitize_tool_name, msg)
                    return False
            # Delete empty dir after everything has been moved to the root
            if (
                not fileUtils.has_subdirectories(directory.path)
                and len(directory.list_files(recursive=True)) == 0
            ):
                result = directory.delete()
                if not result:
                    msg = f'Could not delete "{directory.path}"!'
                    log(Severity.ERROR, tool_name, msg)
                    return False
            else:
                msg = f'Could not delete "{directory.path}" because it is not empty!'
                log(Severity.ERROR, tool_name, msg)
                return False
        return True

    def _normalize_extracted_layout(
        self, extracted_directory, sanitize_tool_name, expected_names
    ) -> bool:
        if fileUtils.has_subdirectories(extracted_directory.path):
            directories = extracted_directory.list_directories()

            # Abort if root has subdir + any unsuspected file (including any image)
            root_files: List[fileUtils.File] = extracted_directory.list_files(
                recursive=False
            )
            for root_file in root_files:
                if root_file.file_name not in expected_names:
                    msg = (
                        "There is at least one subdirectory and at least one unsuspected file at the root: "
                        f'"{root_file.file_name}", which is not supported. Manual cleanup in the original '
                        f".CBZ file required!"
                    )
                    log(Severity.ERROR, sanitize_tool_name, msg)
                    return False

            # ----------------------------------------------------------------------------------------------------------
            # Weird Edge case I had to account for (else it's repetitive manual work)
            # If there is exactly one directory, which itself contains no files and exactly one subdirectory
            # And that subdirectory does not contain itself anymore subdirectories, move the files to the directory.
            if not self._flatten_nested_wrapper(directories, sanitize_tool_name):
                return False

            # Refresh directory_lst because it may have changed
            directories = extracted_directory.list_directories()
            # ----------------------------------------------------------------------------------------------------------

            # Abort if any directory itself has a subdirectory
            for directory in directories:
                if fileUtils.has_subdirectories(directory.path):
                    msg = (
                        f'The subdirectory "{directory.name}" has at least one subdirectory itself, which is '
                        f"not supported. Manual cleanup in the original .CBZ file required!"
                    )
                    log(Severity.ERROR, sanitize_tool_name, msg)
                    return False

            # If there was just one directory, move the files in it to the root
            if not self._flatten_single_wrapper(
                directories, extracted_directory, sanitize_tool_name
            ):
                return False
        return True

    def repair_padding(self, files: List[fileUtils.File]) -> bool:
        """
        Repair padding on a list of files
        """
        padding_tool_name = "Repair .CBZ File Padding"

        # Get padding length
        if len(files) < 90:  # Could put 99, but being safer than sorry
            padding_width: int = 2
        elif len(files) < 950:  # Could put 999, but being safer than sorry
            padding_width: int = 3
        else:
            padding_width: int = 5

        # Validate the complete rename plan before changing any extracted page.
        planned_paths = set()
        for file in files:
            if file.ext not in imageUtils.image_file_cls_supported_ext_lst:
                continue
            if (
                file.file_name.count(".") != 1
                or not file.name_without_ext
                or any(char not in "0123456789" for char in file.name_without_ext)
            ):
                log(
                    Severity.ERROR,
                    padding_tool_name,
                    f"Cannot pad page name: {file.file_name}",
                )
                return False
            destination = file.path.with_name(
                f"{file.name_without_ext.zfill(padding_width)}.{file.ext}"
            )
            key = str(destination).casefold()
            if key in planned_paths or (
                destination != file.path and destination.exists()
            ):
                log(
                    Severity.ERROR,
                    padding_tool_name,
                    f"Padding would overwrite a page: {destination}",
                )
                return False
            planned_paths.add(key)

        for file in files:
            # Skip padding on non-image files
            if file.ext not in imageUtils.image_file_cls_supported_ext_lst:
                continue

            # Determine padded name (without ext)
            padded_file_name_without_ext = file.name_without_ext.zfill(padding_width)
            # Determine padding path
            padded_path = Path(
                file.path.parent, f"{padded_file_name_without_ext}.{file.ext}"
            )
            # If padded path is same as original (ex. 10.jpg with 2 of padding remains 10.jpg), no need to rename
            if file.path == padded_path:
                continue
            # Rename file
            try:
                file.rename_file(padded_path)
            except OSError:
                msg = f"File {file.path} could not be renamed!"
                log(Severity.ERROR, padding_tool_name, msg)
                return False

        # If got here, succeeded
        return True
