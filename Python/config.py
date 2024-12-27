import configparser
from pathlib import Path
import sys
import os


def get_dir_split_character():
    if sys.platform == 'win32':
        return '\\'
    else:
        return '/'


def get_config_file_path():
    # Get config file path
    python_script_file_path = str(Path(__file__))
    python_script_file_path_lst = python_script_file_path.split(get_dir_split_character())
    python_script_file_dir_lst = []
    for part in python_script_file_path_lst:
        if part != python_script_file_path_lst[-1]:
            python_script_file_dir_lst.append(part)

    python_script_file_dir = ''
    for part in python_script_file_dir_lst:
        python_script_file_dir += part + get_dir_split_character()

    config_file_path = str(Path(python_script_file_dir, 'configFile.ini'))

    return config_file_path


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

        # Retrieve and determine values
        if sys.platform == 'win32':
            user_home_dir = get_win32_user_home_dir()
            sub_server_path = config_section_map('DirectoryStructure', 'server_path_win32', config_file_path)
            self.server_path = str(Path(user_home_dir, sub_server_path))
            self.pms_data_path = str(Path(os.environ['LOCALAPPDATA'], 'Plex Media Server'))
            self.yac_lib_prefs_dir = None
            self.temp_path = config_section_map('DirectoryStructure', 'temp_path_win32', config_file_path)
        else:
            user_home_dir = os.environ['HOME']
            sub_server_path_macos = config_section_map('DirectoryStructure', 'server_path_macos', config_file_path)
            self.server_path = str(Path(user_home_dir, sub_server_path_macos))
            self.pms_data_path = str(Path(user_home_dir, 'Library', 'Application Support', 'Plex Media Server'))
            self.yac_lib_prefs_dir = str(Path(user_home_dir, 'Library', 'Application Support', 'YACReader', 'YACReaderLibrary'))
            self.temp_path = str(Path(user_home_dir, config_section_map('DirectoryStructure', 'temp_path_macos', config_file_path)))

        # Subpaths
        self.path_logistics = str(Path(self.server_path, config_section_map('DirectoryStructure', 'logistics_sub_path', config_file_path)))
        self.path_logistics_software = str(Path(self.path_logistics, 'Software'))
        self.path_remote_network_mount = str(Path(self.server_path, config_section_map('DirectoryStructure', 'remote_network_mount_sub_path', config_file_path)))
        self.path_remote_local = str(Path(self.server_path, config_section_map('DirectoryStructure', 'remote_local_sub_path', config_file_path)))
        self.temp_cmd = Path(self.path_logistics, 'Temp', 'sync_cmd.bat')


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
