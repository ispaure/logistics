"""Independent, optional plain-text/code editing feature."""

FEATURE_DESCRIPTION = 'Edit text and code files, or browse Markdown Notes Libraries from location actions.'


def register():
    from .contributions import register as declaration

    return declaration()
