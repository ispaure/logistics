"""Editable native-ink reMarkable notebooks, with opaque archive preservation."""
FEATURE_DESCRIPTION = 'Create, edit and organize reMarkable notebooks, then export native ink as .rmdoc.'


def launch(parent=None):
    from services.documents.ui.notebooks import choose_notebook_document
    return choose_notebook_document(parent)


def new_document(parent=None):
    from services.documents.ui.notebooks import new_notebook_document
    return new_notebook_document(parent)


def activate(context):
    from .ui.workspace import open_workspace
    return open_workspace(path=context.path)


def register():
    from commonUtils.ui.features import FileType, BrowserExtension, FileActivation
    from features.contributions import Feature, DocumentLauncherContribution
    return Feature(id='notebooks', label='Notebooks',
        file_types=[FileType('features.notebooks.file_type:RMDOCFile', extensions=('rmdoc',))],
        browser=BrowserExtension(activation=[FileActivation('features.notebooks.file_type:RMDOCFile', activate)]),
        document_launchers=[DocumentLauncherContribution('rmdoc', 'Notebook (.rmdoc)', launch,
            'notebooks', 15, new_document=new_document, description=FEATURE_DESCRIPTION)])
