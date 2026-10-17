"""Lazy settings and browser contributions for the standalone Books feature."""
from pathlib import Path
from commonUtils.ui.features import BrowserExtension, FileActivation, FileType, SelectionAction
from features.contributions import Feature, SettingsContribution, DocumentLauncherContribution


def create_settings(parent=None):
    from commonUtils.ui import pyside as qt
    label = qt.QLabel('Reader settings apply to every book. Markdown and EPUB share the Reading font in Appearance & shared controls. Reading positions and bookmarks remain per book.', parent)
    label.setWordWrap(True)
    return label


def create_controller(binding):
    from features.books.ui.controller import BooksController
    return BooksController(binding)


def read(context):
    return context.controller.open(context.path)


def edit(context):
    from features.books.ui.metadata_actions import edit_metadata
    return edit_metadata(context)


def single(context):
    return len(context.selection) == 1


def register():
    kind = 'features.books.file_type:EPUBFile'
    return Feature(id='books', label='Books & Comics',
                   document_launchers=[DocumentLauncherContribution('epub', 'EPUB Reader', launch, 'epub', 30, description='Read EPUB books and resume your progress.')], file_types=(FileType(kind, extensions='epub'),),
                   browser=BrowserExtension(
                       actions=(SelectionAction('read', 'Read EPUB…', kind, read, is_available=single, order=5),
                                SelectionAction('metadata', 'Edit metadata…',
                                    (kind, 'features.comics.cbz:CBZFile', 'commonUtils.filesystem.directories:Directory'),
                                    edit, order=10, shared_key='books.edit_metadata')),
                       activation=(FileActivation(kind, read),), create_controller=create_controller),
                   settings=[SettingsContribution('Reader defaults', 'books_reader', create_settings,
                                                  config_files=(Path(__file__).with_name('config.ini'),))])


def launch(parent):
    from services.reader_resources import choose_reader_document
    return choose_reader_document(parent, 'epub')
