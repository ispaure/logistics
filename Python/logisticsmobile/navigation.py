"""Platform-independent destination state; native widgets are presentation only."""
from commonUtils.ui.native.navigation_state import NavigationState as DestinationState

DESTINATIONS = ('home', 'files', 'documents', 'chat', 'settings')


DESTINATION_ITEMS = (
    ('home', 'Home', 'house', 'home'),
    ('files', 'Workspaces', 'square.grid.2x2', 'ic_menu_mapmode'),
    ('documents', 'Documents', 'doc.on.doc', 'ic_menu_edit'),
    ('chat', 'Chat', 'bubble.left.and.bubble.right', 'ic_dialog_email'),
    ('settings', 'Settings', 'gearshape', 'ic_menu_preferences'),
)

# Generated directly from ui_new.sidebar.DestinationIcon; both platforms tint
# the same transparent artwork. Regenerate with Mobile/generate_navigation_icons.py.
DESTINATION_ICON_NAMES = {key: 'nav_' + key for key in DESTINATIONS}


def eink_selection_indicator(bar, enabled, original=None):
    """Make monochrome selection visible without changing native geometry."""
    if enabled:
        if original is None:
            original = (bar.isItemActiveIndicatorEnabled(),
                        bar.getItemActiveIndicatorWidth(), bar.getItemActiveIndicatorHeight(),
                        bar.getItemActiveIndicatorShapeAppearance())
        # MaterialComponents themes can disable indicators entirely. A white
        # checked icon needs an explicitly enabled backing in both presentations.
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
    if host.adapter is not None and hasattr(host.adapter, 'navigation'):
        install_apple_destination_icons(host)
        return
    adapter = host.adapter
    if adapter is None or not hasattr(adapter, 'bottom'):
        return
    install_android_navigation_appearance(host)
    from .hub_icons import ICONS
    from android.util import Base64
    from android.graphics import BitmapFactory
    from android.graphics.drawable import BitmapDrawable
    resources = adapter.impl.native.getResources()
    for destination, name in DESTINATION_ICON_NAMES.items():
        data = Base64.decode(ICONS[name], Base64.DEFAULT)
        bitmap = BitmapFactory.decodeByteArray(data, 0, len(data))
        # Bundled 3x artwork has a logical size of 24 dp at every density.
        bitmap.setDensity(480)
        drawable = BitmapDrawable(resources, bitmap)
        index = host.destinations.index(destination)
        for bar in (adapter.bottom, adapter.rail):
            if bar is not None:
                bar.getMenu().getItem(index).setIcon(drawable.getConstantState().newDrawable().mutate())


def create_android_destination_rail(host):
    """Build the app rail without changing the shared navigation adapter contract."""
    adapter = host.adapter
    from android.view import ContextThemeWrapper
    from com.google.android.material import R as MaterialR
    from java import jclass
    context = ContextThemeWrapper(adapter.impl._native_activity,
        MaterialR.style.Theme_MaterialComponents_DayNight)
    rail = jclass('io.github.ispaure.logisticsmobile.DestinationRailView')(
        context, host.destinations.index('settings') + 1)
    for index, label in enumerate(host.labels):
        item = rail.getMenu().add(0, index + 1, index, label)
        icon = adapter.bottom.getMenu().getItem(index).getIcon()
        item.setIcon(icon.getConstantState().newDrawable().mutate())
        item.setContentDescription(label)
    return rail


def install_android_navigation_appearance(host):
    """Keep Android chrome compact, including rails first created by a resize."""
    adapter = host.adapter
    if getattr(adapter, '_logistics_appearance_installed', False):
        return
    original = adapter.set_mode

    def compact_chrome():
        # Ordinary screens own their headings. Document routes explicitly opt
        # into a custom native bar containing their title and existing actions.
        bar = adapter.impl._native_activity.getSupportActionBar()
        if bar is not None and bar.isShowing() and not getattr(adapter, '_reader_action_bar_active', False):
            bar.hide()
        if adapter.rail is not None:
            from android.view import Gravity
            adapter.rail.setMenuGravity(Gravity.TOP)
        if getattr(host.window.app, '_document_tabs_hidden', False):
            adapter.impl.native_navigationview.setVisibility(8)

    def set_mode(mode):
        previous = adapter.mode
        if mode == 'rail' and adapter.rail is None:
            adapter.rail = create_android_destination_rail(host)
        original(mode)
        if adapter.mode != previous:
            compact_chrome()
            from .appearance import refresh_android_navigation
            refresh_android_navigation(host)

    adapter.set_mode = set_mode
    adapter._logistics_appearance_installed = True
    # The shared host may already have mounted its default tablet rail before
    # application appearance is installed. Rebind through its normal route-safe
    # transition so OptionItem references and keyboard ownership follow the view.
    if adapter.rail is not None:
        mounted = adapter.mode == 'rail'
        if mounted:
            original('bottom')
        # Saved E Ink geometry belongs to the old native instance.
        getattr(adapter, '_eink_bar_styles', {}).pop(1, None)
        adapter.rail = None
        adapter.rail = create_android_destination_rail(host)
        if mounted:
            original('rail')
    compact_chrome()


class NavigationState(DestinationState):
    def __init__(self, destination='home'):
        super().__init__(DESTINATIONS, destination=destination)


def install_apple_destination_icons(host):
    """Retain real Toga icons so rebuilt tab items cannot restore its star.

    Toga 0.5.7 recreates UITabBarItem from OptionItem.icon when a title or icon
    changes. Assigning only navigation.tabBarItem.image leaves that model empty.
    Render native artwork to tiny cache PNGs and give each OptionItem an Icon;
    UIKit then keeps the same template image through its normal update path.
    """
    from pathlib import Path
    import toga
    from rubicon.objc import ObjCClass, Block, objc_id
    from toga_iOS.libs import UIGraphicsImageRenderer, CGSize, CGRect
    from toga_iOS.images import nsdata_to_bytes
    from .hub_icons import ICONS

    cache = Path(host.window.app.paths.cache) / 'navigation-icons-v2'
    cache.mkdir(parents=True, exist_ok=True)
    renderer = UIGraphicsImageRenderer.alloc().initWithSize(CGSize(24, 24))
    scale = int(renderer.format.scale)
    for key, item in zip(host.destinations, host.root.content):
        data = ObjCClass('NSData').alloc().initWithBase64EncodedString(
            ICONS[DESTINATION_ICON_NAMES[key]], options=0)
        image = ObjCClass('UIImage').imageWithData(data)
        if image is None:
            raise ValueError('Missing navigation artwork: ' + key)

        def draw(context):
            ratio = min(24 / float(image.size.width), 24 / float(image.size.height))
            width, height = float(image.size.width) * ratio, float(image.size.height) * ratio
            image.drawInRect(CGRect(((24 - width) / 2, (24 - height) / 2), (width, height)))

        path = cache / f'{key}@{scale}x.png'
        path.write_bytes(nsdata_to_bytes(renderer.PNGDataWithActions(Block(draw, None, objc_id))))
        icon = toga.Icon(path)
        icon._impl.native = icon._impl.native.imageWithRenderingMode(2)
        item.icon = icon
    refresh_apple_tab_items(host)


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
    if getattr(host.adapter, 'sidebar_used', False):
        # iPad's modern tabs can switch native controllers without invoking
        # Toga 0.5.7's tabBar:didSelectItem:. Keep Python route state in sync too.
        delegate = apple_selection_delegate().alloc().init()
        delegate.owner = app
        host.adapter.controller.delegate = delegate
        app._apple_tab_selection_delegate = delegate



_apple_selection_delegate = None


def apple_selection_delegate():
    """iPad's unified tabs/sidebar use UITabBarControllerDelegate callbacks."""
    global _apple_selection_delegate
    if _apple_selection_delegate is None:
        from rubicon.objc import ObjCClass, objc_method, objc_property, SEL

        class LogisticsTabSelectionDelegate(ObjCClass('NSObject')):
            owner = objc_property(object, weak=True)

            @objc_method
            def tabBarController_didSelectViewController_(self, controller, selected) -> None:
                app = self.owner
                if app is not None:
                    # Preserve Toga's layout refresh, then coalesce both old
                    # tab-bar and modern sidebar notifications through one path.
                    controller.performSelector(SEL('refreshContent'), withObject=None, afterDelay=0)
                    app.native_host.root.on_select()

        _apple_selection_delegate = LogisticsTabSelectionDelegate
    return _apple_selection_delegate
