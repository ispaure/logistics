"""Independent provider-backed Notes Library feature; presentation loads lazily."""
FEATURE_DESCRIPTION = 'Read, edit and organize local and LocalCrypt Notes Libraries.'


def create_page(parent=None):
    from .ui.page import NotesLibraryPage
    return NotesLibraryPage(parent)


def register():
    from features.contributions import Feature, PageContribution, FolderFeatureContribution
    from .notes_actions import available, actions
    return Feature(id='notes_library', label='Notes Library', optional_requires=('notebooks', 'rclone'),
        pages=[PageContribution('Notes Library', 'notes_library.workspace', create_page,
            order=17, navigation_icon='notes_library', launch_description=FEATURE_DESCRIPTION)],
        folder_features=[FolderFeatureContribution('Notes Library', available, actions,
            order=5, supports_private_folders=True)])
