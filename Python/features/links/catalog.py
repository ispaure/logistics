"""
Link definitions used by the Logistics Links feature.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LinkEntry:
    label: str
    config_key: str


@dataclass(frozen=True)
class LinkGroup:
    name: str
    links: list[LinkEntry] = field(default_factory=list)


@dataclass(frozen=True)
class LinkCategory:
    name: str
    groups: list[LinkGroup] = field(default_factory=list)


LINK_CATEGORIES = [
    LinkCategory(
        name='Self-Improvement',
        groups=[
            LinkGroup(
                name='',
                links=[
                    LinkEntry('Gratitude Journal', 'self_impr_gratitude_journal'),
                    LinkEntry('Training Routine', 'self_impr_training_routine'),
                    LinkEntry('Training Tracker', 'self_impr_training_tracker'),
                    LinkEntry('Nutritional Tracker', 'self_impr_nutritional_tracker'),
                    LinkEntry('Investments', 'invest_tracker'),
                    LinkEntry('!Links Doc', 'links_gdoc'),
                ]
            )
        ]
    ),
    LinkCategory(
        name='Quick Links',
        groups=[
            LinkGroup(
                name='',
                links=[
                    LinkEntry('Google', 'google'),
                    LinkEntry('Gmail', 'gmail'),
                    LinkEntry('Calendar', 'gcalendar'),
                    LinkEntry('YouTube', 'youtube'),
                    LinkEntry('RDC', 'chromerdc'),
                    LinkEntry('GDrive', 'gdrive'),
                    LinkEntry('Dropbox', 'dropbox'),
                    LinkEntry('iCloud', 'icloud'),
                ]
            )
        ]
    ),
    LinkCategory(
        name='Entertainment',
        groups=[
            LinkGroup(
                name='Movies / TV Series / Anime / Audiobooks',
                links=[
                    LinkEntry('PLEX', 'plex_common_web'),
                    LinkEntry('Tautulli', 'tautulli_common_local'),
                    LinkEntry('Jellyfin', 'jellyfin_common_local'),
                    LinkEntry('Sonarr', 'sonarr_common_local'),
                    LinkEntry('Jackett', 'jackett_common_local'),
                    LinkEntry('μTorrent', 'utorrent_common_local'),
                ]
            ),
            LinkGroup(
                name='Books / Light Novels',
                links=[
                    LinkEntry('CALIBRE WEB', 'calibre_common_web'),
                ]
            ),
            LinkGroup(
                name='Artbooks / Mangas / Comics',
                links=[
                    LinkEntry('KOMGA', 'komga_common_web'),
                ]
            ),
        ]
    ),
]
