"""Independent, optional plain-text/code editing feature."""

FEATURE_DESCRIPTION = 'Edit plain text and code files.'


def register():
    from .contributions import register as declaration

    return declaration()
