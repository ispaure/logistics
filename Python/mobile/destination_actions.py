"""Shared root actions projected into native trailing bars or Android headers."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from .appearance import action_button, surface
from .control_icons import icon_button


DUO_HEADINGS = dict(home='Home', files='Workspaces', documents='Documents', settings='Settings')


def prepare(app, view, destination):
    from .fold_layout import is_iphone_duo
    duo = app.routes.apple and is_iphone_duo()
    if destination == 'settings' and duo:
        from weakref import ref
        previous = getattr(view, '_duo_settings_root', lambda: None)()
        if previous is not None:
            return previous
        original = view
        view = toga.Box(children=[original], style=Pack(direction=COLUMN, flex=1))
        original._duo_settings_root = ref(view)
        prepare_duo_heading(view, destination)
        return view
    if destination not in ('home', 'files', 'documents'):
        return view
    if not isinstance(view, toga.Box) or getattr(view, '_hub_sections', False):
        original = view
        view = toga.Box(children=[original], style=Pack(direction=COLUMN, flex=1))
        view.content = getattr(original, 'content', original)
        if destination == 'home' and hasattr(original, '_home_primary_buttons'):
            view._home_sections = original
            view._home_primary_actions = original._home_primary_actions
            view._home_primary_buttons = original._home_primary_buttons
            view._home_prefer_native = getattr(original, '_home_prefer_native', False)
            view._destination_body_heading = getattr(original, '_destination_body_heading', None)
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
        search = icon_button('find', 'Search documents', on_press=app.open_document_search)
        search._toolbar_symbol = 'magnifyingglass'
        view._document_search_button = search
        view._document_search_close = icon_button('close', 'Exit document search', on_press=app.close_document_search)
        new = action_button(icon_button('compose', 'New document', on_press=app.new_hub_document))
        new._toolbar_symbol = 'plus'
        buttons.extend([new, search])
    header_buttons = buttons
    if destination == 'home' and not app.routes.apple:
        header_buttons = [*buttons, *getattr(view, '_home_primary_buttons', ())]
    view._destination_actions = (header, header_buttons)
    if destination == 'home' and getattr(view, '_home_primary_actions', None) is not None:
        view._home_toolbar_only = duo or getattr(view, '_home_prefer_native', False)

    def apple_actions():
        actions = selected(app, buttons)
        if destination == 'documents':
            searching = getattr(app, 'documents_search_open', False) or bool(getattr(app, 'documents_query', '').strip())
            view._ios_toolbar_leading = [view._document_search_close] if searching else []
            if searching:
                actions = [button for button in actions if button is not search]
        if destination == 'home':
            from .ios_toolbar import vertical_edge
            controller = app.native_host.adapter.content_controller(destination)
            if getattr(view, '_home_toolbar_only', False) or vertical_edge(controller):
                return [*getattr(view, '_home_primary_buttons', ()), *actions]
        if buttons[0] in actions:
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
    if duo:
        prepare_duo_heading(view, destination)
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
    if leading or actions:
        header.add(*leading, toga.Box(style=Pack(flex=1)), *actions)


def sync_native_host(app, view, destination, *, preparing_return=False):
    """Keep tab actions inside that tab's native navigation container.

    Putting actions above the tab controller gives UIKit separate bar owners;
    their controls can overlap instead of participating in shared compression.
    """
    if not app.routes.apple or app.native_host.adapter is None:
        return
    adapter = app.native_host.adapter
    root = preparing_return or not app.routes.screens[destination]
    overview = root and hasattr(view, '_destination_actions')
    # During willShow the root is still detached. The live navigation view
    # spans the same compact pane and can supply its window reservations.
    projection_host = adapter.navigation_for(destination) if preparing_return else None
    projected = (root and hasattr(view, '_duo_root_header') and
                 project_duo_heading(app, view, destination, controller=projection_host))
    if projected:
        overview = False
    elif overview and destination == 'home':
        from .home_header import sync
        overview = not sync(app, view) and bool(view._ios_toolbar_buttons())
    elif overview:
        overview = bool(selected(app, view._destination_actions[1]))
        if not hasattr(view, '_duo_root_header') and project_header(app, view, destination, controller=projection_host):
            overview = False
    outer = adapter.outer_navigation
    if not outer.isNavigationBarHidden():
        outer.setNavigationBarHidden(True, animated=False)
    from .ios_system_occlusions import reserve_bar_clearance
    reserve_bar_clearance(outer)
    if root and hasattr(view, '_destination_actions'):
        navigation = adapter.navigation_for(destination)
        if bool(navigation.isNavigationBarHidden()) == overview:
            navigation.setNavigationBarHidden(not overview, animated=preparing_return)
        reserve_bar_clearance(navigation)


def prepare_duo_heading(view, destination):
    title = toga.Label(DUO_HEADINGS[destination],
                       style=Pack(flex=1, text_align=CENTER, font_size=30, font_weight='bold'))
    view._duo_root_header = toga.Box(children=[title],
        style=Pack(direction=ROW, align_items=CENTER, height=48))
    body_title = getattr(view, '_destination_body_heading', None)
    if body_title is not None and body_title.parent is not None:
        view._duo_body_heading_slot = (body_title.parent, list(body_title.parent.children).index(body_title))


def duo_heading_geometry(regions, safe_top, left, right, required, *, vertical, fold=None):
    """Find a complete touch row beside the Island, within the content column."""
    from .ios_system_occlusions import control_top_clearance
    from .reader_top_band import NATIVE_TOOLBAR_CENTER_OFFSET, available_intervals
    if not regions or (not vertical and safe_top < 56):
        return None
    top = max(8, (safe_top - 48) / 2 + NATIVE_TOOLBAR_CENTER_OFFSET)
    bottom = top + 48
    obstructions = [*regions]
    if fold is not None and fold.vertical:
        # Reserve an actual crease, including when the OS reports zero width.
        obstructions.append((fold.x - 4, top, fold.width + 8, 48))
    for start, end in available_intervals(obstructions, left, right, top, bottom):
        if end - start >= required:
            reserve = control_top_clearance(regions, left, right, bottom + 4, target=48)
            return (start, end, top, reserve)
    return None


def project_duo_heading(app, view, destination, *, controller=None):
    from .fold_layout import division
    from .ios_reader_chrome import content_control, occlusion_geometry
    from .ios_toolbar import vertical_edge

    adapter = app.native_host.adapter
    if controller is None:
        controller = adapter.content_controller(destination)
    columns = getattr(app.adaptive, 'file_columns', None) if destination == 'files' else None
    host = columns.sidebar_box if columns is not None else view
    native = columns.sidebar.native if columns is not None else controller.view
    window = app.main_window._impl.native
    origin = native.convertRect(native.bounds, toView=window).origin
    safe = native.safeAreaInsets
    width = float(native.bounds.size.width)
    left, right = float(safe.left), width - float(safe.right)
    controls = getattr(view, '_ios_toolbar_buttons', None)
    actions = controls() if controls is not None else []
    buttons = [*getattr(view, '_ios_toolbar_leading', ()), *actions]
    source_row = getattr(view, '_workspaces_source_row', None)
    transfer = getattr(app, 'folder_transfers_button', None) if source_row is not None else None
    if transfer is not None and app.feature_enabled('rclone'):
        buttons.insert(0, transfer)
    regions = occlusion_geometry(window)
    regions = tuple((x - float(origin.x), y - float(origin.y), w, h) for x, y, w, h in regions
                    ) if regions else occlusion_geometry(native)
    required = 192 + sum(button.style.width + button.style.margin_left + button.style.margin_right
                         for button in buttons)
    geometry = None
    # The vertical rail has a usable top rectangle in open landscape. In
    # portrait a content header can paint above UIKit's interactive viewport.
    if abs(float(origin.y)) <= .5 and vertical_edge(controller):
        geometry = duo_heading_geometry(regions, float(window.safeAreaInsets.top), left, right,
                                        required, vertical=True, fold=division(app, view))
    fits = geometry is not None or right - left >= required

    state = getattr(view, '_duo_heading_state', None)
    signature = (geometry, tuple(map(id, buttons)), left, right, id(host)) if fits else None
    if state is not None and signature == state['signature']:
        return True
    header = view._duo_root_header
    body_title = getattr(view, '_destination_body_heading', None)
    if header.parent is not None and header.parent is not host:
        header.parent.remove(header)
    if state is not None:
        view._duo_heading_state = None
        view._duo_top_band = None
        header._duo_top_band = False
        if state['group'] is not None:
            state['group'].clear()
            header.remove(state['group'])
    if not fits:
        if transfer is not None and transfer.parent is None and app.feature_enabled('rclone'):
            source_row.add(transfer)
        if body_title is not None:
            if body_title.parent is None:
                original, index = view._duo_body_heading_slot
                original.insert(index, body_title)
            if header.parent is host:
                host.remove(header)
        else:
            # Keep the page heading below the normal system clearance when
            # the upper strip cannot fit the whole group.
            header.style.margin = (8, 16 - host.style.margin_right, 4, 16 - host.style.margin_left)
            if header.parent is None:
                host.insert(0, header)
    else:
        if body_title is not None and body_title.parent is not None:
            body_title.parent.remove(body_title)
        for button in buttons:
            if button.parent is not None:
                button.parent.remove(button)
            button.app, button.window = app, app.main_window
            content_control(button, glass=True)
        group = toga.Box(children=buttons, style=Pack(direction=ROW, align_items=CENTER)) if buttons else None
        if group is not None:
            header.add(group)
        state = view._duo_heading_state = dict(signature=signature, geometry=geometry, header=header,
                                              buttons=buttons, group=group)
        if geometry is not None:
            view._duo_top_band = state
            header._duo_top_band = True
            start, end, top, reserve = geometry
            header.style.margin = (top - host.style.margin_top, right - end + 16 - host.style.margin_right,
                                   reserve - top - 48, start - left + 16 - host.style.margin_left)
        else:
            header.style.margin = (0, 16 - host.style.margin_right, 4, 16 - host.style.margin_left)
        if header.parent is None:
            host.insert(0, header)
    container = getattr(host._impl, 'container', None)
    if columns is not None:
        columns.layout_sidebar(columns.sidebar)
    elif container is not None and (state is not None or fits):
        adapter.layout_content(container)
    return fits


def project_header(app, view, destination, *, controller=None):
    """Use a measured free top column for overview actions after every pose.

    The original buttons and menus move intact. If any target cannot fit, all
    actions return to the adaptive native bar and its existing overflow policy.
    """
    if destination == 'documents':
        # Keep Documents commands in the shared native bar so UIKit owns hit testing.
        return False
    from .ios_toolbar import vertical_edge, system_occlusions
    from .reader_top_band import free_top_band
    if controller is None:
        controller = app.native_host.adapter.content_controller(destination)
    native, window = controller.view, app.main_window._impl.native
    origin = native.convertRect(native.bounds, toView=window).origin
    buttons = list(view._ios_toolbar_buttons())
    buttons = [*view._ios_toolbar_leading, *buttons]
    from .fold_layout import division
    source_row = getattr(view, '_workspaces_source_row', None)
    if source_row is not None:
        return project_workspace_header(app, view, controller, source_row, buttons, origin,
                                        divided=division(app, view) is not None)
    sizes = [(max(44, button.style.width or 48), max(44, button.style.height or 48)) for button in buttons]
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


def project_workspace_header(app, view, controller, row, buttons, origin, *, divided):
    """Move the retained source and transfer controls together into the measured strip."""
    from .ios_toolbar import vertical_edge, system_occlusions
    from .reader_top_band import free_top_band, NATIVE_TOOLBAR_CENTER_OFFSET
    from .ui_metrics import TOUCH_TARGET

    header = view._destination_actions[0]
    state = getattr(view, '_destination_top_band', None)
    width = float(controller.view.bounds.size.width)
    window = app.main_window._impl.native
    tabs = list(row.children[0].children)
    # The equal-width selectors need room for Home Server. Always budget the
    # transfer shortcut so starting one cannot shrink other hit targets.
    required = 72 * len(tabs) + TOUCH_TARGET * (len(buttons) + 1) + 24
    geometry = None
    if not divided and not vertical_edge(controller) and abs(float(origin.y)) <= .5:
        geometry = free_top_band(system_occlusions(controller), width, float(window.safeAreaInsets.top),
                                 required, row_height=TOUCH_TARGET + 16,
                                 center_offset=NATIVE_TOOLBAR_CENTER_OFFSET)
    if geometry is None:
        restore_workspace_header(view)
        return False
    if state is None:
        parent = row.parent
        state = dict(source_parent=parent, source_index=list(parent.children).index(row),
                     source_margin=row.style.margin, actions=[])
        parent.remove(row)
        header.add(row)
    elif geometry == state['geometry'] and buttons == state['actions']:
        return True
    for button in state['actions']:
        row.remove(button)
    for index, button in enumerate(buttons, start=1):
        if button.parent is not None:
            button.parent.remove(button)
        button.app, button.window = app, app.main_window
        row.insert(index, button)
    # The outer box reserves the full system region. The source row keeps its
    # usual height and is centered on the same line as the reader controls.
    del header.style.align_items
    header.style.update(direction=COLUMN, height=geometry['reserve'],
        margin=(-view.style.margin_top, -view.style.margin_right, 0, -view.style.margin_left))
    row.style.margin = (geometry['row_top'] + 6, width - geometry['right'] + 8,
                        4, geometry['left'] + 8)
    if header.parent is None:
        view.insert(0, header)
    state.update(geometry=geometry, actions=buttons, buttons=[*tabs, *buttons], header=header)
    view._destination_top_band = state
    container = getattr(view._impl, 'container', None)
    if container is not None:
        app.native_host.adapter.layout_content(container)
    return True


def restore_workspace_header(view):
    row = getattr(view, '_workspaces_source_row', None)
    state = getattr(view, '_destination_top_band', None)
    if row is None or state is None:
        return
    for button in state['actions']:
        row.remove(button)
    header = state['header']
    header.remove(row)
    row.style.margin = state['source_margin']
    state['source_parent'].insert(state['source_index'], row)
    view.remove(header)
    view._destination_top_band = None
