"""Independent, optional plain-text/code editing feature."""


def register():
    from .contributions import register as declaration
    return declaration()
