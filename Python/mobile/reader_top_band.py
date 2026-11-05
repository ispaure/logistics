"""Project retained native reader chrome beside a measured edge status cluster."""
import weakref


def free_top_band(regions, width, safe_top, required_width, *, row_height=60):
    """Choose only a wide edge column; missing/central/full-width data declines."""
    if safe_top < row_height or required_width <= 0 or width <= 0:
        return None
    top = [(x, y, w, h) for x, y, w, h in regions
           if w > 0 and h > 0 and y <= safe_top and y + h > 0]
    if not top or any(x > 0 and x + w < width for x, y, w, h in top):
        return None
    intervals = [(0., float(width))]
    for x, y, w, h in top:
        if y >= row_height:
            continue
        updated = []
        for left, right in intervals:
            if x >= right or x + w <= left:
                updated.append((left, right))
            else:
                if left < x:
                    updated.append((left, min(right, x)))
                if x + w < right:
                    updated.append((max(left, x + w), right))
        intervals = updated
    choices = [(left, right) for left, right in intervals
               if (left == 0 or right == width) and right - left >= required_width]
    if not choices:
        return None
    left, right = max(choices, key=lambda pair: pair[1] - pair[0])
    from .ios_system_occlusions import control_top_clearance
    reserve = max(row_height, control_top_clearance(regions, 0, width, 0, target=row_height))
    return dict(left=left, right=right, width=width, row_height=row_height, reserve=reserve)


def restore(view):
    state = getattr(view, '_reader_top_band_state', None)
    if state is None:
        return
    owner = state['owner_app']()
    projections = getattr(owner, '_reader_toolbar_projections', None) if owner is not None else None
    if projections is not None:
        projections.pop(state['controller_key'], None)
        projections.pop((state['controller_key'], 'leading'), None)
    header = state['header']
    if header.parent is not None:
        header.parent.remove(header)
    for button in state['buttons']:
        if button.parent is not None:
            button.parent.remove(button)
    frame = getattr(view, '_reading_frame_owner', None)
    if frame is not None and header in frame.controls:
        frame.controls.remove(header)
        frame.top_controls -= 1
    view._document_title_header = state['previous_header']
    view._reader_top_band_state = None


def release_other(app, view):
    reference = getattr(app, '_reader_top_band_view', None)
    previous = reference() if reference is not None else None
    if previous is not None and previous is not view:
        restore(previous)
        app._reader_top_band_view = None


def project(app, view, destination, controller):
    """Keep original native targets/menu owners; decline unsupported geometry."""
    from .ios_toolbar import vertical_edge, system_occlusions
    from commonUtils.ui.native.keyboard import native_value
    native = getattr(controller, 'view', None)
    if native is None or not hasattr(native, 'convertRect'):
        restore(view)
        return False
    window = app.main_window._impl.native
    origin = native.convertRect(native.bounds, toView=window).origin
    status = str(getattr(getattr(view, '_native_reader_status', None), 'text', '') or '')
    prompt = status.lower().startswith(('save failed', 'cannot ', 'unsaved changes:',
                                       'book import failed', 'could not '))
    close = getattr(view, '_reader_close_button', None)
    if (vertical_edge(controller) or getattr(view, '_reader_fullscreen', False)
            or getattr(app, '_reader_chrome_hidden', False) or prompt or close is None
            or abs(float(origin.y)) > .5 or not hasattr(view, '_document_storage_status')
            or hasattr(view, '_document_title_controls')):
        restore(view)
        return False
    from .reader_chrome import reader_buttons
    buttons = [close]
    workspace = getattr(view, '_workspace_frame', None)
    menu = workspace.menu if workspace is not None else getattr(view, '_workspace_menu_button', None)
    if menu is not None:
        buttons.append(menu)
    buttons.extend(reader_buttons(app, view))
    # Never collapse/drop commands to make the new row fit.
    if len({id(button) for button in buttons}) != len(buttons):
        restore(view)
        return False
    sizes = [(button.style.width, button.style.height) for button in buttons]
    if any(not isinstance(value, (int, float)) or value < 44
           for size in sizes for value in size):
        restore(view)
        return False
    row_height = max(48, *(height for width, height in sizes)) + 12
    width = float(native.bounds.size.width)
    geometry = free_top_band(system_occlusions(controller), width,
                             float(native_value(window.safeAreaInsets).top),
                             sum(size[0] for size in sizes) + 44 + 32, row_height=row_height)
    if geometry is None:
        restore(view)
        return False
    title = getattr(view, '_native_reader_title', '')
    title = str(title() if callable(title) else title or controller.navigationItem.title or '').replace('\n', ' ')
    margins = tuple(float(getattr(view.style, 'margin_' + side) or 0) for side in ('top', 'right', 'left'))
    signature = (tuple(sorted(geometry.items())), tuple(id(button) for button in buttons), title,
                 str(view._document_storage_status), tuple(view._document_storage_kinds), margins)
    state = getattr(view, '_reader_top_band_state', None)
    if state is not None and state['controller'] == controller and state['signature'] == signature:
        navigation = app.native_host.adapter.navigation_for(destination)
        if not bool(navigation.isNavigationBarHidden()):
            navigation.setNavigationBarHidden(True, animated=False)
        return True
    restore(view)
    toolbar = view._native_reader_toolbar
    for widget in (toolbar, *getattr(view, '_native_reader_hidden', ())):
        if widget.parent is not None:
            widget.parent.remove(widget)
    from .ios_toolbar import clear_actions, mount_leading
    clear_actions(controller.navigationItem)
    mount_leading(controller, [], replaces_back=False)
    from .document_location import mount_apple_title, place_title_in_header
    mount_apple_title(view, controller, title)
    # Release UIKit's title ownership BEFORE reparenting the same native title.
    controller.navigationItem.titleView = None
    previous = getattr(view, '_document_title_header', None)
    if previous is not None and previous.parent is not None:
        previous.parent.remove(previous)
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN, ROW
    title_host = toga.Box(style=Pack(flex=1, height=row_height - 12, margin_left=8, margin_right=8))
    row = toga.Box(style=Pack(direction=ROW, align_items='center', height=row_height - 12,
        margin_top=6, margin_bottom=6, margin_left=geometry['left'] + 8,
        margin_right=width - geometry['right'] + 8))
    # Cancel only the reader widget's existing content padding for this header.
    # Native/window safe-area insets are never made negative or rewritten.
    header = toga.Box(children=[row], style=Pack(direction=COLUMN, height=geometry['reserve'],
        margin_top=-margins[0], margin_right=-margins[1], margin_left=-margins[2]))
    for index, button in enumerate(buttons):
        if button.parent is not None:
            button.parent.remove(button)
        button.app, button.window = app, app.main_window
        row.add(button)
        if index == 0:
            row.add(title_host)
    row._title_content = title_host
    place_title_in_header(row, view._document_title_view, view._document_storage_status)
    row.style.height = row_height - 12  # Title sizing must not clip an existing 52pt menu.
    frame = getattr(view, '_reading_frame_owner', None)
    if frame is not None:
        frame.controls.insert(0, header)
        frame.top_controls += 1
    view.insert(0, header)
    view._document_title_header = header
    pointer = getattr(controller, 'ptr', None)
    controller_key = pointer.value if pointer is not None else id(controller)
    view._reader_top_band_state = dict(header=header, previous_header=previous,
        signature=signature, buttons=buttons, geometry=geometry, controller=controller,
        controller_key=controller_key, owner_app=weakref.ref(app))
    app._reader_top_band_view = weakref.ref(view)
    navigation = app.native_host.adapter.navigation_for(destination)
    if not bool(navigation.isNavigationBarHidden()):
        navigation.setNavigationBarHidden(True, animated=False)
    container = getattr(view._impl, 'container', None)
    if container is not None:
        app.native_host.adapter.layout_content(container)
    return True
