"""Shared heading and actions for the five destination roots."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER, LEFT, NONE

from .appearance import action_button, surface
from .control_icons import icon_button
from .navigation import DESTINATION_ITEMS


HEADINGS = {key: title for key, title, *_ in DESTINATION_ITEMS}
GROUP_GAP = 8
HEADER_HEIGHT = 48
HEADER_INSET = 16
CENTERED_TITLE_WIDTH = 192


def prepare(app, view, destination):
    if hasattr(view, '_destination_actions'):
        return view
    if getattr(view, '_hub_sections', False):
        original = view
        view = toga.Box(children=[original], style=Pack(direction=COLUMN, flex=1))
        view.content = original.content
        view._home_primary_buttons = original._home_primary_buttons

    header = getattr(view, '_chat_destination_header', None)
    if header is None:
        header = toga.Box()
        view.insert(0, header)
    header.style.update(direction=ROW, align_items=CENTER, height=HEADER_HEIGHT)
    margin_header(header, view)
    title = toga.Label(HEADINGS[destination], style=Pack(flex=1, font_size=24, font_weight='bold'))
    spacer = toga.Box(style=Pack(width=0))
    header.add(title, spacer)
    buttons = []
    if destination in ('home', 'files', 'documents'):
        unlock = surface(icon_button('storage_unlocked', 'Unlock LocalCrypt',
                         on_press=app.show_home_unlock), foreground='accent')
        unlock._toolbar_symbol = 'lock.open'
        unlock._toolbar_group = 'credentials'
        unlock._toolbar_priority = True
        buttons.append(unlock)
    if destination == 'files':
        view._workspace_search = icon_button('find', 'Search local files',
            on_press=lambda widget: app.folder_controller().open_workspace_search())
    elif destination == 'documents':
        search = icon_button('find', 'Search documents', on_press=app.open_document_search)
        search._toolbar_symbol = 'magnifyingglass'
        new = action_button(icon_button('compose', 'New document', on_press=app.new_hub_document))
        new._toolbar_symbol = 'plus'
        buttons.extend((new, search))
    view._destination_actions = (header, buttons)
    view._destination_title = title
    view._destination_key = destination
    view._ios_toolbar_title = ''
    view._ios_toolbar_buttons = lambda: actions_for(app, view)
    view._ios_toolbar_leading = []
    view._ios_toolbar_overflow = destination == 'chat'
    refresh(app, view)
    return view


def actions_for(app, view):
    destination = view._destination_key
    if destination == 'chat':
        return list(view._chat_destination_buttons)
    if destination == 'settings':
        return []
    _, (unlock, *buttons) = view._destination_actions
    if destination == 'home':
        buttons = list(getattr(view, '_home_primary_buttons', ()))
    elif destination == 'files':
        if hasattr(view, '_workspaces_source_row') and app.feature_enabled('rclone'):
            buttons.extend((app.folder_view_toggle, app.folder_transfers_button))
        if getattr(app, 'folder_source', None) == 'Local':
            buttons.insert(0, view._workspace_search)
    if app.home_unlock_candidates():
        buttons.append(unlock)
    return buttons


def margin_header(header, host, *, top=4, right=HEADER_INSET, bottom=4, left=HEADER_INSET):
    header.style.margin = (top - host.style.margin_top, right - host.style.margin_right,
                           bottom, left - host.style.margin_left)


def mount_actions(view, buttons, *, apple):
    header, _ = view._destination_actions
    previous = getattr(view, '_destination_inline_actions', None)
    if previous == tuple(buttons):
        return
    if previous is not None:
        for button in previous:
            if button.parent is not None:
                button.parent.remove(button)
        for group in list(header.children)[2:]:
            header.remove(group)
    view._destination_inline_actions = tuple(buttons)
    if buttons:
        for button in buttons:
            if button.parent is not None:
                button.parent.remove(button)
        if apple:
            from .ios_toolbar import action_groups, inline_action_group
            controls = [inline_action_group(group) for group in action_groups(buttons)]
            header.add(toga.Box(children=controls, style=Pack(direction=ROW, align_items=CENTER, gap=GROUP_GAP)))
        else:
            header.add(*buttons)


def align_title(header, *, centered, space=None, center=None):
    title, spacer = header.children[:2]
    width, offset = NONE, 0
    if center is not None and space is not None:
        start, end = space
        width = round(min(CENTERED_TITLE_WIDTH, end - start))
        offset = round(max(0, min(end - start - width, center - start - width / 2)))
    title.style.update(text_align=CENTER if centered else LEFT, width=width,
                       margin_left=offset, flex=1 if width == NONE else 0)
    spacer.style.update(width=0 if width == NONE else NONE, flex=0 if width == NONE else 1)


def refresh(app, view):
    if not hasattr(view, '_destination_actions') or app.routes.apple or app.main_window is None:
        return
    header, _ = view._destination_actions
    align_title(header, centered=True)
    buttons = actions_for(app, view)
    update_unlock_hint(view, buttons)
    mount_actions(view, buttons, apple=False)


def update_unlock_hint(view, actions):
    hint = getattr(view, '_document_unlock_hint', None)
    if hint is not None:
        visible = view._destination_actions[1][0] in actions
        hint.style.update(display='pack' if visible else 'none',
                          visibility='visible' if visible else 'hidden')


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


def project_apple_heading(app, view, destination, controller, *, folder_sidebar=False):
    from .fold_layout import division, is_iphone_duo
    from .ios_reader_chrome import occlusion_geometry
    from .ios_system_occlusions import control_top_clearance
    from .ios_toolbar import action_groups, vertical_edge

    window = app.main_window._impl.native
    bounds = window.bounds.size
    duo = is_iphone_duo()
    landscape = bounds.width > bounds.height
    from rubicon.objc import ObjCClass
    tablet = int(ObjCClass('UIDevice').currentDevice.userInterfaceIdiom) == 1
    adapter = app.native_host.adapter
    columns = getattr(app.adaptive, 'file_columns', None) if destination == 'files' else None
    edge = vertical_edge(adapter.controller) or vertical_edge(controller)
    native_actions = bool(duo and edge)
    spans_columns = columns is not None and columns.side_by_side and not folder_sidebar
    if spans_columns:
        host, native = columns.heading_host(), columns.controller.view
    elif columns is not None:
        host, native = columns.sidebar_box, columns.sidebar.native
    else:
        host, native = view, controller.view

    header, _ = view._destination_actions
    actions = [] if folder_sidebar else actions_for(app, view)
    update_unlock_hint(view, actions)
    buttons = [] if native_actions else actions
    origin = native.convertRect(native.bounds, toView=window).origin
    safe = native.safeAreaInsets
    left, right = float(safe.left), float(native.bounds.size.width - safe.right)
    regions = tuple((x - float(origin.x), y - float(origin.y), w, h)
                    for x, y, w, h in occlusion_geometry(window)) or occlusion_geometry(native)
    action_width = sum((button.style.width or HEADER_HEIGHT) + button.style.margin_left + button.style.margin_right
                       for button in buttons) + max(0, len(action_groups(buttons)) - 1) * GROUP_GAP
    fold = division(app, app.main_window) if duo else None
    if fold is not None:
        from dataclasses import replace
        fold = replace(fold, x=fold.x - float(origin.x), y=fold.y - float(origin.y))
    geometry = None
    if duo and (landscape or bounds.width >= 550) and abs(float(origin.y)) <= .5:
        geometry = duo_heading_geometry(regions, float(window.safeAreaInsets.top), left, right,
                                        CENTERED_TITLE_WIDTH + action_width, vertical=bool(edge), fold=fold)
    start, end = geometry[:2] if geometry is not None else (left, right)
    title_end = end - HEADER_INSET - action_width
    if geometry is None and fold is not None and fold.vertical and start < fold.x:
        title_end = min(title_end, fold.x - 4)
    center = (float(bounds.width) / 2 - float(origin.x)
              if not folder_sidebar and landscape and (tablet or edge) else None)
    space = (start + HEADER_INSET, max(start + HEADER_INSET + 1, title_end))
    clearance = control_top_clearance(regions, left, right, float(safe.top), target=HEADER_HEIGHT)
    state = getattr(view, '_destination_heading_state', None)
    signature = (id(host), geometry, clearance, float(safe.top), left, right, space,
                 center, native_actions, tuple(map(id, actions)))
    if state is not None and state['signature'] == signature and header.parent is host:
        return native_actions and bool(actions)

    if header.parent is not None and header.parent is not host:
        header.parent.remove(header)
    mount_actions(view, buttons, apple=True)
    align_title(header, centered=True, space=space, center=center)
    if geometry is not None:
        _, _, top, reserve = geometry
        margin_header(header, host, top=top, right=right - end + HEADER_INSET,
                      bottom=reserve - top - HEADER_HEIGHT, left=start - left + HEADER_INSET)
    else:
        margin_header(header, host, top=max(0, clearance - float(safe.top)) + 4)
    header._destination_top_band = geometry is not None
    if header.parent is None:
        host.insert(0, header)
    view._destination_heading_state = dict(signature=signature, header=header,
        buttons=buttons, group=header.children[2] if buttons else None,
        native_actions=native_actions, title_space=space, center=center, spans_columns=spans_columns)
    if columns is not None:
        columns.layout_heading(float(safe.top) if spans_columns and geometry is None else 0)
        columns.layout_sidebar(columns.sidebar)
    elif (container := getattr(host._impl, 'container', None)) is not None:
        adapter.layout_content(container)
    return native_actions and bool(actions)


def detach_workspace_heading(app):
    root = next(iter(app.routes.roots['files'].children), None)
    actions = getattr(root, '_destination_actions', None)
    if actions is not None:
        from .file_drawer import detach
        detach(actions[0])


def sync_native_host(app, view, destination, *, preparing_return=False):
    if not app.routes.apple or app.native_host.adapter is None:
        return
    adapter = app.native_host.adapter
    from .ios_system_occlusions import reserve_bar_clearance
    outer = adapter.outer_navigation
    if not outer.isNavigationBarHidden():
        outer.setNavigationBarHidden(True, animated=False)
    reserve_bar_clearance(outer)
    screens = app.routes.screens[destination]
    if not preparing_return and screens:
        frame = getattr(view, '_workspace_frame', None)
        if destination == 'files':
            from .reader_lifecycle import document_stack
            if document_stack(screens):
                detach_workspace_heading(app)
            elif (getattr(app.adaptive, 'file_columns', None) is not None
                    and (hasattr(view, '_folder_screen') or getattr(frame, 'folder_detail', False))):
                root = app.routes.roots['files'].children[0]
                project_apple_heading(app, root, destination, adapter.content_controller(destination),
                                      folder_sidebar=True)
        return
    if not hasattr(view, '_destination_actions'):
        return
    navigation = adapter.navigation_for(destination)
    controller = navigation if preparing_return else adapter.content_controller(destination)
    show = project_apple_heading(app, view, destination, controller)
    if bool(navigation.isNavigationBarHidden()) == show:
        navigation.setNavigationBarHidden(not show, animated=preparing_return)
    reserve_bar_clearance(navigation)


def compact_content_top(container):
    """Apply the measured top strip only to a root header using that strip."""
    if container.content is None:
        return False
    # The native container mounts the tab body, which wraps the route root.
    # The header is the first child along that chain. Match this container's
    # live content so a pushed page never inherits the overview's top inset.
    header = container.content.interface
    while not getattr(header, '_destination_top_band', False):
        children = getattr(header, 'children', ())
        if not children:
            return False
        header = children[0]
    native = container.native
    window = native.window
    window = window() if callable(window) else window
    if window is None:
        return False
    origin = native.convertRect(native.bounds, toView=window).origin
    top = max(0, -float(origin.y))
    changed = abs(container.top_inset - top) > .5
    container.top_inset = top
    return changed
