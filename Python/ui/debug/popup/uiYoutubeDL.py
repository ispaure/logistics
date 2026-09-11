from commonUtils.ui import pyside
from wrappers import youtubedlWrapper as youtubedlWrapper


class YoutubeDLUI(pyside.Window):
    def __init__(self, remote_cls):
        super().__init__(f'Youtube Download Options [{remote_cls.name}]')

        # Set dimensions
        self.width = 500
        self.height = 355

        # YOUTUBE DOWNLOAD ---------------------------------------------------------------------------------------------
        panel = pyside.create_frame(self.dlg, pyside.QRect(5, 5, 490, 95))
        pyside.Label('Download from Youtube: ', panel, pyside.QRect(10, 10, 200, 13))
        pyside.button('Download All Channels', panel, pyside.QRect(85, 65, 320, 25),
                      youtubedlWrapper.download_all, remote_cls.youtube_dl_cfg_path)
        # --------------------------------------------------------------------------------------------------------------

        # CUSTOM PUSH --------------------------------------------------------------------------------------------------
        panel_ghetto = pyside.create_frame(self.dlg, pyside.QRect(5, 105, 490, 125))
        # Label: Package for PUSH to CLOUD from ELSEWHERE
        pyside.Label('Custom Push:', panel_ghetto, pyside.QRect(10, 10, 400, 20))
        pyside.button('PUSH Local Season Folders', panel_ghetto, pyside.QRect(85, 65, 320, 25),
                      youtubedlWrapper.push_seasons, remote_cls)
        pyside.button('PUSH Local Config', panel_ghetto, pyside.QRect(85, 95, 320, 25),
                      youtubedlWrapper.push_config, remote_cls)
        # --------------------------------------------------------------------------------------------------------------

        # CUSTOM PULL --------------------------------------------------------------------------------------------------
        panel_add_dir = pyside.create_frame(self.dlg, pyside.QRect(5, 235, 490, 115))
        # Label: Add Folder to CLOUD
        pyside.Label('Custom Pull:', panel_add_dir, pyside.QRect(10, 10, 400, 20))
        pyside.button('PULL Remote Config', panel_add_dir, pyside.QRect(85, 80, 320, 25),
                      youtubedlWrapper.pull_config, remote_cls)
        # --------------------------------------------------------------------------------------------------------------