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
from commonUtils import dirUtils
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
