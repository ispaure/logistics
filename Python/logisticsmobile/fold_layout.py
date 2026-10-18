"""Window-local hinge observation and vertical seam coordinates (iOS 27.1+)."""
import weakref


def install(app):
    if not type(app.main_window._impl).__module__.startswith('toga_iOS.'):
        return
    from rubicon.objc import ObjCClass, ObjCInstance, Block, objc_id
    try:
        interaction = ObjCClass('UIHingeInteraction')
    except NameError:  # Older supported iOS releases have no hinge interaction.
        return
    owner = weakref.ref(app)

    def update(interaction, value):
        host = owner()
        if host is None:
            return
        hinge = ObjCInstance(value).hinge
        status = int(hinge.status) if hinge is not None else 0
        if status != getattr(host, '_hinge_status', 0):
            host._hinge_status = status
            host.loop.call_soon(host.resize_workspace)

    app._hinge_handler = Block(update, None, objc_id, objc_id)
    app._hinge_interaction = interaction.alloc().initWithUpdateHandler(app._hinge_handler)
    app.main_window._impl.native.addInteraction(app._hinge_interaction)


def seam_fraction(owner, widget, *, include_open=False):
    """Return the physical vertical seam in widget coordinates, or None.

    Safe areas and the side rail can make the widget's midpoint asymmetric.
    Horizontal hinges (rotated windows) do not define side-by-side panes.
    Workspaces also aligns its panes when the hinge reports fully open.
    """
    app = getattr(owner, 'app', owner)
    if getattr(app, '_hinge_status', 0) not in ((2, 3) if include_open else (2,)):
        return None
    window = app.main_window._impl.native
    if int(window.windowScene.interfaceOrientation) not in (3, 4):
        return None
    native = widget._impl.native
    rect = native.convertRect(native.bounds, toView=window)
    if rect.size.width <= 0:
        return None
    fraction = (window.bounds.size.width / 2 - rect.origin.x) / rect.size.width
    return float(fraction) if 0 < fraction < 1 else None


def comic_mode(owner, widget):
    return 'double' if seam_fraction(owner, widget) is not None else owner.preferences.values['comic_layout']
