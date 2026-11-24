"""A leading destination rail for iPhones without a native vertical tab bar."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from weakref import ref

from .ios_toolbar import vertical_edge

RAIL_WIDTH = 56
ITEM_SIZE = 44
ITEM_GAP = 4


def uses_leading_rail(*, phone, duo, landscape, native_edge):
    return phone and not duo and landscape and not native_edge


def clear_landscape_gutters(width, left, right, sensor_x, regions):
    """Return the mirrored safe-area margin that has no hardware or system UI."""
    if not left or not right or abs(left - right) > 1:
        return 0, 0
    if sensor_x <= left and not any(x + w > width - right for x, _, w, _ in regions):
        return 0, right
    if sensor_x >= width - right and not any(x < left for x, _, _, _ in regions):
        return left, 0
    return 0, 0


class DestinationRail:
    def __init__(self, host):
        from rubicon.objc import Block, ObjCClass, objc_id

        self.host = host
        self.adapter = host.adapter
        self.parent = self.adapter.controller.view
        self.left_inset = self.adapter.controller.additionalSafeAreaInsets.left
        self.active = False
        self.state = None
        self.clear_gutters = (0, 0)
        self.native_set_hidden = self.adapter.set_keyboard_tabs_hidden
        self.adapter.set_keyboard_tabs_hidden = self.set_tabs_hidden
        self.view = ObjCClass('UIView').alloc().init()
        self.view.setHidden(True)
        self.view.clipsToBounds = True
        self.parent.addSubview(self.view)
        self.buttons = []
        reference = ref(self)
        for destination, label in zip(host.destinations, host.labels):
            def select(_, key=destination):
                owner = reference()
                if owner is not None:
                    owner.host.window.app.loop.call_soon(owner.select, key)
            handler = Block(select, None, objc_id)
            action = ObjCClass('UIAction').actionWithHandler(handler)
            button = ObjCClass('UIButton').buttonWithType(1)
            button.addAction(action, forControlEvents=1 << 13)  # primary action
            button.accessibilityLabel = label
            button.accessibilityIdentifier = 'destination-' + destination
            button.layer.cornerRadius = 14
            self.view.addSubview(button)
            self.buttons.append((button, handler))

    def close(self):
        controller = self.adapter.controller
        self.active = False
        self.adapter.set_keyboard_tabs_hidden = self.native_set_hidden
        insets = controller.additionalSafeAreaInsets
        insets.left = self.left_inset
        controller.additionalSafeAreaInsets = insets
        self.view.removeFromSuperview()

    def select(self, destination):
        app = self.host.window.app
        if self.active and app.active_host:
            app.routes.return_to(destination)
            self.layout()
            app.resize_workspace()

    def set_tabs_hidden(self, modern, hidden):
        self.native_set_hidden(modern, hidden or self.active)
        if self.active:
            self.layout()

    def hardware_gutters(self, window):
        from rubicon.objc import CGPoint
        from .ios_reader_chrome import occlusion_geometry

        # The screen's fixed coordinate space is portrait. Project its top
        # edge into the window to locate the sensor after either rotation.
        fixed = window.screen.fixedCoordinateSpace
        origin, size = fixed.bounds.origin, fixed.bounds.size
        point = window.convertPoint(CGPoint(origin.x + size.width / 2, origin.y),
                                    fromCoordinateSpace=fixed)
        safe = window.safeAreaInsets
        return clear_landscape_gutters(float(window.bounds.size.width), float(safe.left),
                                       float(safe.right), float(point.x), occlusion_geometry(window))

    def content_insets(self, native):
        """Release only UIKit's mirrored margin; keep the rail and local insets."""
        safe = native.safeAreaInsets
        left, right = self.clear_gutters
        if left or right:
            window = self.host.window._impl.native
            frame = native.convertRect(native.bounds, toView=window)
            left = max(0, left - max(0, float(frame.origin.x)))
            right = max(0, right - max(0, float(window.bounds.size.width
                                               - frame.origin.x - frame.size.width)))
        return max(0, float(safe.left) - left), max(0, float(safe.right) - right)

    def layout(self):
        from rubicon.objc import CGRect, ObjCClass, SEL
        from .appearance import apple_color
        from .fold_layout import is_iphone_duo

        controller = self.adapter.controller
        if self.host.adapter is not self.adapter:
            return
        bounds = self.parent.bounds.size
        if min(bounds.width, bounds.height) <= 0 or self.parent.window is None:
            return
        active = uses_leading_rail(phone=int(ObjCClass('UIDevice').currentDevice.userInterfaceIdiom) == 0,
            duo=is_iphone_duo(), landscape=bounds.width > bounds.height, native_edge=vertical_edge(controller))
        app = self.host.window.app
        hidden = (getattr(app, '_document_tabs_hidden', False)
                  or (self.adapter.keyboard_visible and self.host.chrome.context is None))
        visible = active and not hidden
        # This view already inherits the additional rail inset. Subtract that
        # contribution to position the rail beside the hardware safe area.
        own_inset = float(controller.additionalSafeAreaInsets.left - self.left_inset)
        safe = self.parent.safeAreaInsets
        gutters = self.hardware_gutters(self.host.window._impl.native) if active else (0, 0)
        left = max(0, float(safe.left) - own_inset - gutters[0])
        visible_items = tuple(self.host.root.content[i].enabled for i in range(len(self.buttons)))
        selected = self.host.state.destination
        signature = (active, visible, left, gutters, float(safe.top), float(safe.bottom), bounds.height,
                     visible_items, selected, int(self.parent.traitCollection.userInterfaceStyle))
        if signature == self.state:
            return
        self.state = signature
        changed_axis, self.active = active != self.active, active
        gutter_changed = gutters != self.clear_gutters
        self.clear_gutters = gutters
        self.view.setHidden(not visible)
        inset = RAIL_WIDTH if visible else 0
        if own_inset != inset:
            insets = controller.additionalSafeAreaInsets
            insets.left = self.left_inset + inset
            controller.additionalSafeAreaInsets = insets
        if changed_axis:
            modern = bool(controller.respondsToSelector(SEL('setTabBarHidden:animated:')))
            self.native_set_hidden(modern, active or hidden)
        if gutter_changed:
            app.loop.call_soon(self.reflow_content)
        if not visible:
            return
        self.view.frame = CGRect((left, safe.top), (RAIL_WIDTH, bounds.height - safe.top - safe.bottom))
        self.view.backgroundColor = apple_color('surface')
        self.parent.bringSubviewToFront(self.view)
        y = 4
        for index, ((button, _), enabled) in enumerate(zip(self.buttons, visible_items)):
            button.setHidden(not enabled)
            if not enabled:
                continue
            current = self.host.destinations[index] == selected
            item = self.host.root.content[index]
            button.setImage(item.icon._impl.native, forState=0)
            button.tintColor = apple_color('accent' if current else 'text')
            button.backgroundColor = apple_color('hover' if current else 'surface')
            button.accessibilityTraits = 1 | (4 if current else 0)
            if self.host.destinations[index] == 'settings':
                y = max(y, self.view.bounds.size.height - ITEM_SIZE - 4)
            button.frame = CGRect(((RAIL_WIDTH - ITEM_SIZE) / 2, y), (ITEM_SIZE, ITEM_SIZE))
            y += ITEM_SIZE + ITEM_GAP

    def reflow_content(self):
        if self.host.adapter is self.adapter:
            app = self.host.window.app
            if not app.active_host:
                return
            for child in app.routes.body().children:
                container = getattr(child._impl, 'container', None)
                if container is not None:
                    self.adapter.layout_content(container)
            app.adaptive.render()
