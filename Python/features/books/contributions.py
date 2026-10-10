"""Lazy settings and browser contributions for the standalone Books feature."""
from pathlib import Path
from commonUtils.ui.features import BrowserExtension, FileActivation, FileType, SelectionAction
from features.contributions import Feature, SettingsContribution, DocumentLauncherContribution


def create_settings(parent=None):
    from commonUtils.ui import pyside as qt
    label = qt.QLabel('Defaults apply to books without saved reading preferences.', parent)
    label.setWordWrap(True)
    return label


def create_controller(binding):
    from .controller import BooksController
    return BooksController(binding)


def read(context):
    return context.controller.open(context.path)


def edit(context):
    from .metadata_actions import edit_metadata
    return edit_metadata(context)


def single(context):
    return len(context.selection) == 1


def register():
    kind = 'features.books.file_type:EPUBFile'
    return Feature(id='books', label='Books & Comics',
                   document_launchers=[DocumentLauncherContribution('epub', 'EPUB Reader', launch, 'epub', 30)], file_types=(FileType(kind, extensions='epub'),),
                   browser=BrowserExtension(
                       actions=(SelectionAction('read', 'Read EPUB…', kind, read, is_available=single, order=5),
                                SelectionAction('metadata', 'Edit metadata…',
                                    (kind, 'features.comics.cbz:CBZFile', 'commonUtils.filesystem.directories:Directory'),
                                    edit, order=10, shared_key='books.edit_metadata')),
                       activation=(FileActivation(kind, read),), create_controller=create_controller),
                   settings=[SettingsContribution('Reader defaults', 'books_reader', create_settings,
                                                  config_files=(Path(__file__).with_name('config.ini'),))])


def launch(parent):
    from commonUtils.ui import pyside as qt
    path, _ = qt.QFileDialog.getOpenFileName(parent, 'Open EPUB', '', 'EPUB books (*.epub)')
    if path:
        from .controller import BooksController
        owner = getattr(parent, 'document_service_owner', parent)
        controller = getattr(owner, '_books_controller', None)
        if controller is None:
            controller = owner._books_controller = BooksController(owner)
        return controller.open(path)
