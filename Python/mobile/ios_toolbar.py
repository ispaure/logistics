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
                  identity(button._impl.native.menu), identity(button._impl.native.imageForState(0)))
                 for button in buttons)


def mount_actions(controller, owner, buttons, *, overflow=True):
    """Mount semantic groups in natural order; UIKit handles vertical ordering."""
    from rubicon.objc import ObjCClass, Block, ObjCBlock, objc_id, ns_from_py, SEL
    nav = controller.navigationItem
    buttons = list(buttons)
    use_overflow = overflow and bool(vertical_edge(controller))
    menus = [button for button in buttons if getattr(button, 'control_icon', None) in ('more', 'overflow')
             and button._impl.native.menu is not None] if use_overflow else []
    actions = [button for button in buttons if button not in menus]
    grouped = bool(nav.respondsToSelector(SEL('setTrailingItemGroups:')))
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
    if menus:
        def provide(completion):
            children = [child for button in menus if button.enabled and button._impl.native.menu is not None
                        for child in button._impl.native.menu.children]
            ObjCBlock(completion, None, objc_id)(ns_from_py(children))
        provider = Block(provide, None, objc_id)
        nav.additionalOverflowItems = ObjCClass('UIDeferredMenuElement').elementWithUncachedProvider(provider)
        owner._ios_overflow_provider = provider
    elif nav.respondsToSelector(SEL('setAdditionalOverflowItems:')):
        nav.additionalOverflowItems = None
        owner._ios_overflow_provider = None
    owner._ios_toolbar_items = [button._ios_action_item for button in actions]
    return owner._ios_toolbar_items


def mount_leading(controller, buttons, *, replaces_back=False):
    from rubicon.objc import ObjCClass, SEL
    nav = controller.navigationItem
    nav.leftItemsSupplementBackButton = not replaces_back
    nav.hidesBackButton = replaces_back
    if nav.respondsToSelector(SEL('setLeadingItemGroups:')):
        nav.leadingItemGroups = [ObjCClass('UIBarButtonItemGroup').alloc().initWithBarButtonItems(
            [bar_item(button)], representativeItem=None) for button in buttons]
    else:
        nav.leftBarButtonItems = [bar_item(button) for button in buttons]


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
    mount_actions(controller, view, buttons)
    if leading:
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
