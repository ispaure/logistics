"""Executable-backed Git workspace; no UI or executable probing at import time."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

FEATURE_DESCRIPTION = 'Inspect repository changes, stage files and manage commits.'


def create_page(parent=None):
    from .ui.page import GitPage
    return GitPage(parent)


def create_settings(parent=None):
    from .ui.application_settings import GitPreferencesPanel
    return GitPreferencesPanel(parent)


def register():
    from pathlib import Path
    from features.contributions import Feature, PageContribution, SettingsContribution
    return Feature(id='git', label='Git', pages=[
        PageContribution('Git', 'git.workspace', create_page, order=15, navigation_icon='git'),
    ], settings=[SettingsContribution('Git preferences', 'git.preferences', create_settings, scope='personal',
                                      config_files=(Path(__file__).with_name('config.ini'),), config_scope='application', separate_tab=True)])
