"""Managed Blender installations and isolated user presets."""

FEATURE_DESCRIPTION = 'Manage Blender versions and isolated user presets.'
from pathlib import Path


def _create_page(parent=None):
    from .page import BlenderPage
    return BlenderPage(parent)


def register():
    from features.contributions import Feature, PageContribution, SettingsContribution
    return Feature(
        id='blender', label='Blender',
        pages=[PageContribution('Blender', 'blender', _create_page, order=65,
                                navigation_icon='blender')],
        settings=[SettingsContribution('Release downloads', 'blender_releases',
                                       config_files=(Path(__file__).with_name('config.ini'),))],
    )
