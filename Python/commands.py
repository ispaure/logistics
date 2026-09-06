
import config as config
from pathlib import Path
import webbrowser
from commonUtils.wrappers import cmdShellWrapper


def run_repair_windows_script():
    cmd = 'start ' + str(Path(config.LogisticsConfig().path_logistics_scripts, 'windows_system_files_repair.bat'))
    cmdShellWrapper.exec_cmd(cmd, wait_for_output=False)


def run_repair_ntfs_on_d():
    cmd = 'start ' + str(Path(config.LogisticsConfig().path_logistics_scripts, 'repair_ntfs_on_D.bat'))
    cmdShellWrapper.exec_cmd(cmd, wait_for_output=False)


def open_config_file_url(entry_str):
    """
    Opens URL from those stored in ConfigFile.ini
    """
    print('attempting to open url')
    cfg_file_pth = config.get_config_file_path()
    url = config.config_section_map('URLs', entry_str, cfg_file_pth)

    if '<' in url and '>' in url:
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