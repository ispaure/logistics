from typing import List, Optional
from pathlib import Path
from commonUtils import fileUtils, dirUtils, configUtils, appUtils
from commonUtils.wrappers import cmdShellWrapper
import webbrowser
from commonUtils.osUtils import *
from commonUtils.debugUtils import *
from enum import Enum
import commands


class MinecraftServerType(Enum):
    JAVA = "Java"
    BEDROCK = "Bedrock"
    UNKNOWN = "Unknown"


class MinecraftServer:
    def __init__(self, path: Path):
        self.path: Path = path
        self.name: str = path.name
        self.properties: fileUtils.TXTFile = fileUtils.TXTFile(path / 'server.properties')
        self.__log_name = f'{self.name} Minecraft Server'
        self.type: MinecraftServerType = self.__get_type()
        self.disk_app: Optional[appUtils.DiskApp] = self.__get_disk_app()
        self.wiki_url: Optional[str] = self.__get_wiki_url()

    def __get_cfg_value(self, section, value):
        cfg_file_path = self.path / 'logistics_cfg.ini'

        if not cfg_file_path.is_file():
            log(Severity.WARNING, self.__log_name, 'Could not retrieve info from logistics_cfg.ini')
            return None

        return configUtils.config_section_map(cfg_file_path, section, value)

    def __get_disk_app(self) -> Optional[appUtils.DiskApp]:

        match self.type:
            case MinecraftServerType.JAVA:

                # Get variable name (OS-dependent)
                match get_os():
                    case OS.WIN:
                        variable = 'win'
                    case OS.MAC:
                        variable = 'mac'
                    case OS.LINUX:
                        variable = 'linux'
                    case _:
                        raise Exception('Invalid OS')

                value = self.__get_cfg_value('LaunchScript', variable)

                if value is not None:
                    return appUtils.DiskApp(self.name, self.path / value, self.path)
                else:
                    return None

            case MinecraftServerType.BEDROCK:

                if get_os() == OS.WIN:
                    return appUtils.DiskApp(self.name, self.path / 'bedrock_server.exe', self.path)
                else:
                    return None

    def __get_wiki_url(self) -> Optional[str]:
        return self.__get_cfg_value('Documentation', 'wiki')

    def __get_type(self) -> MinecraftServerType:
        file_lst: List[fileUtils.File] = dirUtils.Directory(self.path).list_files(recursive=False)

        # If no files, label as "undefined"
        if not file_lst:
            return MinecraftServerType.UNKNOWN

        # If bedrock_server.exe exists, it is Bedrock
        for file in file_lst:
            if file.file_name == 'bedrock_server.exe':
                return MinecraftServerType.BEDROCK

        # Else Java
        return MinecraftServerType.JAVA

    # ------------------------------------------------------------------------------------------------------------------
    # Actions

    def launch_server(self):
        if self.disk_app is None:
            msg = f'Executable Path could not be determined for this platform. Aborting launch!'
            log(Severity.ERROR, self.__log_name, msg, popup=True)
            return

        self.disk_app.launch()

    def open_dir(self):
        dirUtils.Directory(self.path).open()

    def open_wiki(self):
        if self.wiki_url is None:
            msg = f'Wiki URL missing from config file'
            log(Severity.ERROR, self.__log_name, msg, popup=True)
            return

        webbrowser.open(self.wiki_url)

    def edit_properties(self):
        self.properties.edit_in_default_editor()

    def do_thing_2(self):
        pass

    # ------------------------------------------------------------------------------------------------------------------
    # Can I Action?

    def is_launchable(self):
        return self.disk_app is not None

    def can_open_dir(self):
        return self.path.is_dir()

    def can_open_wiki(self):
        return self.wiki_url is not None

    def can_edit_props(self):
        return self.properties.path.is_file()


def get_minecraft_server_lst(servers_root: Path) -> List[MinecraftServer]:
    if not os.path.isdir(str(servers_root)):
        return []

    dir_lst: List[dirUtils.Directory] = dirUtils.Directory(servers_root).list_directories()

    # Else, create Minecraft servers from the list of directories
    minecraft_server_lst: List[MinecraftServer] = []
    for directory in dir_lst:
        if not directory.name.endswith('Backups'):
            mc_server = MinecraftServer(directory.path)
            minecraft_server_lst.append(mc_server)

    return minecraft_server_lst
