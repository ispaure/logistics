
import config as config
from pathlib import Path
import webbrowser
from commonUtils.debugUtils import *
from commonUtils.osUtils import *
from commonUtils import zipUtils
from commonUtils.wrappers import cmdShellWrapper


def run_repair_windows_script():
    cmd = 'start ' + str(Path(config.LogisticsConfig().path_logistics_scripts, 'windows_system_files_repair.bat'))
    cmdShellWrapper.exec_cmd(cmd, wait_for_output=False)


def run_repair_ntfs_on_d():
    cmd = 'start ' + str(Path(config.LogisticsConfig().path_logistics_scripts, 'repair_ntfs_on_D.bat'))
    cmdShellWrapper.exec_cmd(cmd, wait_for_output=False)


def open_calibre(calibre_library_path):
    match get_os():
        case OS.WIN:
            software_exec_path = str(Path(config.LogisticsConfig().path_logistics_software_win, 'Calibre2', 'calibre.exe'))
            launch_cmd = '"{}" --with-library "{}"'.format(software_exec_path, calibre_library_path)
            cmdShellWrapper.exec_cmd(launch_cmd, wait_for_output=False)
        case OS.MAC:
            # Calibre location on macOS
            software_exec_path = str(Path('/Applications', 'calibre.app', 'Contents', 'MacOS', 'calibre'))

            # If macOS, calibre.app might not be installed yet (it doesn't come extracted in Logistics as it creates rclone
            # bug. So check if it is installed. If not extract to folder.
            if not os.path.exists(software_exec_path):
                zipUtils.unzip_file(str(Path(config.LogisticsConfig().path_logistics_software_mac, 'calibre.app.zip')), str(Path('/Applications')))

            # Once it is known that calibre has been installed (or is there on macOS, can execute it.)
            launch_cmd = f'"{software_exec_path}" --with-library "{calibre_library_path}"'
            print(launch_cmd)
            cmdShellWrapper.exec_cmd(launch_cmd, wait_for_output=False)
            print('done')
        case OS.LINUX:
            # If Linux, calibre might not be installed yet
            if not os.path.isdir('/var/lib/flatpak/app/com.calibre_ebook.calibre'):
                log(Severity.CRITICAL, 'Open Calibre', 'Cannot Open Calibre because it is not installed on the system. install using Bazaar on Bazzite', popup=True)
            else:
                cmdShellWrapper.exec_cmd(f'flatpak run com.calibre_ebook.calibre --with-library "{calibre_library_path}"')


def open_url(entry_str):
    """
    Opens URL from those stored in ConfigFile.ini
    """
    print('attempting to open url')
    cfg_file_pth = config.get_config_file_path()
    url = config.config_section_map('URLs', entry_str, cfg_file_pth)

    if '<' and '>' in url:
        # Get computers internal ip addresses and resolve in URL if applicable
        computer_ips = {'goat-pc': config.config_section_map('ResolveIP', 'goat-pc', cfg_file_pth),
                        'yagi-mac': config.config_section_map('ResolveIP', 'yagi-mac', cfg_file_pth),
                        'reserved-server': config.config_section_map('ResolveIP', 'reserved-server', cfg_file_pth)}

        # Resolve IP if necessary
        for key, value in computer_ips.items():
            url = url.replace('<{}>'.format(key), value)

    # Open URL
    webbrowser.open(url)


def disable_macos_lid_sleep():
    launch_cmd = 'sudo pmset -b sleep 0; sudo pmset -b disablesleep 1'
    cmdShellWrapper.exec_cmd(launch_cmd, wait_for_output=True)
    print('Disabled macOS Lid Sleep!')


def enable_macos_lid_sleep():
    launch_cmd = 'sudo pmset -b sleep 5; sudo pmset -b disablesleep 0'
    cmdShellWrapper.exec_cmd(launch_cmd, wait_for_output=True)
    print('Enabled macOS Lid Sleep!')