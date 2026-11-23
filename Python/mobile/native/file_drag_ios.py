"""Keep the UIKit drag session on the browser while folder contents change."""

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from weakref import ref

from rubicon.objc import CGPoint, ObjCClass, ObjCProtocol, SEL, objc_method, objc_property

from commonUtils.ui.native.keyboard import native_value

TILE_MENU_DELAY = .28


def contains(view, gesture):
    if view is None or native_value(view.window) is None:
        return False
    return bool(view.pointInside(gesture.locationInView(view), withEvent=None))


def flash_view(view):
    if view is None:
        return lambda active: None
    from ..appearance import apple_color
    original = native_value(view.backgroundColor)
    highlight = apple_color('hover')

    def flash(active):
        view.backgroundColor = highlight if active else original
    return flash


def browser_item(drag, gesture, *, lifting=False):
    browser = drag.browser()
    if browser is None or browser.closed:
        return None, None
    if browser.mode == 'List':
        table = browser.native_list._impl.native
        if browser.native_list.updating or not contains(table, gesture):
            return None, None
        index_path = table.indexPathForRowAtPoint(gesture.locationInView(table))
        if index_path is None:
            return None, None
        rows = browser.native_list.data
        index = int(native_value(index_path.row))
        if not 0 <= index < len(rows) or rows[index].epoch != browser.epoch:
            return None, None
        cell = table.cellForRowAtIndexPath(index_path)
        if cell is None or lifting and contains(native_value(cell.accessoryView), gesture):
            return None, None
        return rows[index].entry, native_value(cell.contentView)

    if contains(browser._tile_scroll._impl.native, gesture):
        for entry, card, *_ in browser._tile_cards.values():
            view = card._impl.native
            if contains(view, gesture):
                return entry, view
    return None, None


def move_preview(preview, gesture):
    point = gesture.locationInView(native_value(preview.superview))
    preview.center = CGPoint(point.x, point.y - preview.bounds.size.height / 2 - 12)


def cancel_menu_timer(delegate):
    if delegate.menu_timer is not None:
        delegate.menu_timer.cancel()
        delegate.menu_timer = None


def open_tile_menu(delegate):
    cancel_menu_timer(delegate)
    press, delegate.tile_press = delegate.tile_press, None
    drag = delegate.owner()
    if press is None or drag is None:
        return
    drag.end(delegate.token)
    delegate.token = None
    entry, epoch, _, _ = press
    browser = drag.browser()
    if browser is not None and browser.can_show_tile_actions and browser.epoch == epoch:
        browser._loop.create_task(browser._tile_actions(entry))


class BrowserFileDrag(ObjCClass('NSObject'), protocols=(ObjCProtocol('UIGestureRecognizerDelegate'),)):
    owner = objc_property(object)
    token = objc_property(object)
    preview = objc_property(object)
    tile_press = objc_property(object)
    menu_timer = objc_property(object)

    @objc_method
    def gestureRecognizer_shouldReceiveTouch_(self, gesture, touch) -> bool:
        drag = self.owner()
        if drag is None:
            return False
        browser = drag.browser()
        if browser is None or not (browser.can_show_tile_actions or drag.context() is not None):
            return False
        listing = browser.native_list if browser.mode == 'List' else browser._tile_scroll
        view = native_value(touch.view)
        return view is not None and bool(view.isDescendantOfView(listing._impl.native))

    @objc_method
    def gestureRecognizerShouldBegin_(self, gesture) -> bool:
        drag = self.owner()
        browser = drag.browser() if drag is not None else None
        if browser is None or not (browser.can_show_tile_actions or drag.context() is not None):
            return False
        entry, _ = browser_item(drag, gesture, lifting=True)
        return entry is not None

    @objc_method
    def holdFile_(self, gesture) -> None:
        drag = self.owner()
        if drag is None:
            return
        state = int(native_value(gesture.state))
        window = native_value(gesture.view)
        if state == 1 and window is not None:  # Began
            entry, view = browser_item(drag, gesture, lifting=True)
            browser = drag.browser()
            self.token = drag.begin(entry)
            self.tile_press = None
            if browser is not None and browser.can_show_tile_actions and entry is not None:
                point = gesture.locationInView(window)
                self.tile_press = (entry, browser.epoch, float(point.x), float(point.y))
                delay = TILE_MENU_DELAY if self.token is not None else 0
                self.menu_timer = browser._loop.call_later(delay, open_tile_menu, self)
            elif self.token is not None:
                lift_preview(self, view, window, gesture)
        elif state == 2 and window is not None:  # Changed
            if self.tile_press is not None:
                entry, _, x, y = self.tile_press
                point = gesture.locationInView(window)
                if (float(point.x) - x) ** 2 + (float(point.y) - y) ** 2 < 10 ** 2:
                    return
                cancel_menu_timer(self)
                self.tile_press = None
                browser = drag.browser()
                card = browser._tile_cards.get(entry.identity) if browser is not None else None
                if self.token is not None and card is not None:
                    lift_preview(self, card[1]._impl.native, window, gesture)
            if self.token is None:
                return
            if self.preview is not None:
                move_preview(self.preview, gesture)
            point = gesture.locationInView(window)
            coordinates = float(point.x), float(point.y)
            entry, view = browser_item(drag, gesture)
            target = drag.target_entry(entry, coordinates)
            if target is not drag.hover_entry:
                drag.hover(self.token, target, flash_view(view if target is not None else None), coordinates)
            else:
                drag.hover_point = coordinates
        elif state in (3, 4, 5):  # Ended, cancelled, or failed
            cancel_menu_timer(self)
            if state == 3 and self.tile_press is not None:
                open_tile_menu(self)
                return
            token = self.token
            self.token = self.tile_press = None
            if self.preview is not None:
                self.preview.removeFromSuperview()
                self.preview = None
            browser = drag.browser()
            if token is None:
                return
            if state == 3 and window is not None and browser is not None and contains(browser.widget._impl.native, gesture):
                point = gesture.locationInView(window)
                entry, _ = browser_item(drag, gesture)
                target = drag.target_entry(entry, (float(point.x), float(point.y)))
                drag.finish(token, target)
            else:
                drag.end(token)



def lift_preview(delegate, view, window, gesture):
    if view is None:
        return
    preview = view.snapshotViewAfterScreenUpdates(False)
    if preview is not None:
        preview.userInteractionEnabled = False
        preview.accessibilityElementsHidden = True
        preview.alpha = .85
        preview.layer.cornerRadius = 8
        preview.layer.masksToBounds = True
        window.addSubview(preview)
        delegate.preview = preview
        move_preview(preview, gesture)

class TileAccessibilityAction(ObjCClass('NSObject')):
    browser = objc_property(object)
    entry = objc_property(object)

    @objc_method
    def openTileActions_(self, action) -> bool:
        browser = self.browser()
        if browser is None or not browser.can_show_tile_actions:
            return False
        browser._loop.create_task(browser._tile_actions(self.entry))
        return True


def attach_accessibility_action(browser, view, entry):
    target = TileAccessibilityAction.alloc().init()
    target.browser, target.entry = ref(browser), entry
    action = ObjCClass('UIAccessibilityCustomAction').alloc().initWithName(
        'File actions', target=target, selector=SEL('openTileActions:'))
    view.accessibilityCustomActions = [action]
    return target


def install(owner, browser):
    from ..file_drag import FileDrag
    browser.file_drag = model = FileDrag(owner, browser)
    delegate = BrowserFileDrag.alloc().init()
    delegate.owner = ref(model)
    delegate.token = delegate.preview = delegate.tile_press = delegate.menu_timer = None
    gesture = ObjCClass('UILongPressGestureRecognizer').alloc().initWithTarget(delegate, action=SEL('holdFile:'))
    gesture.delegate = delegate
    gesture.minimumPressDuration = .45
    # An empty folder replaces the list or tiles. The gesture stays on their
    # shared parent so it can continue across that replacement.
    # The native list's controller mounts its table separately from the Box.
    # The window is their common ancestor. The touch delegate scopes the
    # recognizer to the active listing and ignores other controls and screens.
    native = owner.main_window._impl.native
    native.addGestureRecognizer(gesture)
    browser.native_list._impl.native.dragInteractionEnabled = False
    browser._file_drag_delegate = native, delegate, gesture


def uninstall(browser):
    native, delegate, gesture = browser._file_drag_delegate
    gesture.enabled = False
    native.removeGestureRecognizer(gesture)
    gesture.delegate = None
    cancel_menu_timer(delegate)
    if delegate.preview is not None:
        delegate.preview.removeFromSuperview()
    browser.file_drag.end(delegate.token)
    browser._file_drag_delegate = None
