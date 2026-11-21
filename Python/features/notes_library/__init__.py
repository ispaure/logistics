"""Independent provider-backed Notes Library feature; presentation loads lazily."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

FEATURE_DESCRIPTION = 'Read, edit and organize local and LocalCrypt Notes Libraries.'


def create_page(parent=None):
    from .ui.page import NotesLibraryPage
    return NotesLibraryPage(parent)


def register():
    from features.contributions import Feature, PageContribution, FolderFeatureContribution
    from .notes_actions import available, actions
    return Feature(id='notes_library', label='Notes Library', optional_requires=('notebooks', 'rclone', 'images', 'pdf'),
        pages=[PageContribution('Notes Library', 'notes_library.workspace', create_page,
            order=17, navigation_icon='notes_library', launch_description=FEATURE_DESCRIPTION)],
        folder_features=[FolderFeatureContribution('Notes Library', available, actions,
            order=5, supports_private_folders=True)])
