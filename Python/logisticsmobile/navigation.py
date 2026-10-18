"""Platform-independent destination state; native widgets are presentation only."""
from commonUtils.ui.native.navigation_state import NavigationState as DestinationState

DESTINATIONS = ('home', 'files', 'documents', 'chat', 'settings')


DESTINATION_ITEMS = (
    ('home', 'Home', 'house', 'home'),
    ('files', 'Folder Hub', 'square.grid.2x2', 'ic_menu_mapmode'),
    ('documents', 'Documents', 'doc.on.doc', 'ic_menu_edit'),
    ('chat', 'Chat', 'bubble.left.and.bubble.right', 'ic_dialog_email'),
    ('settings', 'Settings', 'gearshape', 'ic_menu_preferences'),
)

# Application destinations use explicit artwork rather than OEM menu icons.
# The 24-point outlines match the meaning of the Apple navigation symbols.
ANDROID_DESTINATION_PATHS = {
    'documents': (
        ((7, 3), (15, 3), (20, 8), (20, 18), (7, 18), (7, 3)),
        ((15, 3), (15, 8), (20, 8)),
        ((4, 6), (4, 21), (17, 21)),
        ((10, 11), (17, 11)), ((10, 14), (17, 14)),
    ),
    'chat': (
        ((16, 13), (20, 13), (23, 16), (23, 5), (9, 5), (9, 7)),
        ((2, 8), (17, 8), (17, 18), (7, 18), (2, 22), (2, 8)),
        ((6, 12), (13, 12)), ((6, 15), (11, 15)),
    ),
    'settings': (
        ((9, 1), (15, 1), (15.5, 4), (17, 5), (20, 4), (23, 9),
         (20.5, 11), (20.5, 13), (23, 15), (20, 20), (17, 19),
         (15.5, 20), (15, 23), (9, 23), (8.5, 20), (7, 19),
         (4, 20), (1, 15), (3.5, 13), (3.5, 11), (1, 9),
         (4, 4), (7, 5), (8.5, 4), (9, 1)),
    ),
}


def eink_selection_indicator(bar, enabled, original=None):
    """Give checked Android destinations a square backing; preserve theme geometry."""
    if enabled:
        from com.google.android.material.shape import ShapeAppearanceModel
        if original is None:
            original = (bar.isItemActiveIndicatorEnabled(),
                        bar.getItemActiveIndicatorWidth(), bar.getItemActiveIndicatorHeight(),
                        bar.getItemActiveIndicatorShapeAppearance())
        # MaterialComponents themes can disable indicators entirely. A white
        # checked icon needs an explicitly enabled backing in both presentations.
        size = round(40 * bar.getResources().getDisplayMetrics().density)
        bar.setItemActiveIndicatorShapeAppearance(ShapeAppearanceModel.builder().build())
        bar.setItemActiveIndicatorWidth(size)
        bar.setItemActiveIndicatorHeight(size)
        bar.setItemActiveIndicatorEnabled(True)
        return original
    if original is not None:
        active, width, height, shape = original
        bar.setItemActiveIndicatorShapeAppearance(shape)
        bar.setItemActiveIndicatorWidth(width)
        bar.setItemActiveIndicatorHeight(height)
        bar.setItemActiveIndicatorEnabled(active)
    return None


def install_destination_icons(host):
    """Install app-owned glyphs on Android bottom bars and wide-screen rails."""
    install_folder_hub_icon(host)
    adapter = host.adapter
    if adapter is None or not hasattr(adapter, 'bottom'):
        return
    from android.graphics import Path, Paint
    from android.graphics.drawable import ShapeDrawable
    from android.graphics.drawable.shapes import PathShape
    for destination, lines in ANDROID_DESTINATION_PATHS.items():
        path = Path()
        for line in lines:
            path.moveTo(*line[0])
            for point in line[1:]:
                path.lineTo(*point)
        if destination == 'settings':
            path.addCircle(12, 12, 3.5, Path.Direction.CW)
        drawable = ShapeDrawable(PathShape(path, 24, 24))
        paint = drawable.getPaint()
        paint.setStyle(Paint.Style.STROKE)
        paint.setStrokeWidth(1.6)
        paint.setStrokeCap(Paint.Cap.ROUND)
        paint.setStrokeJoin(Paint.Join.ROUND)
        paint.setAntiAlias(True)
        drawable.setIntrinsicWidth(24)
        drawable.setIntrinsicHeight(24)
        index = host.destinations.index(destination)
        for bar in (adapter.bottom, adapter.rail):
            if bar is not None:
                # Independent instances let Material own each bar's tint state.
                bar.getMenu().getItem(index).setIcon(drawable.getConstantState().newDrawable().mutate())


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
