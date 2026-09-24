from commonUtils.ui import pyside
from features.youtube_downloader import detection as youtube_downloader_detection
from features.youtube_downloader import downloader
from models.local_folder import LocalFolder


class YoutubeDLUI(pyside.Window):
    def __init__(self, folder: LocalFolder):
        super().__init__(f'Youtube Download Options [{folder.name}]')

        # Set dimensions
        self.width = 500
        self.height = 355

        youtube_dl_cfg_path = youtube_downloader_detection.get_config_path(folder)

        # YOUTUBE DOWNLOAD ---------------------------------------------------------------------------------------------
        panel = pyside.create_frame(self.dlg, pyside.QRect(5, 5, 490, 95))
        pyside.Label('Download from Youtube: ', panel, pyside.QRect(10, 10, 200, 13))
        pyside.button('Download All Channels', panel, pyside.QRect(85, 65, 320, 25),
                      downloader.download_all, youtube_dl_cfg_path)
        # --------------------------------------------------------------------------------------------------------------

        # CUSTOM PUSH --------------------------------------------------------------------------------------------------
        panel_ghetto = pyside.create_frame(self.dlg, pyside.QRect(5, 105, 490, 125))
        # Label: Package for PUSH to CLOUD from ELSEWHERE
        pyside.Label('Custom Push:', panel_ghetto, pyside.QRect(10, 10, 400, 20))
        pyside.button('PUSH Local Season Folders', panel_ghetto, pyside.QRect(85, 65, 320, 25),
                      downloader.push_seasons, folder)
        pyside.button('PUSH Local Config', panel_ghetto, pyside.QRect(85, 95, 320, 25),
                      downloader.push_config, folder)
        # --------------------------------------------------------------------------------------------------------------

        # CUSTOM PULL --------------------------------------------------------------------------------------------------
        panel_add_dir = pyside.create_frame(self.dlg, pyside.QRect(5, 235, 490, 115))
        # Label: Add Folder to CLOUD
        pyside.Label('Custom Pull:', panel_add_dir, pyside.QRect(10, 10, 400, 20))
        pyside.button('PULL Remote Config', panel_add_dir, pyside.QRect(85, 80, 320, 25),
                      downloader.pull_config, folder)
        # --------------------------------------------------------------------------------------------------------------
