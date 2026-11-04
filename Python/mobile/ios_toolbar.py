"""Logistics action semantics over UIKit's adaptive navigation bars.

Keep real bar items, not horizontal custom-view stacks: UIKit owns their axis,
shared glass and overflow. Android/content controls retain their existing owners.
"""
import weakref


def vertical_edge(controller):
    """Read the current container's bar preference, never a device model/size."""
    if controller is None:
        return 0
    from rubicon.objc import SEL
    traits = controller.traitCollection
    return int(traits.verticalBarEdge) if traits.respondsToSelector(SEL('verticalBarEdge')) else 0


def system_occlusions(controller):
    from .ios_reader_chrome import occlusion_geometry
    return occlusion_geometry(getattr(controller, 'view', None))


def bar_item(button, *, prominent=False, symbol=None):
    """Forward to the retained button's handler/menu without a custom view."""
    from rubicon.objc import ObjCClass, SEL
    native = button._impl.native
    item = getattr(button, '_ios_action_item', None)
    if item is None:
        if getattr(button, 'control_icon', None) == 'close':
            item = ObjCClass('UIBarButtonItem').alloc().initWithBarButtonSystemItem(
                24, target=native, action=SEL('onPress:'))
        else:
            item = ObjCClass('UIBarButtonItem').alloc().initWithImage(
                None, style=0, target=native, action=SEL('onPress:'))
        button._ios_action_item = item
        # Native items aren't Toga widgets. Keep enabled state live even when a
        # busy operation updates a button without rebuilding the current route.
        original = button._impl.set_enabled
        reference = weakref.ref(button)

        def set_enabled(value):
            original(value)
            control = reference()
            if control is not None:
                control._ios_action_item.enabled = value
        button._impl.set_enabled = set_enabled
    title = getattr(button, 'accessible_name', None) or native.accessibilityLabel or button.text or ''
    item.accessibilityLabel = str(title)
    icon = getattr(button, 'control_icon', None)
    from .appearance import apple_color
    item.tintColor = apple_color('text') if icon in {'more', 'overflow'} else None
    item.title = ('Save' if icon == 'save' else
                  str(button.text or title) if icon is None else str(title))
    symbol = symbol or getattr(button, '_toolbar_symbol', None)
    if getattr(button, 'control_icon', None) == 'overflow':
        symbol = 'ellipsis'
    if icon == 'save':
        # The download-shaped icon is ambiguous for saving an edited document.
        item.image = None
    elif icon != 'close':
        item.image = (ObjCClass('UIImage').systemImageNamed(symbol) if symbol
                      else native.imageForState(0))
    item.menu = native.menu
    # A target/action would make UIKit reserve the menu for a long press. Match
    # the original UIButton's primary-menu interaction on ordinary iPhones too.
    primary_menu = native.menu is not None and bool(native.showsMenuAsPrimaryAction)
    item.target = None if primary_menu else native
    item.action = None if primary_menu else SEL('onPress:')
    item.enabled = button.enabled
    item.style = 2 if prominent else 0
    if item.respondsToSelector(SEL('setSharesBackground:')):
        item.sharesBackground = not prominent and getattr(button, 'control_icon', None) != 'close'
    if item.respondsToSelector(SEL('setAxisBehavior:')):
        item.axisBehavior = 1 if getattr(button, '_toolbar_horizontal', False) else 0
    if item.respondsToSelector(SEL('setVisibilityPriority:')):
        # Status and primary actions survive ordinary tools in system overflow.
        item.visibilityPriority = 1000 if prominent or getattr(button, '_toolbar_priority', False) else 0
    return item


def action_groups(buttons):
    """Adjacent related actions share glass; navigation/completion stand apart."""
    groups = []
    for button in buttons:
        icon = getattr(button, 'control_icon', None)
        key = getattr(button, '_toolbar_group', None)
        if key is None:
            key = ('comic-navigation' if icon in ('previous_comic', 'next_comic')
                   else 'document-tools')
        if icon in ('close', 'save') or getattr(button, '_toolbar_prominent', False):
            key = id(button)
        if groups and groups[-1][0] == key:
            groups[-1][1].append(button)
        else:
            groups.append((key, [button]))
    return [group for _, group in groups]


def action_state(buttons):
    """Capture bar projection values without retaining widgets or private owners."""
    def identity(value):
        pointer = getattr(value, 'ptr', None)
        return pointer.value if pointer is not None else id(value) if value is not None else None
    return tuple((id(button), button.enabled, button.text,
                  getattr(button, 'accessible_name', None), getattr(button, 'control_icon', None),
                  getattr(button, '_toolbar_symbol', None), getattr(button, '_toolbar_group', None),
                  getattr(button, '_toolbar_prominent', False), getattr(button, '_toolbar_priority', False),
                  getattr(button, '_toolbar_horizontal', False),
                  identity(button._impl.native.menu), identity(button._impl.native.imageForState(0)))
                 for button in buttons)


def supplemental_fits(controller, count):
    """Reserve touch slots between the current system region and destination bar."""
    if not count or not vertical_edge(controller):
        return True
    tabs = controller.tabBarController
    tabs = tabs() if callable(tabs) else tabs
    if tabs is None or tabs.tabBar.isHidden():
        return True
    view = controller.view
    bar = tabs.tabBar
    frame = bar.convertRect(bar.bounds, toView=view)
    bounds = view.bounds
    # A horizontal destination bar does not share the vertical action column.
    if frame.size.height <= frame.size.width:
        return True
    start = float(bounds.origin.y)
    left, right = float(frame.origin.x), float(frame.origin.x + frame.size.width)
    for x, y, width, height in system_occlusions(controller):
        if min(right, x + width) > max(left, x):
            start = max(start, y + height)
    # The public tab-bar frame spans the entire side, including empty space.
    # Budget 44-point targets with 16 points between independent groups for
    # its visible destinations, Back/Close, overflow and supplemental controls.
    end = float(bounds.origin.y + bounds.size.height - view.safeAreaInsets.bottom)
    slots = len(list(bar.items or ())) + count + 2
    return end - start >= slots * 60


def mount_actions(controller, owner, buttons, *, overflow=True, supplemental=None):
    """Mount semantic groups in natural order; UIKit handles vertical ordering."""
    from rubicon.objc import ObjCClass, Block, ObjCBlock, objc_id, ns_from_py, SEL
    nav = controller.navigationItem
    buttons = list(buttons)
    supplemental = None if supplemental is None else list(supplemental)
    collapsed = bool(supplemental) and not supplemental_fits(controller, len(supplemental))
    edge = vertical_edge(controller)
    use_overflow = overflow and bool(edge)
    grouped = bool(nav.respondsToSelector(SEL('setTrailingItemGroups:')))
    pointer = getattr(controller, 'ptr', None)
    signature = (pointer.value if pointer is not None else id(controller),
                 action_state(buttons), edge, overflow, system_occlusions(controller),
                 action_state(supplemental or ()), collapsed)
    mounted = getattr(owner, '_ios_toolbar_mount', None)
    if grouped and mounted is not None and mounted[0] == signature:
        _, groups, pinned, additional = mounted
        # Layout callbacks must not replace an open menu's native groups. Check
        # actual ownership too: another screen can have reused this controller.
        if (list(nav.trailingItemGroups) == groups and nav.pinnedTrailingGroup == pinned
                and nav.additionalOverflowItems == additional):
            if supplemental is not None:
                mount_leading(controller, [] if collapsed else supplemental)
            return owner._ios_toolbar_items
    menus = [button for button in buttons if getattr(button, 'control_icon', None) in ('more', 'overflow')
             and button._impl.native.menu is not None] if use_overflow else []
    extra = supplemental if collapsed else []
    actions = [button for button in buttons if button not in menus]
    groups, pinned, ordinary = [], [], []
    for group in action_groups(actions):
        items = []
        for button in group:
            primary = (getattr(button, 'control_icon', None) == 'save'
                       or getattr(button, '_toolbar_prominent', False))
            item = bar_item(button, prominent=primary)
            (pinned if primary else items).append(item)
            if not primary:
                ordinary.append(item)
        if items and grouped:
            groups.append(ObjCClass('UIBarButtonItemGroup').alloc().initWithBarButtonItems(
                items, representativeItem=None))
    if grouped:
        nav.trailingItemGroups = groups
        nav.pinnedTrailingGroup = (ObjCClass('UIBarButtonItemGroup').alloc().initWithBarButtonItems(
            pinned, representativeItem=None) if pinned else None)
    else:
        # iOS 15 remains supported; its item arrays run from the outside inward.
        nav.rightBarButtonItems = [*pinned, *reversed(ordinary)]
    # Load live menus at presentation time: document/privacy/busy guards and
    # refreshed menu callbacks remain owned by their original action owners.
    if menus or extra:
        # Supplemental leading controls cannot be compressed by UIKit. When
        # the shared column runs out of space, keep their live actions in the
        # same native overflow menu instead of overlapping destination tabs.
        extra_actions, handlers = [], []
        for button in extra:
            item = bar_item(button)
            def invoke(action, button=button):
                if button.enabled:
                    button._impl.native.performSelector(SEL('onPress:'), withObject=None)
            handler = Block(invoke, None, objc_id)
            handlers.append(handler)
            action = ObjCClass('UIAction').actionWithTitle(item.title, image=item.image,
                                                         identifier=None, handler=handler)
            action.attributes = 0 if button.enabled else 1
            extra_actions.append(action)
        owner._ios_supplemental_handlers = handlers
        owner._ios_supplemental_actions = extra_actions
        def provide(completion):
            for button, action in zip(extra, extra_actions):
                action.attributes = 0 if button.enabled else 1
            children = list(extra_actions)
            children.extend(child for button in menus if button.enabled and button._impl.native.menu is not None
                            for child in button._impl.native.menu.children)
            ObjCBlock(completion, None, objc_id)(ns_from_py(children))
        provider = Block(provide, None, objc_id)
        nav.additionalOverflowItems = ObjCClass('UIDeferredMenuElement').elementWithUncachedProvider(provider)
        owner._ios_overflow_provider = provider
    elif nav.respondsToSelector(SEL('setAdditionalOverflowItems:')):
        nav.additionalOverflowItems = None
        owner._ios_overflow_provider = None
    owner._ios_toolbar_items = [button._ios_action_item for button in actions]
    if supplemental is not None:
        mount_leading(controller, [] if collapsed else supplemental)
    if grouped:
        owner._ios_toolbar_mount = (signature, groups, nav.pinnedTrailingGroup, nav.additionalOverflowItems)
    return owner._ios_toolbar_items


def mount_leading(controller, buttons, *, replaces_back=False):
    """Retain unchanged groups through UIKit trait/rotation layout callbacks."""
    from rubicon.objc import ObjCClass, SEL
    nav = controller.navigationItem
    buttons = list(buttons)
    grouped = bool(nav.respondsToSelector(SEL('setLeadingItemGroups:')))
    signature = (action_state(buttons), replaces_back, grouped, system_occlusions(controller))
    mounted = getattr(controller, '_ios_leading_mount', None)
    if mounted is not None and mounted[0] == signature:
        current = nav.leadingItemGroups if grouped else nav.leftBarButtonItems
        if (list(current or ()) == mounted[1]
                and bool(nav.leftItemsSupplementBackButton) == (not replaces_back)
                and bool(nav.hidesBackButton) == replaces_back):
            return
    nav.leftItemsSupplementBackButton = not replaces_back
    nav.hidesBackButton = replaces_back
    if grouped:
        projection = [ObjCClass('UIBarButtonItemGroup').alloc().initWithBarButtonItems(
            [bar_item(button)], representativeItem=None) for button in buttons]
        nav.leadingItemGroups = projection
    else:
        projection = [bar_item(button) for button in buttons]
        nav.leftBarButtonItems = projection
    controller._ios_leading_mount = (signature, projection)


def clear_actions(nav):
    from rubicon.objc import SEL
    nav.rightBarButtonItems = None
    if nav.respondsToSelector(SEL('setTrailingItemGroups:')):
        nav.trailingItemGroups = []
        nav.pinnedTrailingGroup = None
        nav.additionalOverflowItems = None


def sync_screen(app, view, destination):
    """Apply explicit screen actions and refresh retained folder bars on resize."""
    if not app.routes.apple or app.native_host.adapter is None:
        return
    controller = app.native_host.adapter.content_controller(destination)
    screens = app.routes.screens[destination]
    if not screens and hasattr(view, '_destination_actions'):
        controller = app.native_host.adapter.parent
    if screens:
        folder = app.routes.folders.screens.get((destination, screens[-1][0]))
        if folder is not None:
            header = getattr(folder.browser, 'location_bar', None)
            if header is not None and getattr(header, '_native_title_mounted', False):
                from .folder_title import mount_actions as mount_folder
                mount_folder(header, controller)
                return
    controls = getattr(view, '_ios_toolbar_buttons', None)
    if controls is None:
        return
    buttons = list(controls() if callable(controls) else controls)
    leading = list(getattr(view, '_ios_toolbar_leading', ()))
    for button in (*buttons, *leading):
        if button.parent is not None:
            button.parent.remove(button)
        button.app, button.window = app, app.main_window
    mount_actions(controller, view, buttons, overflow=getattr(view, '_ios_toolbar_overflow', True))
    if leading or hasattr(view, '_ios_toolbar_leading'):
        mount_leading(controller, leading, replaces_back=getattr(view, '_ios_toolbar_replaces_back', False))
    for widget in getattr(view, '_ios_toolbar_hidden', ()):
        if widget.parent is not None:
            widget.parent.remove(widget)
    fit_form(app, view, destination)
    title = getattr(view, '_ios_toolbar_title', None)
    if title is not None:
        controller.navigationItem.title = str(title() if callable(title) else title)



def fit_form(app, view, destination):
    """Refit declared forms to today's safe width, retaining source label text."""
    if getattr(view, '_ios_fitted_form', False):
        from .settings.forms import fit_section
        fit_section(view, app.adaptive.content_width(destination, margin=0))


def prepare_form(view, *, primary=None, cancel=None, back=None, primary_symbol='checkmark'):
    """Owners explicitly name navigation/completion actions; body actions stay put.

    Runs only for the iOS backend. Labels refer to declared buttons in the form,
    not arbitrary commands discovered or promoted by position/appearance.
    """
    if not type(view._impl).__module__.startswith('toga_iOS.'):
        return
    view._ios_fitted_form = True
    import toga
    def walk(widget):
        yield widget
        if isinstance(widget, toga.ScrollContainer):
            if widget.content is not None:
                yield from walk(widget.content)
        else:
            for child in widget.children:
                yield from walk(child)
    buttons = {widget.text: widget for widget in walk(view) if isinstance(widget, toga.Button)}
    if primary in buttons:
        button = buttons[primary]
        button._toolbar_prominent, button._toolbar_symbol = True, primary_symbol
        view._ios_toolbar_buttons = [button]
    if cancel in buttons or back in buttons:
        cancellation = cancel in buttons
        button = buttons[cancel if cancellation else back]
        button._toolbar_symbol = 'xmark' if cancellation else 'chevron.left'
        button.accessible_name = button.text
        view._ios_toolbar_leading = [button]
        view._ios_toolbar_replaces_back = True
    if not hasattr(view, '_ios_toolbar_buttons') and hasattr(view, '_ios_toolbar_leading'):
        view._ios_toolbar_buttons = []
