from commonUtils.pySideUtils import *
from wrappers import youtubedlWrapper as youtubedlWrapper


class YoutubeDLUI(Window):
    def __init__(self, remote_cls):
        super().__init__(f'Youtube Download Options [{remote_cls.name}]')

        # Set dimensions
        self.width = 500
        self.height = 355

        # YOUTUBE DOWNLOAD ---------------------------------------------------------------------------------------------
        panel = create_frame(self.dlg, QRect(5, 5, 490, 95))
        Label('Download from Youtube: ', panel, QRect(10, 10, 200, 13))
        button('Download All Channels', panel, QRect(85, 65, 320, 25), youtubedlWrapper.download_all, remote_cls.youtube_dl_cfg_path)
        # --------------------------------------------------------------------------------------------------------------

        # CUSTOM PUSH --------------------------------------------------------------------------------------------------
        panel_ghetto = create_frame(self.dlg, QRect(5, 105, 490, 125))
        # Label: Package for PUSH to CLOUD from ELSEWHERE
        Label('Custom Push:', panel_ghetto, QRect(10, 10, 400, 20))
        button('PUSH Local Season Folders', panel_ghetto, QRect(85, 65, 320, 25), youtubedlWrapper.push_seasons, remote_cls)
        button('PUSH Local Config', panel_ghetto, QRect(85, 95, 320, 25), youtubedlWrapper.push_config, remote_cls)
        # --------------------------------------------------------------------------------------------------------------

        # CUSTOM PULL --------------------------------------------------------------------------------------------------
        panel_add_dir = create_frame(self.dlg, QRect(5, 235, 490, 115))
        # Label: Add Folder to CLOUD
        Label('Custom Pull:', panel_add_dir, QRect(10, 10, 400, 20))
        button('PULL Remote Config', panel_add_dir, QRect(85, 80, 320, 25), youtubedlWrapper.pull_config, remote_cls)
        # --------------------------------------------------------------------------------------------------------------
