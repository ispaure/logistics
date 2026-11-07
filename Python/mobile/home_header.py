"""Place retained Home commands using live iOS geometry."""


def restore(view):
    state = getattr(view, '_home_top_band', None)
    if state is None:
        return
    for button, height in state['heights']:
        button.style.height = height
    row = state['row']
    row.style.margin_left, row.style.margin_right, row.style.margin_bottom = state['margins']
    unlock = state['unlock']
    if unlock.parent is row:
        row.remove(unlock)
    view._home_top_band = None


def place_unlock(row, unlock, visible):
    if visible and unlock.parent is not row:
        if unlock.parent is not None:
            unlock.parent.remove(unlock)
        unlock.style.margin_left = 8
        row.add(unlock)
    elif not visible and unlock.parent is row:
        row.remove(unlock)


def use_document_menu(app, view):
    if getattr(view, '_home_document_menu', None) is not None:
        return
    restore(view)
    row = view._home_primary_actions
    from .action_menu import NativeMenu
    from .control_icons import icon_button
    more = icon_button('overflow', 'Document actions')
    more._toolbar_priority = True
    def invoke(callback):
        if app.active_host and app.native_host.state.destination == 'home':
            callback()
    more._home_commands = NativeMenu(more,
        [(button.text, button.on_press) for button in view._home_primary_buttons],
        invoke=invoke, context=lambda: app._impl.native, fallback=lambda: None)
    view._home_document_menu = more
    row.parent.remove(row)


def sync(app, view):
    row = getattr(view, '_home_primary_actions', None)
    if row is None:
        return False
    from .fold_layout import division, has_fold
    if getattr(view, '_home_document_menu', None) is not None or has_fold(app, app.main_window):
        use_document_menu(app, view)
        place_unlock(row, view._destination_actions[1][0], False)
        view._home_inline_unlock = False
        return False
    from .ios_toolbar import vertical_edge, system_occlusions
    controller = app.native_host.adapter.content_controller('home')
    primary = view._home_primary_buttons
    unlock = view._destination_actions[1][0]
    if vertical_edge(controller):
        restore(view)
        place_unlock(row, unlock, False)
        view._home_inline_unlock = False
        # The shared toolbar renderer detaches and projects the original controls.
        return False
    for index, button in enumerate(primary):
        if button.parent is not row:
            row.insert(index, button)
    native, window = controller.view, app.main_window._impl.native
    origin = native.convertRect(native.bounds, toView=window).origin
    split = division(app, view) is not None or getattr(getattr(view, '_home_sections', None), 'paired', False)
    wants_unlock = bool(app.home_unlock_candidates())
    buttons = [*primary, *([unlock] if wants_unlock else [])]
    from rubicon.objc import CGSize
    sizes = [button._impl.native.sizeThatFits(CGSize(10000, 10000)) for button in buttons]
    height = max(48, *(float(size.height) for size in sizes))
    required = sum(max(48, float(size.width)) for size in sizes) + 8 * len(buttons) + 32
    from .reader_top_band import free_top_band
    width = float(native.bounds.size.width)
    geometry = None
    if not split and abs(float(origin.y)) <= .5:
        geometry = free_top_band(system_occlusions(controller), width, float(window.safeAreaInsets.top),
                                 required, row_height=height + 16)
    if geometry is None:
        restore(view)
        # Use the normal safe-area layout below the system region when the
        # single pane can fit the actual localized labels and credential icon.
        insets = getattr(native, 'safeAreaInsets', None)
        inline = (wants_unlock and not split and insets is not None
                  and required <= width - float(insets.left) - float(insets.right)
                  and height <= 48)
        place_unlock(row, unlock, inline)
        view._home_inline_unlock = inline
        return inline
    view._home_inline_unlock = False
    state = getattr(view, '_home_top_band', None)
    if state is None:
        state = view._home_top_band = dict(row=row, unlock=unlock,
            heights=[(button, button.style.height) for button in primary],
            margins=(row.style.margin_left, row.style.margin_right, row.style.margin_bottom))
    changed = state.get('geometry') != geometry
    state['geometry'] = geometry
    for button in primary:
        button.style.height = height
    place_unlock(row, unlock, wants_unlock)
    row.style.margin_left = geometry['left']
    row.style.margin_right = width - geometry['right']
    row.style.margin_bottom = max(8, geometry['reserve'] - height - 8)
    container = getattr(view._impl, 'container', None)
    if changed and container is not None:
        app.native_host.adapter.layout_content(container)
    return True


def compact_content_top(container):
    if container.content is None:
        return False
    def projected(widget, *attributes):
        return any(getattr(widget, name, None) for name in attributes) or any(
            projected(child, *attributes) for child in getattr(widget, 'children', ()))

    root = container.content.interface
    if projected(root, '_home_inline_unlock'):
        from .ios_reader_chrome import occlusion_geometry
        from .ios_system_occlusions import control_top_clearance
        native = container.native
        top = control_top_clearance(occlusion_geometry(native), container.left_inset,
                                    float(native.bounds.size.width) - container.right_inset,
                                    container.top_inset, target=48)
        changed = abs(container.top_inset - top) > .5
        container.top_inset = top
        return changed
    if not projected(root, '_home_top_band', '_destination_top_band'):
        return False
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
