"""Comics has one unified declaration consumed by the Logistics feature registry."""


def register():
    from .ui_contributions import register as declaration
    return declaration()


def register_file_types():
    """Compatibility helper; new integrations consume register() as a whole."""
    from features.registry import get_feature_definition
    return get_feature_definition('comics').register_types()
