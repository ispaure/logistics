"""Window-local fold geometry from UIKit reserved regions (iOS 27.1+)."""
from dataclasses import dataclass
import weakref


@dataclass(frozen=True)
class Division:
    """An active fold and its included interaction margins, in local points."""
    x: float
    y: float
    width: float
    height: float

    @property
    def vertical(self):
        return self.height > self.width

    def spans(self, width, height):
        # Ignore regions that do not divide this particular container.
        return (self.y <= 1 and self.y + self.height >= height - 1 if self.vertical
                else self.x <= 1 and self.x + self.width >= width - 1)


def reserved_divisions(widget, *, include_inactive=False):
    """Query in the view's own coordinates; older platforms return no regions."""
    if not type(widget._impl).__module__.startswith('toga_iOS.'):
        return ()
    native = widget._impl.native
    if not hasattr(native, 'reservedRegionsOfKind'):
        return ()
    from rubicon.objc import ObjCClass
    kind = ObjCClass('UIViewReservedRegionKind').divisionRegionKind()
    regions = native.reservedRegionsOfKind(kind, options=int(include_inactive))
    return tuple(Division(float(r.frame.origin.x), float(r.frame.origin.y),
                          float(r.frame.size.width), float(r.frame.size.height))
                 for r in regions)


def division(owner, widget, *, include_inactive=False):
    """The active fold dividing a container, independent of device orientation."""
    for region in reserved_divisions(widget, include_inactive=include_inactive):
        bounds = widget._impl.native.bounds.size
        if region.spans(float(bounds.width), float(bounds.height)):
            return region
    return None


def has_fold(owner, widget):
    app = getattr(owner, 'app', owner)
    return bool(getattr(app, '_hinge_status', 0) or
                reserved_divisions(widget, include_inactive=True))


def install(app):
    if not type(app.main_window._impl).__module__.startswith('toga_iOS.'):
        return
    from rubicon.objc import ObjCClass, ObjCInstance, Block, objc_id
    try:
        interaction = ObjCClass('UIHingeInteraction')
    except NameError:
        return
    owner = weakref.ref(app)

    def refresh():
        host = owner()
        if host is not None:
            host._fold_refresh_pending = False
            host.resize_workspace()

    def update(interaction, value):
        host = owner()
        if host is None:
            return
        hinge = ObjCInstance(value).hinge
        host._hinge_status = int(hinge.status) if hinge is not None else 0
        # Geometry can change without a status transition. Coalesce callbacks;
        # consumers use actual reserved regions, never hinge angle or a midpoint.
        if not getattr(host, '_fold_refresh_pending', False):
            host._fold_refresh_pending = True
            host.loop.call_soon(refresh)

    app._hinge_handler = Block(update, None, objc_id, objc_id)
    app._hinge_interaction = interaction.alloc().initWithUpdateHandler(app._hinge_handler)
    app.main_window._impl.native.addInteraction(app._hinge_interaction)


def seam_fraction(owner, widget, *, include_open=False):
    """Compatibility center of an active vertical division, in view coordinates.

    An inactive flat fold never overrides a preferred pane ratio. include_open
    remains accepted for callers written before reserved regions were available.
    """
    region = division(owner, widget)
    if region is None or not region.vertical:
        return None
    width = float(widget._impl.native.bounds.size.width)
    fraction = (region.x + region.width / 2) / width if width > 0 else 0
    return fraction if 0 < fraction < 1 else None


def seam_gap(owner, widget):
    region = division(owner, widget)
    return region.width if region is not None and region.vertical else 0


def comic_mode(owner, widget):
    return 'double' if seam_fraction(owner, widget) is not None else owner.preferences.values['comic_layout']


def reading_seam(owner, widget):
    """Keep the reading anchor on the same physical side even when flat."""
    region = division(owner, widget, include_inactive=True)
    if region is None or not region.vertical:
        return None
    width = float(widget._impl.native.bounds.size.width)
    center = region.x + region.width / 2
    return center / width if 0 < center < width else None
