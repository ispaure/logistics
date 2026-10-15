"""Platform-independent destination state; native widgets are presentation only."""
from commonUtils.ui.native.navigation_state import NavigationState as DestinationState

DESTINATIONS = ('home', 'files', 'documents', 'chat', 'settings')


DESTINATION_ITEMS = (
    ('home', 'Home', 'house', 'home'),
    ('files', 'Folder Hub', 'square.grid.2x2', 'ic_menu_mapmode'),
    ('documents', 'Documents', 'doc.on.doc', 'ic_menu_edit'),
    ('chat', 'Chat', 'bubble.left.and.bubble.right', 'ic_menu_send'),
    ('settings', 'Settings', 'gearshape', 'ic_menu_preferences'),
)


class NavigationState(DestinationState):
    def __init__(self, destination='home'):
        super().__init__(DESTINATIONS, destination=destination)


def install_folder_hub_icon(host):
    """Use the desktop hub glyph on both native navigation presentations."""
    from .hub_icons import ICONS
    adapter = host.adapter
    if adapter is None:
        return
    index = host.destinations.index('files')
    if hasattr(adapter, 'navigation'):
        from rubicon.objc import ObjCClass
        data = ObjCClass('NSData').alloc().initWithBase64EncodedString(ICONS['folder_hub'], options=0)
        image = ObjCClass('UIImage').imageWithData(data)
        image = ObjCClass('UIImage').imageWithCGImage(image.CGImage, scale=3, orientation=0)
        adapter.navigation[index].tabBarItem.image = image.imageWithRenderingMode(2)
    elif hasattr(adapter, 'bottom'):
        from android.util import Base64
        from android.graphics import BitmapFactory
        from android.graphics.drawable import BitmapDrawable
        data = Base64.decode(ICONS['folder_hub'], Base64.DEFAULT)
        bitmap = BitmapFactory.decodeByteArray(data, 0, len(data))
        drawable = BitmapDrawable(adapter.impl.native.getResources(), bitmap)
        for bar in (adapter.bottom, adapter.rail):
            if bar is not None:
                bar.getMenu().getItem(index).setIcon(drawable)
