from commonUtils.ui import pyside
from features.links import actions as link_actions


def display_links(dialog_obj):
    """
    Display the contents of the links tab on the UI
    """

    # Create grid layout contained in scroll area
    widget_content, grid_layout = pyside.create_scroll_area_grid(
        target=dialog_obj,
        rect=pyside.QRect(5, 5, 685, 470),
        rect_content=pyside.create_size(690, 1000)
    )

    # SELF-IMPROVEMENT
    panel = pyside.create_frame(widget_content, pyside.QRect(5, 5, 660, 60))
    pyside.Label('SELF-IMPROVEMENT: ', panel, pyside.QRect(10, 10, 160, 13))
    pyside.button('Gratitude Journal', panel, pyside.QRect(10, 30, 130, 20),
                  link_actions.open_config_file_url, 'self_impr_gratitude_journal')
    pyside.button('Training Routine', panel, pyside.QRect(145, 30, 130, 20),
                  link_actions.open_config_file_url, 'self_impr_training_routine')
    pyside.button('Training Tracker', panel, pyside.QRect(280, 30, 130, 20),
                  link_actions.open_config_file_url, 'self_impr_training_tracker')
    pyside.button('Nutritional Tracker', panel, pyside.QRect(415, 30, 130, 20),
                  link_actions.open_config_file_url, 'self_impr_nutritional_tracker')
    pyside.button('Investments', panel, pyside.QRect(445 + 140 + 5 - 40, 30, 100, 20),
                  link_actions.open_config_file_url, 'invest_tracker')
    pyside.button('!Links Doc', panel, pyside.QRect(155, 6, 100, 20),
                  link_actions.open_config_file_url, 'links_gdoc')

    # QUICK LINKS
    panel = pyside.create_frame(widget_content, pyside.QRect(5, 70, 660, 60))
    pyside.Label('QUICK LINKS: ', panel, pyside.QRect(10, 10, 160, 13))
    pyside.button('Google', panel, pyside.QRect(10, 30, 60, 20), link_actions.open_config_file_url, 'google')
    pyside.button('Gmail', panel, pyside.QRect(75, 30, 55, 20), link_actions.open_config_file_url, 'gmail')
    pyside.button('Calendar', panel, pyside.QRect(135, 30, 70, 20), link_actions.open_config_file_url, 'gcalendar')
    pyside.button('Youtube', panel, pyside.QRect(210, 30, 65, 20), link_actions.open_config_file_url, 'youtube')
    pyside.button('RDC', panel, pyside.QRect(280, 30, 35, 20), link_actions.open_config_file_url, 'chromerdc')
    pyside.button('GDrive', panel, pyside.QRect(320, 30, 60, 20), link_actions.open_config_file_url, 'gdrive')
    pyside.button('Dropbox', panel, pyside.QRect(385, 30, 70, 20), link_actions.open_config_file_url, 'dropbox')
    pyside.button('iCloud', panel, pyside.QRect(460, 30, 65, 20), link_actions.open_config_file_url, 'icloud')

    # ENTERTAINMENT
    panel = pyside.create_frame(widget_content, pyside.QRect(5, 150, 660, 140))
    pyside.Label('ENTERTAINMENT: ', panel, pyside.QRect(10, 10, 120, 13))
    pyside.Label('Movies / TV Series / Anime / Audiobooks: ', panel, pyside.QRect(10, 45, 260, 13))
    pyside.button('PLEX', panel, pyside.QRect(260, 40, 80, 20), link_actions.open_config_file_url, 'plex_common_web')
    pyside.button('Tautulli', panel, pyside.QRect(345, 40, 80, 20),
                  link_actions.open_config_file_url, 'tautulli_common_local')
    pyside.button('Jellyfin', panel, pyside.QRect(430, 40, 70, 20),
                  link_actions.open_config_file_url, 'jellyfin_common_local')
    pyside.button('Sonarr', panel, pyside.QRect(505, 40, 70, 20),
                  link_actions.open_config_file_url, 'sonarr_common_local')
    pyside.button('Jackett', panel, pyside.QRect(580, 40, 70, 20),
                  link_actions.open_config_file_url, 'jackett_common_local')
    pyside.button('μTorrent', panel, pyside.QRect(580, 63, 70, 20),
                  link_actions.open_config_file_url, 'utorrent_common_local')

    pyside.Label('Books / Light Novels: ', panel, pyside.QRect(10, 80, 200, 13))
    pyside.button('CALIBRE WEB', panel, pyside.QRect(142, 78, 120, 20),
                  link_actions.open_config_file_url, 'calibre_common_web')
    pyside.Label('Artbooks / Mangas / Comics: ', panel, pyside.QRect(10, 115, 200, 13))
    pyside.button('KOMGA', panel, pyside.QRect(188, 112, 80, 20),
                  link_actions.open_config_file_url, 'komga_common_web')

    # RESERVED
    panel = pyside.create_frame(widget_content, pyside.QRect(5, 480, 660, 140))
    pyside.Label('RESERVED: ', panel, pyside.QRect(10, 10, 120, 13))
    pyside.Label('Movies / TV Series / Anime / Audiobooks: ', panel, pyside.QRect(10, 45, 260, 13))
    pyside.button('PLEX', panel, pyside.QRect(260, 40, 80, 20),
                  link_actions.open_config_file_url, 'plex_reserved_web')
    pyside.Label('Books / Light Novels: ', panel, pyside.QRect(10, 80, 200, 13))
    pyside.button('CALIBRE WEB', panel, pyside.QRect(142, 78, 120, 20),
                  link_actions.open_config_file_url, 'calibre_reserved_local')
    pyside.Label('Artbooks / Mangas / Comics: ', panel, pyside.QRect(10, 115, 200, 13))
    pyside.button('KOMGA', panel, pyside.QRect(188, 112, 80, 20),
                  link_actions.open_config_file_url, 'komga_reserved_local')
