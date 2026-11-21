"""Comics has one unified declaration consumed by the Logistics feature registry."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

# Keep public modules and runtime ownership stable; present one feature in Settings.
FEATURE_GROUP = 'books'


def register():
    from .ui_contributions import register as declaration
    return declaration()


def register_file_types():
    """Compatibility helper; new integrations consume register() as a whole."""
    from features.application import registry
    return registry.get_feature_definition('comics').register_types()
