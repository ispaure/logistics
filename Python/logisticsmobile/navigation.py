"""Platform-independent destination state; native widgets are presentation only."""
from commonUtils.ui.native.navigation_state import NavigationState as DestinationState

DESTINATIONS = ('home', 'files', 'documents', 'chat', 'settings')


DESTINATION_ITEMS = (
    ('home', 'Home', 'house', 'home'),
    ('files', 'Files', 'folder', 'ic_menu_agenda'),
    ('documents', 'Documents', 'doc.on.doc', 'ic_menu_edit'),
    ('chat', 'Chat', 'bubble.left.and.bubble.right', 'ic_menu_send'),
    ('settings', 'Settings', 'gearshape', 'ic_menu_preferences'),
)


class NavigationState(DestinationState):
    def __init__(self, destination='home'):
        super().__init__(DESTINATIONS, destination=destination)
