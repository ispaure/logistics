"""Editable native-ink reMarkable notebooks, with opaque archive preservation."""
FEATURE_DESCRIPTION = 'Create, edit and organize reMarkable notebooks, then export native ink as .rmdoc.'


def launch(parent=None):
    from .ui.workspace import open_workspace
    return open_workspace(parent)


def activate(context):
    from .ui.workspace import open_workspace
    return open_workspace(path=context.path)


def create_page(parent):
    from .ui.workspace import NotebookWorkspace
    return NotebookWorkspace(parent)


def register():
    from commonUtils.ui.features import FileType, BrowserExtension, FileActivation
    from features.contributions import Feature, PageContribution, DocumentLauncherContribution
    return Feature(id='notebooks', label='Notebooks',
        file_types=[FileType('features.notebooks.file_type:RMDOCFile', extensions=('rmdoc',))],
        browser=BrowserExtension(activation=[FileActivation('features.notebooks.file_type:RMDOCFile', activate)]),
        pages=[PageContribution('Notebooks', 'notebooks', create_page, order=5,
            navigation_icon='notebooks', launch_description=FEATURE_DESCRIPTION)],
        document_launchers=[DocumentLauncherContribution('rmdoc', 'reMarkable Notebook', launch,
            'notebooks', 15, new_document=launch, description=FEATURE_DESCRIPTION)])
