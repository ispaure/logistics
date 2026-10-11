"""Independent project IDE; shared editor and analysis imports remain lazy."""

def create_page(parent=None):
    from .page import IDEPage
    return IDEPage(parent)


def register():
    from features.contributions import Feature, PageContribution
    return Feature(id='ide', label='IDE', pages=[
        PageContribution('IDE', 'ide.workspace', create_page, order=16, navigation_icon='text')])
