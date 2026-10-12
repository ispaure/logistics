"""Managed Blender installations and isolated user presets."""

FEATURE_DESCRIPTION = 'Manage Blender versions and isolated user presets.'


def _create_page(parent=None):
    from .page import BlenderPage
    return BlenderPage(parent)


def _create_settings(parent, scope):
    from .settings import BlenderSettings
    return BlenderSettings(parent, scope=scope)


def register():
    from features.contributions import Feature, PageContribution, SettingsContribution
    return Feature(
        id='blender', label='Blender',
        pages=[PageContribution('Blender', 'blender', _create_page, order=65,
                                navigation_icon='blender')],
        settings=[SettingsContribution('Blender configuration', 'blender_release_defaults',
                    lambda parent: _create_settings(parent, 'application'), scope='application'),
                  SettingsContribution('Blender configuration', 'blender_release_overrides',
                    lambda parent: _create_settings(parent, 'personal'), scope='personal')],
    )
