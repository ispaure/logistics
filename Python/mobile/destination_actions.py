"""Shared root actions projected into native trailing bars or Android headers."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from .appearance import surface
from .control_icons import icon_button


def prepare(app, view, destination):
    if destination not in ('home', 'files', 'documents'):
        return view
    if not isinstance(view, toga.Box) or getattr(view, '_hub_sections', False):
        original = view
        view = toga.Box(children=[original], style=Pack(direction=COLUMN, flex=1))
        view.content = getattr(original, 'content', original)
        if destination == 'home' and hasattr(original, '_home_primary_actions'):
            view._home_sections = original
            view._home_primary_actions = original._home_primary_actions
            view._home_primary_buttons = original._home_primary_buttons
    if hasattr(view, '_destination_actions'):
        return view
    # Existing root pages already own different content margins. Cancel that
    # contribution so the action row has one common window-relative inset.
    header = toga.Box(style=Pack(direction=ROW, align_items=CENTER, margin=(
        8 - (view.style.margin_top or 0), 16 - (view.style.margin_right or 0),
        8, 16 - (view.style.margin_left or 0))))
    unlock = surface(icon_button('storage_unlocked', 'Unlock LocalCrypt',
                                on_press=app.show_home_unlock), foreground='accent')
    unlock._toolbar_symbol = 'lock.open'
    unlock._toolbar_group = 'credentials'
    unlock._toolbar_priority = True
    buttons = [unlock]
    if destination == 'documents':
        opener = icon_button('folder_hub', 'Open document', on_press=app.open_hub_file)
        search = icon_button('find', 'Search documents', on_press=app.open_document_search)
        search._toolbar_symbol = 'magnifyingglass'
        view._document_search_button = search
        view._document_search_close = icon_button('close', 'Exit document search', on_press=app.close_document_search)
        new = icon_button('compose', 'New document', on_press=app.new_hub_document)
        opener._toolbar_symbol, new._toolbar_symbol = 'folder', 'plus'
        buttons.extend([opener, new, search])
    view._destination_actions = (header, buttons)
    def apple_actions():
        actions = selected(app, buttons)
        if destination == 'documents':
            searching = getattr(app, 'documents_search_open', False) or bool(getattr(app, 'documents_query', '').strip())
            view._ios_toolbar_leading = [view._document_search_close] if searching else []
            if searching:
                actions = [button for button in actions if button is not search]
        from .ios_toolbar import vertical_edge
        controller = app.native_host.adapter.content_controller(destination)
        # Horizontal groups run left-to-right; vertical groups run top-to-bottom.
        # Keep Unlock outermost horizontally and first in a vertical action rail.
        vertical = vertical_edge(controller)
        if destination == 'home' and vertical:
            return [*actions, *getattr(view, '_home_primary_buttons', ())]
        if buttons[0] in actions and not vertical:
            actions = [*actions[1:], actions[0]]
        return actions
    view._ios_toolbar_buttons = apple_actions
    view._ios_toolbar_leading = []
    view._ios_toolbar_overflow = False
    # Destination tabs/rail already identify these main pages. Keep their
    # actions without spending title space repeating the selected tab label.
    view._ios_toolbar_title = ''
    view._ios_toolbar_hidden = [header]
    view.insert(0, header)
    refresh(app, view)
    return view


def selected(app, buttons):
    return buttons if app.home_unlock_candidates() else buttons[1:]


def refresh(app, view):
    controls = getattr(view, '_destination_actions', None)
    if controls is None or app.routes.apple:
        return
    header, buttons = controls
    # Unlock is always the outside/rightmost action, independent of the tab.
    actions = selected(app, buttons)
    actions = [*actions[1:], actions[0]] if buttons[0] in actions else actions
    close = getattr(view, '_document_search_close', None)
    searching = close is not None and (getattr(app, 'documents_search_open', False) or bool(getattr(app, 'documents_query', '').strip()))
    if searching:
        actions = [button for button in actions if button is not view._document_search_button]
    leading = [close] if searching else []
    current = [child for child in header.children if isinstance(child, toga.Button)]
    if current == [*leading, *actions]:
        return
    header.clear()
    if actions:
        header.add(*leading, toga.Box(style=Pack(flex=1)), *actions)


def sync_native_host(app, view, destination):
    """Keep tab actions inside that tab's native navigation container.

    Putting actions above the tab controller gives UIKit separate bar owners;
    their controls can overlap instead of participating in shared compression.
    """
    if not app.routes.apple or app.native_host.adapter is None:
        return
    adapter = app.native_host.adapter
    overview = (not app.routes.screens[destination]
                and hasattr(view, '_destination_actions'))
    if overview and destination == 'home':
        from .home_header import sync
        overview = not sync(app, view) and bool(view._ios_toolbar_buttons())
    elif overview:
        overview = bool(selected(app, view._destination_actions[1]))
        # Documents commands stay in UIKit's bar for native hit testing.
        if destination == 'files' and project_header(app, view, destination):
            overview = False
    outer = adapter.outer_navigation
    if not outer.isNavigationBarHidden():
        outer.setNavigationBarHidden(True, animated=False)
    from .ios_system_occlusions import reserve_bar_clearance
    reserve_bar_clearance(outer)
    if not app.routes.screens[destination] and hasattr(view, '_destination_actions'):
        navigation = adapter.navigation_for(destination)
        if bool(navigation.isNavigationBarHidden()) == overview:
            navigation.setNavigationBarHidden(not overview, animated=False)
        reserve_bar_clearance(navigation)


def project_header(app, view, destination):
    """Use a measured free top column for overview actions after every pose.

    The original buttons and menus move intact. If any target cannot fit, all
    actions return to the adaptive native bar and its existing overflow policy.
    """
    from .ios_toolbar import vertical_edge, system_occlusions
    from .reader_top_band import free_top_band
    controller = app.native_host.adapter.content_controller(destination)
    native, window = controller.view, app.main_window._impl.native
    origin = native.convertRect(native.bounds, toView=window).origin
    buttons = list(view._ios_toolbar_buttons())
    buttons = [*view._ios_toolbar_leading, *buttons]
    sizes = [(max(44, button.style.width or 48), max(44, button.style.height or 48)) for button in buttons]
    from .fold_layout import division
    geometry = None
    if (buttons and not vertical_edge(controller) and abs(float(origin.y)) <= .5
            and division(app, view) is None):
        geometry = free_top_band(system_occlusions(controller), float(native.bounds.size.width),
            float(window.safeAreaInsets.top), sum(width for width, _ in sizes) + 32,
            row_height=max(height for _, height in sizes) + 16)
    state = getattr(view, '_destination_top_band', None)
    header = view._destination_actions[0]
    if geometry is None:
        if state is not None:
            if header.parent is not None:
                header.parent.remove(header)
            del header.style.height
            header.style.margin = state['margins']
            header.style.align_items = CENTER
            view._destination_top_band = None
        return False
    signature = (tuple(sorted(geometry.items())), tuple(id(button) for button in buttons))
    if state is not None and state['signature'] == signature:
        return True
    margins = state['margins'] if state is not None else tuple(
        getattr(header.style, 'margin_' + side) for side in ('top', 'right', 'bottom', 'left'))
    header.clear()
    # Keep actions at the top even when a detached activity extends the body
    # reservation. An auto-height row can center them inside that larger gap.
    row = toga.Box(style=Pack(direction=ROW, align_items=CENTER, height=max(height for _, height in sizes)))
    for button in buttons:
        if button.parent is not None:
            button.parent.remove(button)
        button.app, button.window = app, app.main_window
        row.add(button)
    header.add(row)
    header.style.align_items = 'start'
    header.style.height = geometry['reserve'] - 16
    header.style.margin = (8 - (view.style.margin_top or 0),
        geometry['width'] - geometry['right'] + 16 - (view.style.margin_right or 0),
        8, geometry['left'] + 16 - (view.style.margin_left or 0))
    if header.parent is None:
        view.insert(0, header)
    view._destination_top_band = dict(signature=signature, geometry=geometry, margins=margins,
                                      buttons=buttons, header=header)
    container = getattr(view._impl, 'container', None)
    if container is not None:
        app.native_host.adapter.layout_content(container)
    return True
