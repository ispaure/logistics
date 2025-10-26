import configparser
from pathlib import Path
import sys
import os
from commonUtils.osUtils import *
from commonUtils.debugUtils import *
import commonUtils.marcUtils as marcUtils


def get_dir_split_character():
    match get_os():
        case OS.WIN:
            return '\\'
        case _:
            return '/'


def get_config_file_path():
    current_dir = Path(__file__).resolve().parent
    config_ini_path = current_dir / "configFile.ini"
    return str(config_ini_path)


def get_win32_user_doc_dir():
    CSIDL_PERSONAL = 5  # My Documents
    SHGFP_TYPE_CURRENT = 0  # Get current, not default value
    buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_PERSONAL, None, SHGFP_TYPE_CURRENT, buf)
    user_documents_dir = buf.value
    return user_documents_dir


def get_win32_user_home_dir():
    return os.path.expanduser("~")


class LogisticsConfig:
    """
    Stores the Logistics Config Information
    """

    def __init__(self):

        # Get config file path
        config_file_path = get_config_file_path()

        # Get Server Path
        match get_os():
            case OS.WIN:
                user_home_dir = get_win32_user_home_dir()
                sub_server_path = config_section_map('DirectoryStructure', 'server_path_win32', config_file_path)
                self.server_path = str(Path(user_home_dir, sub_server_path))
            case OS.MAC:
                user_home_dir = os.environ['HOME']
                sub_server_path_macos = config_section_map('DirectoryStructure', 'server_path_macos', config_file_path)
                self.server_path = str(Path(user_home_dir, sub_server_path_macos))
            case _:
                log(Severity.CRITICAL, 'config.py', 'OS not in list!')
                sys.exit()

        # Get Logistics directory
        current_file = Path(__file__).resolve()
        self.path_logistics = str(current_file.parent.parent)
        # Get Scripts directory
        self.path_logistics_scripts = str(Path(self.path_logistics, 'Scripts'))

        # Get Logistics software directory
        marc_dropbox_path = marcUtils.get_marc_dropbox_root()
        if os.path.isdir(marc_dropbox_path):
            self.path_logistics_software = str(Path(marc_dropbox_path, 'Software', 'Logistics', 'Software'))
            self.path_logistics_remote_cred = str(Path(marc_dropbox_path, 'Software', 'Logistics', 'RemoteCredentials'))
        else:
            self.path_logistics_software = str(Path(self.server_path, 'Logistics', 'Software'))
            self.path_logistics_remote_cred = str(Path(self.server_path, 'Logistics', 'RemoteCredentials'))

        # Other paths
        self.temp_path = str(Path(self.path_logistics, 'temp'))
        self.path_remote_network_mount = str(Path(self.server_path, config_section_map('DirectoryStructure', 'remote_network_mount_sub_path', config_file_path)))
        self.path_remote_local = str(Path(self.server_path, config_section_map('DirectoryStructure', 'remote_local_sub_path', config_file_path)))
        match get_os():
            case OS.WIN:
                self.pms_data_path = str(Path(os.environ['LOCALAPPDATA'], 'Plex Media Server'))
                self.yac_lib_prefs_dir = None
            case OS.MAC:
                self.pms_data_path = str(Path(user_home_dir, 'Library', 'Application Support', 'Plex Media Server'))
                self.yac_lib_prefs_dir = str(Path(user_home_dir, 'Library', 'Application Support', 'YACReader', 'YACReaderLibrary'))
            case _:
                log(Severity.CRITICAL, 'config.py', 'OS not in list!')
                sys.exit()
        self.temp_cmd = Path(self.temp_path, 'sync_cmd.bat')


def config_section_map(section, value, cfg_file_path=get_config_file_path()):
    """
    Retrieve a value from a section of a config file.
    :param section: Name of section in which the value you want is found.
    :type section: str
    :param value: Name of the value you want to get as return
    :type value: str
    :param cfg_file_path: Path to the config file to look into
    :type cfg_file_path: str
    :rtype: str
    """
    # Read config file
    config = configparser.ConfigParser()
    config.read(cfg_file_path)
    config.sections()

    # Retrieve dict
    dict1 = {}
    try:
        options = config.options(section)
    except:
        return None
    for option in options:
        try:
            dict1[option] = config.get(section, option)
            if dict1[option] == -1:
                DebugPrint("skip: %s" % option)
        except:
            print("exception on %s!" % option)
            dict1[option] = None
    if value in dict1.keys():
        return dict1[value]
    else:
        return None
