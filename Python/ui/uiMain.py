import wrappers.rcloneWrapper as rcloneWrapper
from commonUtils.ui import pyside
import ui.uiRemoteCredentials as uiRemoteCredentials
import ui.rclone.tabRclone as tabRclone
import ui.links.tabLinks as tabLinks
import ui.debug.tabDebug as tabDebug
import ui.smartHome.tabSmartHome as tabSmartHome
from minecraft import server as mcServer
from ui.minecraft import tabMinecraftServer
import ui.flightSim.tabFlightSim as tabFlightSim

from commonUtils.osUtils import *
from commonUtils.debugUtils import *


class MainMenu(pyside.Window):
    def __init__(self):
        super().__init__('Logistics Main UI Window')

        # Set dimensions
        self.width = 720
        self.height = 500

        # Central Widget
        self.centralwidget = pyside.QWidget(self.dlg)
        self.centralwidget.setObjectName("centralwidget")
        self.tabWidget = pyside.QTabWidget(self.centralwidget)
        self.tabWidget.setGeometry(pyside.QRect(10, 10, 700, 460))
        self.tabWidget.setToolTip("")
        self.tabWidget.setObjectName("tabWidget")

        # Set Font and Size
        match get_os():
            case OS.WIN:
                font_size = 10
            case OS.MAC:
                font_size = 13
            case OS.LINUX:
                font_size = 13

        self.tabWidget.setFont(pyside.QFont('Arial', font_size))

        # Load Credentials Button
        pyside.button_open_win('Load Remote Credentials...', self.centralwidget, pyside.QRect(10, 470, 200, 25),
                               uiRemoteCredentials.LoadRemoteCredentials)

        # Clear Credentials from machine
        pyside.button('Clear Rclone.conf', self.centralwidget, pyside.QRect(215, 470, 130, 25),
                      rcloneWrapper.clear_rclone_conf)

        # TAB (LINKS)
        self.tab_links = pyside.QWidget()
        self.tab_links.setEnabled(True)
        self.tab_links.setObjectName('Tab_Links')
        self.tabWidget.addTab(self.tab_links, '')
        tabLinks.display_links(self.tab_links)

        # TAB (SMART HOME)
        self.tab_smart_home = pyside.QWidget()
        self.tab_smart_home.setEnabled(True)
        self.tab_smart_home.setObjectName('Tab_Links')
        self.tabWidget.addTab(self.tab_smart_home, '')
        tabSmartHome.display_smart_home(self.tab_smart_home)

        # TAB (RCLONE LOCAL)
        self.tab_rclone_local = pyside.QWidget()
        self.tab_rclone_local.setEnabled(True)
        self.tab_rclone_local.setObjectName('Tab_Local')
        self.tabWidget.addTab(self.tab_rclone_local, "")
        tabRclone.display_remotes(self.tab_rclone_local, type='Local')

        # TAB (RCLONE REMOTE)
        self.tab_rclone_remote = pyside.QWidget()
        self.tab_rclone_remote.setEnabled(True)
        self.tab_rclone_remote.setObjectName("Tab_Remote")
        self.tabWidget.addTab(self.tab_rclone_remote, "")
        tabRclone.display_remotes(self.tab_rclone_remote, type='Remote')

        # TAB (MINECRAFT SERVERS: JAVA)
        self.tab_mc_servers_java = pyside.QWidget()
        self.tab_mc_servers_java.setEnabled(True)
        self.tab_mc_servers_java.setObjectName("Tab_MC_Servers_JAVA")
        self.tabWidget.addTab(self.tab_mc_servers_java, "")
        tabMinecraftServer.display_servers(self.tab_mc_servers_java, server_type=mcServer.MinecraftServerType.JAVA)

        # TAB (MINECRAFT SERVERS: BEDROCK)
        self.tab_mc_servers_bedrock = pyside.QWidget()
        self.tab_mc_servers_bedrock.setEnabled(True)
        self.tab_mc_servers_bedrock.setObjectName("Tab_MC_Servers_BEDROCK")
        self.tabWidget.addTab(self.tab_mc_servers_bedrock, "")
        tabMinecraftServer.display_servers(self.tab_mc_servers_bedrock,
                                           server_type=mcServer.MinecraftServerType.BEDROCK)

        # TAB (FLIGHT SIM)
        self.tab_flight_sim = pyside.QWidget()
        self.tab_flight_sim.setEnabled(True)
        self.tab_flight_sim.setObjectName("Tab_FlightSim")
        self.tabWidget.addTab(self.tab_flight_sim, "")
        tabFlightSim.display_flight_sim(self.tab_flight_sim)

        # TAB (DEBUG)
        self.tab_debug = pyside.QWidget()
        self.tab_debug.setEnabled(True)
        self.tab_debug.setObjectName("Tab_Debug")
        self.tabWidget.addTab(self.tab_debug, "")
        tabDebug.display_debug(self.tab_debug)

        _translate = pyside.QCoreApplication.translate

        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_links), _translate('MainWindow', 'Links'))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_smart_home), _translate('MainWindow', 'Smart Home'))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_rclone_local), _translate('MainWindow', 'Local'))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_rclone_remote), _translate('MainWindow', 'Remote'))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_mc_servers_java),
                                  _translate('MainWindow', 'Minecraft [JAVA]'))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_mc_servers_bedrock),
                                  _translate('MainWindow', 'Minecraft [BEDROCK]'))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_flight_sim), _translate('MainWindow', 'Flight Sim'))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_debug), _translate('MainWindow', 'Debug'))


def display_main_menu():
    main_menu = MainMenu()
    main_menu.display_ui()
