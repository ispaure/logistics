"""Home's retained actions can occupy a measured free edge of the status band."""


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


def sync(app, view):
    row = getattr(view, '_home_primary_actions', None)
    if row is None:
        return False
    from .ios_toolbar import vertical_edge, system_occlusions
    controller = app.native_host.adapter.content_controller('home')
    native, window = controller.view, app.main_window._impl.native
    origin = native.convertRect(native.bounds, toView=window).origin
    from .fold_layout import division
    if vertical_edge(controller) or abs(float(origin.y)) > .5 or division(app, view) is not None:
        restore(view)
        return False
    primary = view._home_primary_buttons
    unlock = view._destination_actions[1][0]
    buttons = [*primary, *([unlock] if app.home_unlock_candidates() else [])]
    from rubicon.objc import CGSize
    sizes = [button._impl.native.sizeThatFits(CGSize(10000, 10000)) for button in buttons]
    height = max(48, *(float(size.height) for size in sizes))
    from .reader_top_band import free_top_band
    width = float(native.bounds.size.width)
    geometry = free_top_band(system_occlusions(controller), width, float(window.safeAreaInsets.top),
        sum(max(48, float(size.width)) for size in sizes) + 8 * len(buttons) + 32,
        row_height=height + 16)
    if geometry is None:
        restore(view)
        return False
    state = getattr(view, '_home_top_band', None)
    if state is None:
        state = view._home_top_band = dict(row=row, unlock=unlock,
            heights=[(button, button.style.height) for button in primary],
            margins=(row.style.margin_left, row.style.margin_right, row.style.margin_bottom))
    changed = state.get('geometry') != geometry
    state['geometry'] = geometry
    for button in primary:
        button.style.height = height
    if unlock in buttons and unlock.parent is not row:
        if unlock.parent is not None:
            unlock.parent.remove(unlock)
        row.add(unlock)
    elif unlock not in buttons and unlock.parent is row:
        row.remove(unlock)
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
    def projected(widget):
        return bool(getattr(widget, '_home_top_band', None) or getattr(widget, '_destination_top_band', None)) or any(
            projected(child) for child in getattr(widget, 'children', ()))
    if not projected(container.content.interface):
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
