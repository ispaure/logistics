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
        width, height = float(bounds.width), float(bounds.height)
        start, end, extent = ((region.x, region.x + region.width, width) if region.vertical
                              else (region.y, region.y + region.height, height))
        if region.spans(width, height) and 0 < start <= end < extent:
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
            native = host.main_window._impl.native
            bounds, safe = native.bounds.size, native.safeAreaInsets
            signature = (getattr(host, '_hinge_status', 0),
                         float(bounds.width), float(bounds.height),
                         float(safe.left), float(safe.right), float(safe.top), float(safe.bottom),
                         reserved_divisions(host.main_window),
                         reserved_divisions(host.main_window, include_inactive=True))
            if signature != getattr(host, '_fold_geometry', None):
                host._fold_geometry = signature
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
    """Reserve an active crease; flat readers fit their whole available pane."""
    return seam_fraction(owner, widget)


def page_region(owner, widget):
    """A discrete page sits above an active horizontal fold; controls stay below."""
    region = division(owner, widget)
    if region is None or region.vertical:
        return None
    bounds = widget._impl.native.bounds.size
    if 0 < region.y < float(bounds.height):
        return (0, 0, float(bounds.width), region.y)
    return None


def epub_geometry(widget):
    """Normalized active crease in the reading WebView's local coordinates."""
    region = division(None, widget)
    if region is None or not region.vertical:
        return None
    width = float(widget._impl.native.bounds.size.width)
    return dict(seam=(region.x + region.width / 2) / width, gap=region.width / width)


def bind_epub_geometry(widget):
    bridge = widget._chapter_bridge
    bridge.geometry_provider = lambda: epub_geometry(widget)
    bridge.refresh_geometry(force=True)


def sync_epub_geometry(app):
    """Hinge callbacks also reflow retained EPUBs without a viewport resize."""
    for name in ('readers', 'private_sessions'):
        manager = getattr(app, name, None)
        for owner in getattr(manager, 'controllers', {}).values():
            panel = getattr(owner, 'provider_epub_view', None)
            widget = getattr(owner, 'epub_view', None) or getattr(panel, 'webview', None)
            bridge = getattr(widget, '_chapter_bridge', None)
            if bridge is not None:
                bridge.refresh_geometry()
