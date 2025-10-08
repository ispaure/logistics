
import wrappers.rcloneWrapper as rcloneWrapper
import sys
from commonUtils.pySideUtils import *
import interactions
import config
import commands
import wrappers.plex.plexDatabaseReader as plexDatabaseReader
import ui.uiRemoteCredentials as uiRemoteCredentials
import ui.uiBatchConvertCBRtoCBZ as uiBatchConvertCBRtoCBZ
import ui.uiComicInfoBatchAuthorFromFolderName as uiComicInfoBatchAuthorFromFolderName
import ui.uiComicInfoBatchSeriesFromFolderName as uiComicInfoBatchSeriesFromFolderName
import ui.uiBatchIndividualFoldersforCBZ as uiBatchIndividualFoldersforCBZ
import ui.uiJPGExifBatchSetFieldComment as uiJPGExifBatchSetFieldComment
import ui.uiListFilesWeirdChars as uiListFilesWeirdChars
import ui.uiBatchRenameMKAfromCSV as uiBatchRenameMKAfromCSV
import ui.uiBulkDeletePYCInDir as uiBulkDeletePYCInDir
import ui.uiBatchCompressCBZ as uiBatchCompressCBZ
import wrappers.philipsHueWrapper as philipsHueWrapper
from flightSim import flightSimUtils
from commonUtils.osUtils import *
from commonUtils.debugUtils import *


def push_logistics():
    source_path = config.LogisticsConfig().path_logistics
    destination_path = 'Server-Logistics:'
    rcloneWrapper.rclone_sync(source_path, destination_path)


def pull_logistics():
    source_path = 'Server-Logistics:'
    destination_path = config.LogisticsConfig().path_logistics
    rcloneWrapper.rclone_sync(source_path, destination_path)


def display_remotes(dialog_obj, type):
    """
    Display remotes in the UI
    """

    # Get list of remotes
    remote_cls_lst = rcloneWrapper.get_all_remote_class()

    # Filter remotes by type (so you only show Local or Remote remotes since they each have their own tab)
    display_lst = []
    for remote_cls in remote_cls_lst:
        if remote_cls.type == type:
            display_lst.append(remote_cls)

    # Determine size of grid contents
    height_per_row = 30
    scroll_height = len(display_lst) * height_per_row + 50

    # Create grid layout contained in scroll area
    widget_content, grid_layout = create_scroll_area_grid(target=dialog_obj,
                                                          rect=QRect(0, 0, 700, 450),
                                                          rect_content=create_size(695, scroll_height))

    # Get interactions
    interactions_complete_lst, remote_amt = interactions.get_remote_cls_lst_interactions(display_lst)

    # Determine number of rows and columns
    positions = [(i, j) for i in range(len(display_lst)) for j in
                 range(len(interactions_complete_lst) // remote_amt)]

    # For each position (in order, from left to right, top to bottom) create a button with the correct thing
    for position, name in zip(positions, interactions_complete_lst):
        button_var = button(text=name[0](name[1])['Name'], target=widget_content, rect=QRect(0, 0, 120, 80), fn=name[0](name[1])['Action'], args=name[1])

        grid_layout.addWidget(button_var, *position)


def display_links(dialog_obj):
    """
    Display the contents of the links tab on the UI
    """

    # Create grid layout contained in scroll area
    widget_content, grid_layout = create_scroll_area_grid(target=dialog_obj,
                                                          rect=QRect(5, 5, 685, 470),
                                                          rect_content=create_size(690, 1000))

    # SELF-IMPROVEMENT
    panel = create_frame(widget_content, QRect(5, 5, 660, 60))
    Label('SELF-IMPROVEMENT: ', panel, QRect(10, 10, 160, 13))
    button('Gratitude Journal', panel, QRect(10, 30, 130, 20), commands.open_url, 'self_impr_gratitude_journal')
    button('Training Routine', panel, QRect(145, 30, 130, 20), commands.open_url, 'self_impr_training_routine')
    button('Training Tracker', panel, QRect(280, 30, 130, 20), commands.open_url, 'self_impr_training_tracker')
    button('Nutritional Tracker', panel, QRect(415, 30, 130, 20), commands.open_url, 'self_impr_nutritional_tracker')
    button('Investments', panel, QRect(445 + 140 + 5 - 40, 30, 100, 20), commands.open_url, 'invest_tracker')
    button('!Links Doc', panel, QRect(155, 6, 100, 20), commands.open_url, 'links_gdoc')

    # QUICK LINKS
    panel = create_frame(widget_content, QRect(5, 70, 660, 60))
    Label('QUICK LINKS: ', panel, QRect(10, 10, 160, 13))
    button('Google', panel, QRect(10, 30, 60, 20), commands.open_url, 'google')
    button('Gmail', panel, QRect(75, 30, 55, 20), commands.open_url, 'gmail')
    button('Calendar', panel, QRect(135, 30, 70, 20), commands.open_url, 'gcalendar')
    button('Youtube', panel, QRect(210, 30, 65, 20), commands.open_url, 'youtube')
    button('RDC', panel, QRect(280, 30, 35, 20), commands.open_url, 'chromerdc')
    button('GDrive', panel, QRect(320, 30, 60, 20), commands.open_url, 'gdrive')
    button('Dropbox', panel, QRect(385, 30, 70, 20), commands.open_url, 'dropbox')
    button('iCloud', panel, QRect(460, 30, 65, 20), commands.open_url, 'icloud')

    # ENTERTAINMENT
    panel = create_frame(widget_content, QRect(5, 150, 660, 140))
    Label('ENTERTAINMENT: ', panel, QRect(10, 10, 120, 13))
    Label('Movies / TV Series / Anime / Audiobooks: ', panel, QRect(10, 45, 260, 13))
    button('PLEX', panel, QRect(260, 40, 80, 20), commands.open_url, 'plex_common_web')
    button('Tautulli', panel, QRect(345, 40, 80, 20), commands.open_url, 'tautulli_common_local')
    button('Jellyfin', panel, QRect(430, 40, 70, 20), commands.open_url, 'jellyfin_common_local')
    button('Sonarr', panel, QRect(505, 40, 70, 20), commands.open_url, 'sonarr_common_local')
    button('Jackett', panel, QRect(580, 40, 70, 20), commands.open_url, 'jackett_common_local')
    button('μTorrent', panel, QRect(580, 63, 70, 20), commands.open_url, 'utorrent_common_local')

    Label('Books / Light Novels: ', panel, QRect(10, 80, 200, 13))
    button('CALIBRE WEB', panel, QRect(142, 78, 120, 20), commands.open_url, 'calibre_common_web')
    Label('Artbooks / Mangas / Comics: ', panel, QRect(10, 115, 200, 13))
    button('KOMGA', panel, QRect(188, 112, 80, 20), commands.open_url, 'komga_common_web')

    # RESERVED
    panel = create_frame(widget_content, QRect(5, 480, 660, 140))
    Label('RESERVED: ', panel, QRect(10, 10, 120, 13))
    Label('Movies / TV Series / Anime / Audiobooks: ', panel, QRect(10, 45, 260, 13))
    button('PLEX', panel, QRect(260, 40, 80, 20), commands.open_url, 'plex_reserved_web')
    Label('Books / Light Novels: ', panel, QRect(10, 80, 200, 13))
    button('CALIBRE WEB', panel, QRect(142, 78, 120, 20), commands.open_url, 'calibre_reserved_local')
    Label('Artbooks / Mangas / Comics: ', panel, QRect(10, 115, 200, 13))
    button('KOMGA', panel, QRect(188, 112, 80, 20), commands.open_url, 'komga_reserved_local')


def display_debug(dialog_obj):
    # Repair Windows Script
    button('Windows System Files Repair', dialog_obj, QRect(10, 10, 250, 30), commands.run_repair_windows_script)
    button('Repair NTFS on D:/', dialog_obj, QRect(10, 40, 250, 30), dialog_obj, commands.run_repair_ntfs_on_d)

    # PLEX Database Script
    button('PLEXDB - Parse Database test', dialog_obj, QRect(10, 70, 250, 30), plexDatabaseReader.test_script)

    # Batch Convert .CBR to .CBZ
    button_open_win('Batch Convert .CBR to .CBZ', dialog_obj, QRect(10, 100, 250, 30), uiBatchConvertCBRtoCBZ.DirBatchConvertCBRtoCBZ)
    # Batch ComicInfo.XML Folder name to Author Label
    button_open_win('ComicInfo.XML: Batch Set Author from Folder Name', dialog_obj, QRect(10, 130, 350, 30), uiComicInfoBatchAuthorFromFolderName.ComicInfoBatchAuthorFromFolderName)
    button_open_win('ComicInfo.XML: Batch Set Series from Folder Name', dialog_obj, QRect(10, 160, 350, 30), uiComicInfoBatchSeriesFromFolderName.ComicInfoBatchSeriesFromFolderName)
    button_open_win('.CBZ move in folder with name of file', dialog_obj, QRect(10, 190, 300, 30), uiBatchIndividualFoldersforCBZ.BatchIndividualFolderforCBZ)
    # List weird chars in dir (recursive)
    button_open_win('List Weird Chars in Dir', dialog_obj, QRect(10, 220, 200, 30), uiListFilesWeirdChars.ListFilesWeirdChars)
    # Rename MKA from CSV in Directory
    button_open_win('Rename MKA from CSV', dialog_obj, QRect(10, 250, 200, 30), uiBatchRenameMKAfromCSV.BatchRenameMKAfromCSV)

    # Hash change
    button_open_win('.JPG: EXIF Batch Set Comments Field', dialog_obj, QRect(260, 10, 250, 30), uiJPGExifBatchSetFieldComment.JPGEXIFBatchSetFieldComment)

    # MacOS Sleep
    button('Disable macOS Lid Sleep', dialog_obj, QRect(260, 40, 250, 30), commands.disable_macos_lid_sleep)
    button('Enable macOS Lid Sleep', dialog_obj, QRect(260, 70, 250, 30), commands.enable_macos_lid_sleep)

    # Bulk Delete .PYC in Dir
    button_open_win('Bulk Delete .PYC in Dir', dialog_obj, QRect(10, 280, 200, 30), uiBulkDeletePYCInDir.BulkDeletePYCInDir)

    # Batch Compress .CBZ in Dir
    button_open_win('Batch Compress .CBZ in Dir', dialog_obj, QRect(10, 310, 200, 30), uiBatchCompressCBZ.DirBatchCompressCBZWindow)


def display_lights(dialog_obj):
    """
    Display things to control lights
    """

    def display_room(line_name, line_height, panel):
        Label(str(line_name + ':'), panel, QRect(10, line_height + 5, 260, 13))
        button('OFF', panel, QRect(100, line_height, 50, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': False})
        button('1%', panel, QRect(155, line_height, 50, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Brightness': 0})
        button('50%', panel, QRect(210, line_height, 50, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Brightness': 127})
        button('100%', panel, QRect(265, line_height, 50, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Brightness': 255})
        button('ON', panel, QRect(320, line_height, 50, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True})
        button('R', panel, QRect(375, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Red'})
        button('O', panel, QRect(400, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Orange'})
        button('Y', panel, QRect(425, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Yellow'})
        button('G', panel, QRect(450, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Green'})
        button('A', panel, QRect(475, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Aqua'})
        button('B', panel, QRect(500, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Blue'})
        button('P', panel, QRect(525, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Purple'})
        button('M', panel, QRect(550, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'Magenta'})
        button('W', panel, QRect(575, line_height, 20, 20), philipsHueWrapper.set_group_prop_from_arg_dict,
                      {'Room': line_name, 'State': True, 'Color': 'White'})

    # LIGHTS
    panel = create_frame(dialog_obj, QRect(10, 10, 675, 150))
    button('Connect Bridge', panel, QRect(550, 5, 120, 20), philipsHueWrapper.connect_bridge)
    Label('LIGHTS: ', panel, QRect(10, 10, 120, 13))

    # Living Room
    display_room(line_name='Living Room', line_height=40, panel=panel)

    # Bedroom
    display_room(line_name='Bedroom', line_height=78, panel=panel)

    # Kitchen
    display_room(line_name='Kitchen', line_height=112, panel=panel)


def display_flight_sim(dialog_obj):
    """
    Display Flight Sim Tab things
    """
    panel = create_frame(dialog_obj, QRect(10, 10, 675, 150))
    Label('M3 Max: ', panel, QRect(10, 5, 350, 20))
    button('Preset: Standalone', panel, QRect(10, 25, 140, 30), flightSimUtils.set_xp12_m3_max_standalone)
    button('Preset: Flight Desk [Internal ON]', panel, QRect(155, 25, 250, 30), flightSimUtils.set_xp12_m3_max_flight_desk_internal)


class MainMenu(Window):
    def __init__(self):
        super().__init__('Logistics Main UI Window')

        # Set dimensions
        self.width = 720
        self.height = 500

        # Central Widget
        self.centralwidget = QWidget(self.dlg)
        self.centralwidget.setObjectName("centralwidget")
        self.tabWidget = QTabWidget(self.centralwidget)
        self.tabWidget.setGeometry(QRect(10, 10, 700, 460))
        self.tabWidget.setToolTip("")
        self.tabWidget.setObjectName("tabWidget")

        # Set Font and Size
        match get_os():
            case OS.WIN:
                font_size = 10
            case OS.MAC:
                font_size = 13
            case _:
                log(Severity.CRITICAL, 'uiMain', 'Platform unsupported!')
                return

        self.tabWidget.setFont(QFont('Arial', font_size))

        # Load Credentials Button
        button_open_win('Load Remote Credentials...', self.centralwidget, QRect(10, 470, 200, 25), uiRemoteCredentials.LoadRemoteCredentials)

        # Clear Credentials from machine
        button('Clear Rclone.conf', self.centralwidget, QRect(215, 470, 130, 25), rcloneWrapper.clear_rclone_conf)

        # Push Logistics
        button('PUSH Logistics', self.centralwidget, QRect(470, 470, 120, 25), push_logistics)

        # Pull Logistics
        button('PULL Logistics', self.centralwidget, QRect(590, 470, 120, 25), pull_logistics)

        # TAB (LINKS)
        self.tab_links = QWidget()
        self.tab_links.setEnabled(True)
        self.tab_links.setObjectName('Tab_Links')
        self.tabWidget.addTab(self.tab_links, '')
        display_links(self.tab_links)

        # TAB (SMART HOME)
        self.tab_smart_home = QWidget()
        self.tab_smart_home.setEnabled(True)
        self.tab_smart_home.setObjectName('Tab_Links')
        self.tabWidget.addTab(self.tab_smart_home, '')
        display_lights(self.tab_smart_home)

        # TAB (RCLONE LOCAL)
        self.tab_rclone_local = QWidget()
        self.tab_rclone_local.setEnabled(True)
        self.tab_rclone_local.setObjectName('Tab_Local')
        self.tabWidget.addTab(self.tab_rclone_local, "")
        display_remotes(self.tab_rclone_local, type='Local')

        # TAB (RCLONE REMOTE)
        self.tab_rclone_remote = QWidget()
        self.tab_rclone_remote.setEnabled(True)
        self.tab_rclone_remote.setObjectName("Tab_Remote")
        self.tabWidget.addTab(self.tab_rclone_remote, "")
        display_remotes(self.tab_rclone_remote, type='Remote')

        # TAB (FLIGHT SIM)
        self.tab_flight_sim = QWidget()
        self.tab_flight_sim.setEnabled(True)
        self.tab_flight_sim.setObjectName("Tab_FlightSim")
        self.tabWidget.addTab(self.tab_flight_sim, "")
        display_flight_sim(self.tab_flight_sim)

        # TAB (DEBUG)
        self.tab_debug = QWidget()
        self.tab_debug.setEnabled(True)
        self.tab_debug.setObjectName("Tab_Debug")
        self.tabWidget.addTab(self.tab_debug, "")
        display_debug(self.tab_debug)

        _translate = QCoreApplication.translate

        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_links), _translate('MainWindow', 'Links'))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_smart_home), _translate('MainWindow', 'Smart Home'))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_rclone_local), _translate('MainWindow', 'Local'))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_rclone_remote), _translate('MainWindow', 'Remote'))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_flight_sim), _translate('MainWindow', 'Flight Sim'))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_debug), _translate('MainWindow', 'Debug'))


def display_main_menu():
    main_menu = MainMenu()
    main_menu.display_ui()
