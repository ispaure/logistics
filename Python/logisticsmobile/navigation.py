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
        refresh_apple_tab_items(host)
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


def refresh_apple_tab_items(host):
    """Give the wrapped controllers fresh items after final titles/icons exist.

    iOS 26 can retain the original OptionContainer label's compressed geometry
    when its item is reused by a navigation controller. Selection remeasures it,
    but rebuilding these five app-owned items avoids requiring any selection.
    """
    from rubicon.objc import ObjCClass
    adapter = host.adapter
    for index, (navigation, title) in enumerate(zip(adapter.navigation, host.labels)):
        image = navigation.tabBarItem.image
        navigation.title = title
        navigation.tabBarItem = ObjCClass('UITabBarItem').alloc().initWithTitle(
            title, image=image, tag=index)
        navigation.tabBarItem.accessibilityLabel = title
    adapter.impl.refresh_tabs()


def install_apple_selection(app):
    """Read UIKit selection after its tab-bar callback has finished switching.

    Toga 0.5.7 reports tabBar:didSelectItem: before selectedViewController is
    necessarily updated. Programmatic activate() already owns its selection.
    """
    host = app.native_host
    if host.adapter is None or not hasattr(host.adapter, 'navigation'):
        return
    pending = None

    def selected(widget, **kwargs):
        nonlocal pending
        if pending is not None:
            pending.cancel()
            pending = None
        if host.changing:
            return

        def complete():
            nonlocal pending
            pending = None
            if not app.active_host:
                return
            host._selected(widget)
            # Pack and toolbar ownership must use the newly visible controller,
            # after the host has also committed its destination state.
            if host.adapter is not None:
                host.adapter.controller.view.setNeedsLayout()
                host.adapter.controller.view.layoutIfNeeded()
            app.resize_workspace()
        pending = app.loop.call_soon(complete)

    host.root.on_select = selected
