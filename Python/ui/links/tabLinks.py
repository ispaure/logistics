
from commonUtils.pySideUtils import *
import commands


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
    button('Gratitude Journal', panel, QRect(10, 30, 130, 20), commands.open_config_file_url, 'self_impr_gratitude_journal')
    button('Training Routine', panel, QRect(145, 30, 130, 20), commands.open_config_file_url, 'self_impr_training_routine')
    button('Training Tracker', panel, QRect(280, 30, 130, 20), commands.open_config_file_url, 'self_impr_training_tracker')
    button('Nutritional Tracker', panel, QRect(415, 30, 130, 20), commands.open_config_file_url, 'self_impr_nutritional_tracker')
    button('Investments', panel, QRect(445 + 140 + 5 - 40, 30, 100, 20), commands.open_config_file_url, 'invest_tracker')
    button('!Links Doc', panel, QRect(155, 6, 100, 20), commands.open_config_file_url, 'links_gdoc')

    # QUICK LINKS
    panel = create_frame(widget_content, QRect(5, 70, 660, 60))
    Label('QUICK LINKS: ', panel, QRect(10, 10, 160, 13))
    button('Google', panel, QRect(10, 30, 60, 20), commands.open_config_file_url, 'google')
    button('Gmail', panel, QRect(75, 30, 55, 20), commands.open_config_file_url, 'gmail')
    button('Calendar', panel, QRect(135, 30, 70, 20), commands.open_config_file_url, 'gcalendar')
    button('Youtube', panel, QRect(210, 30, 65, 20), commands.open_config_file_url, 'youtube')
    button('RDC', panel, QRect(280, 30, 35, 20), commands.open_config_file_url, 'chromerdc')
    button('GDrive', panel, QRect(320, 30, 60, 20), commands.open_config_file_url, 'gdrive')
    button('Dropbox', panel, QRect(385, 30, 70, 20), commands.open_config_file_url, 'dropbox')
    button('iCloud', panel, QRect(460, 30, 65, 20), commands.open_config_file_url, 'icloud')

    # ENTERTAINMENT
    panel = create_frame(widget_content, QRect(5, 150, 660, 140))
    Label('ENTERTAINMENT: ', panel, QRect(10, 10, 120, 13))
    Label('Movies / TV Series / Anime / Audiobooks: ', panel, QRect(10, 45, 260, 13))
    button('PLEX', panel, QRect(260, 40, 80, 20), commands.open_config_file_url, 'plex_common_web')
    button('Tautulli', panel, QRect(345, 40, 80, 20), commands.open_config_file_url, 'tautulli_common_local')
    button('Jellyfin', panel, QRect(430, 40, 70, 20), commands.open_config_file_url, 'jellyfin_common_local')
    button('Sonarr', panel, QRect(505, 40, 70, 20), commands.open_config_file_url, 'sonarr_common_local')
    button('Jackett', panel, QRect(580, 40, 70, 20), commands.open_config_file_url, 'jackett_common_local')
    button('μTorrent', panel, QRect(580, 63, 70, 20), commands.open_config_file_url, 'utorrent_common_local')

    Label('Books / Light Novels: ', panel, QRect(10, 80, 200, 13))
    button('CALIBRE WEB', panel, QRect(142, 78, 120, 20), commands.open_config_file_url, 'calibre_common_web')
    Label('Artbooks / Mangas / Comics: ', panel, QRect(10, 115, 200, 13))
    button('KOMGA', panel, QRect(188, 112, 80, 20), commands.open_config_file_url, 'komga_common_web')

    # RESERVED
    panel = create_frame(widget_content, QRect(5, 480, 660, 140))
    Label('RESERVED: ', panel, QRect(10, 10, 120, 13))
    Label('Movies / TV Series / Anime / Audiobooks: ', panel, QRect(10, 45, 260, 13))
    button('PLEX', panel, QRect(260, 40, 80, 20), commands.open_config_file_url, 'plex_reserved_web')
    Label('Books / Light Novels: ', panel, QRect(10, 80, 200, 13))
    button('CALIBRE WEB', panel, QRect(142, 78, 120, 20), commands.open_config_file_url, 'calibre_reserved_local')
    Label('Artbooks / Mangas / Comics: ', panel, QRect(10, 115, 200, 13))
    button('KOMGA', panel, QRect(188, 112, 80, 20), commands.open_config_file_url, 'komga_reserved_local')
