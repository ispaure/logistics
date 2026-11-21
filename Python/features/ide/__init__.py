"""Independent project IDE; shared editor and analysis imports remain lazy."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

FEATURE_DESCRIPTION = 'Work on code projects with editing, search and code analysis.'

def create_page(parent=None):
    from features.ide.ui.page import IDEPage
    return IDEPage(parent)


def register():
    from features.contributions import Feature, PageContribution
    return Feature(id='ide', label='IDE', pages=[
        PageContribution('IDE', 'ide.workspace', create_page, order=16, navigation_icon='text')])
