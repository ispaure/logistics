"""Lazy settings and browser contributions for the standalone Books feature."""
from pathlib import Path
from commonUtils.features import BrowserExtension, FileActivation, FileType, SelectionAction
from features.contributions import Feature, SettingsContribution


def create_settings(parent=None):
    from commonUtils.ui import pyside as qt
    label = qt.QLabel('Defaults apply when opening a book without saved reading preferences. '
                     'The reader also saves preferences and position per book in commonUtils/Cache/Books. '
                     'Metadata saves keep an original backup beside the EPUB.', parent)
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
    return Feature(id='books', label='Books & Comics', file_types=(FileType(kind, extensions='epub'),),
                   browser=BrowserExtension(
                       actions=(SelectionAction('read', 'Read EPUB…', kind, read, is_available=single, order=5),
                                SelectionAction('metadata', 'Edit metadata…',
                                    (kind, 'features.comics.cbz:CBZFile', 'commonUtils.dirUtils:Directory'),
                                    edit, order=10, shared_key='books.edit_metadata')),
                       activation=(FileActivation(kind, read),), create_controller=create_controller),
                   settings=[SettingsContribution('Reader defaults', 'books_reader', create_settings,
                                                  config_files=(Path(__file__).with_name('config.ini'),))])
