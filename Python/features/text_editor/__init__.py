"""Independent, optional plain-text/code editing feature."""

FEATURE_DESCRIPTION = 'Edit text and code files with search, syntax highlighting and file options.'


def register():
    from .contributions import register as declaration

    return declaration()
