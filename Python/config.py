import configparser
from pathlib import Path
from commonUtils.osUtils import *
from commonUtils.debugUtils import *
from commonUtils import marcUtils, fileUtils
from typing import *


def get_dir_split_character():
    match get_os():
        case OS.WIN:
            return '\\'
        case _:
            return '/'


def get_config_file_path() -> Path:
    current_dir = Path(__file__).resolve().parent
    config_ini_path = current_dir / "configFile.ini"
    return config_ini_path


def get_plex_data_dir_linux() -> Optional[Path]:
    candidates = [
        Path("/var/lib/plexmediaserver/Library/Application Support/Plex Media Server"),
        Path.home() / ".var/app/tv.plex.PlexMediaServer/data/Plex Media Server",
        Path.home() / "snap/plexmediaserver/common/Library/Application Support/Plex Media Server",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


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
        config_file_path: Path = get_config_file_path()

        # Get Server Path
        user_home_dir = fileUtils.get_user_home_dir()
        match get_os():
            case OS.WIN:
                sub_server_path = config_section_map('DirectoryStructure', 'server_path_win32', config_file_path)
                self.server_path: Path = Path(user_home_dir, sub_server_path)
            case OS.MAC:
                sub_server_path_macos = config_section_map('DirectoryStructure', 'server_path_macos', config_file_path)
                self.server_path: Path = Path(user_home_dir, sub_server_path_macos)
            case OS.LINUX:
                sub_server_path_linux = config_section_map('DirectoryStructure', 'server_path_linux', config_file_path)
                self.server_path: Path = Path(user_home_dir, sub_server_path_linux)

        # Get Logistics directory
        current_file = Path(__file__).resolve()
        self.path_logistics: Path = current_file.parent.parent
        # Get Scripts directory
        self.path_logistics_scripts: Path = Path(self.path_logistics, 'Scripts')

        # Get Logistics software directory
        marc_dropbox_path = marcUtils.get_marc_dropbox_root()

        if os.path.isdir(Path(__file__).resolve().parent.parent / 'Software') and os.path.isdir(Path(__file__).resolve().parent.parent / 'RemoteCredentials'):
            self.path_logistics_software: Path = Path(__file__).resolve().parent.parent / 'Software'
            self.path_logistics_remote_cred: Path = Path(__file__).resolve().parent.parent / 'RemoteCredentials'
        elif os.path.isdir(marc_dropbox_path):
            self.path_logistics_software: Path = Path(marc_dropbox_path, 'Software', 'GIT', 'logistics', 'Software')
            self.path_logistics_remote_cred: Path = Path(marc_dropbox_path, 'Software', 'GIT', 'logistics', 'RemoteCredentials')
        else:
            self.path_logistics_software: Path = Path(self.server_path, 'Logistics', 'Software')
            self.path_logistics_remote_cred: Path = Path(self.server_path, 'Logistics', 'RemoteCredentials')

        # Get Logistics software director per-platform
        self.path_logistics_software_win: Path = Path(self.path_logistics_software, 'Windows')
        self.path_logistics_software_mac: Path = Path(self.path_logistics_software, 'macOS')
        self.path_logistics_software_linux: Path = Path(self.path_logistics_software, 'Linux')
        self.path_logistics_software_general: Path = Path(self.path_logistics_software, 'General')

        # Other paths
        self.temp_path: Path = Path(self.path_logistics, 'temp')
        self.path_remote_network_mount: Path = Path(self.server_path, config_section_map('DirectoryStructure', 'remote_network_mount_sub_path', config_file_path))
        self.path_remote_local: Path = Path(self.server_path, config_section_map('DirectoryStructure', 'remote_local_sub_path', config_file_path))
        if os.path.isdir(marc_dropbox_path):
            self.path_minecraft_servers_java: Optional[Path] = Path(marc_dropbox_path, 'Software', 'Server', 'Minecraft')
            self.path_minecraft_servers_bedrock: Optional[Path] = Path(marc_dropbox_path, 'Software', 'Server', 'Minecraft (Bedrock)')
        else:
            self.path_minecraft_servers_java: Optional[Path] = None
            self.path_minecraft_servers_bedrock: Optional[Path] = None
        match get_os():
            case OS.WIN:
                self.pms_data_path: Optional[Path] = Path(os.environ['LOCALAPPDATA'], 'Plex Media Server')
                self.yac_lib_prefs_dir: Optional[Path] = None
            case OS.MAC:
                self.pms_data_path: Optional[Path] = Path(user_home_dir, 'Library', 'Application Support', 'Plex Media Server')
                self.yac_lib_prefs_dir: Optional[Path] = Path(user_home_dir, 'Library', 'Application Support', 'YACReader', 'YACReaderLibrary')
            case OS.LINUX:
                self.pms_data_path: Optional[Path] = get_plex_data_dir_linux()
                self.yac_lib_prefs_dir: Optional[Path] = Path(user_home_dir, ".local", "share", "YACReader", "YACReaderLibrary")


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
