"""Android drag and hold gestures for the in-app File Browser."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from weakref import ref

from android.content import ClipData
from android.graphics import Rect
from android.view import DragEvent, MotionEvent, View
from android.widget import AdapterView
from java import dynamic_proxy, jarray, jint

from ..file_drag import FileDrag

TILE_MENU_DELAY = .28


def screen_origin(view):
    point = jarray(jint)(2)
    view.getLocationOnScreen(point)
    return point[0], point[1]


def hit(view, x, y):
    bounds = Rect()
    return view.getGlobalVisibleRect(bounds) and bounds.contains(int(x), int(y))


def item_at(browser, x, y):
    if browser.mode == 'List':
        listing = browser.native_list
        native = listing._impl.native
        if listing.updating or not hit(native, x, y):
            return None, None
        left, top = screen_origin(native)
        index = native.pointToPosition(int(x - left), int(y - top))
        rows = listing.data
        if 0 <= index < len(rows) and rows[index].epoch == browser.epoch:
            return rows[index].entry, native.getChildAt(index - native.getFirstVisiblePosition())
    else:
        for entry, card, *_ in browser._tile_cards.values():
            view = card._impl.native
            if hit(view, x, y):
                return entry, view
    return None, None


def highlight(view):
    alpha = view.getAlpha() if view is not None else 1.0

    def update(active):
        if view is not None:
            view.setAlpha(alpha * .65 if active else alpha)
    return update


def lift(drag, token, native):
    clip = ClipData.newPlainText(token, '')
    started = native.startDragAndDrop(clip, View.DragShadowBuilder(native), None, 0)
    if not started:
        drag.end(token)
    return bool(started)


def install(owner, browser):
    drag = browser.file_drag = FileDrag(owner, browser)
    browser_ref = ref(browser)
    listing = browser.native_list._impl.native
    root = browser.widget._impl.native

    class Start(dynamic_proxy(AdapterView.OnItemLongClickListener)):
        def onItemLongClick(self, parent, native, position, identifier):
            browser = browser_ref()
            if browser is None or browser.mode != 'List' or browser.on_check_entry is not None:
                return False
            rows = browser.native_list.data
            if not 0 <= position < len(rows) or rows[position].epoch != browser.epoch:
                return False
            row = rows[position]
            token = drag.begin(row.entry)
            if token is not None:
                return lift(drag, token, native)
            if browser.on_item_actions is None:
                return False
            browser.native_list.on_primary_action(row=row)
            return True

    class Drop(dynamic_proxy(View.OnDragListener)):
        def __init__(self):
            super().__init__()
            self.token = None
            self.dropped = False

        def onDrag(self, native, event):
            action = event.getAction()
            if action == DragEvent.ACTION_DRAG_STARTED:
                description = event.getClipDescription()
                source = drag.source
                if source is None or description is None or str(description.getLabel()) != source.token:
                    return False
                self.token = source.token
                self.dropped = False
                return True
            token = self.token
            if token is None:
                return False
            if action == DragEvent.ACTION_DRAG_ENDED:
                if not self.dropped:
                    drag.end(token)
                self.token = None
                return True
            browser = browser_ref()
            if browser is None or browser.closed:
                return False
            if action in (DragEvent.ACTION_DRAG_LOCATION, DragEvent.ACTION_DROP):
                left, top = screen_origin(native)
                point = left + float(event.getX()), top + float(event.getY())
                entry, view = item_at(browser, *point)
                target = drag.target_entry(entry, point)
                if action == DragEvent.ACTION_DROP:
                    self.dropped = True
                    drag.finish(token, target)
                elif target is not drag.hover_entry:
                    drag.hover(token, target, highlight(view if target is not None else None), point)
                else:
                    drag.hover_point = point
            elif action == DragEvent.ACTION_DRAG_EXITED:
                drag.clear_hover()
            return True

    start, drop = Start(), Drop()
    listing.setOnItemLongClickListener(start)
    root.setOnDragListener(drop)
    browser._android_file_drag = listing, root, start, drop


def uninstall(browser):
    listing, root, _, drop = browser._android_file_drag
    listing.setOnItemLongClickListener(None)
    root.setOnDragListener(None)
    drag = browser.file_drag
    if drag.source is not None:
        drag.end(drag.source.token)
    drop.token = None
    browser._android_file_drag = None


def attach_tile_hold(browser, native, entry):
    browser_ref, epoch = ref(browser), browser.epoch
    drag = getattr(browser, 'file_drag', None)
    slop = native.getResources().getDisplayMetrics().density * 10
    point = None
    token = timer = None

    def retire():
        nonlocal timer, token
        if timer is not None:
            timer.cancel()
            timer = None
            parent = native.getParent()
            if parent is not None:
                parent.requestDisallowInterceptTouchEvent(False)
        if token is not None:
            drag.end(token)
            token = None

    def open_menu():
        retire()
        browser = browser_ref()
        if browser is not None and browser.can_show_tile_actions and browser.epoch == epoch:
            browser._loop.create_task(browser._tile_actions(entry))

    class Hold(dynamic_proxy(View.OnLongClickListener)):
        def onLongClick(self, view):
            nonlocal token, timer
            browser = browser_ref()
            if browser is None or not browser.can_show_tile_actions or browser.epoch != epoch:
                return False
            if drag is not None and point is not None:
                token = drag.begin(entry)
            if token is None:
                open_menu()
            else:
                parent = view.getParent()
                if parent is not None:
                    parent.requestDisallowInterceptTouchEvent(True)
                timer = browser._loop.call_later(TILE_MENU_DELAY, open_menu)
            return True

    class Touch(dynamic_proxy(View.OnTouchListener)):
        def onTouch(self, view, event):
            nonlocal point, token
            action = event.getActionMasked()
            if action == MotionEvent.ACTION_DOWN:
                point = float(event.getRawX()), float(event.getRawY())
            elif token is not None and action == MotionEvent.ACTION_MOVE:
                dx = float(event.getRawX()) - point[0]
                dy = float(event.getRawY()) - point[1]
                if dx * dx + dy * dy >= slop * slop:
                    armed, token = token, None
                    retire()
                    return lift(drag, armed, view)
            elif action == MotionEvent.ACTION_UP:
                if token is not None:
                    open_menu()
                point = None
            elif action == MotionEvent.ACTION_CANCEL:
                retire()
                point = None
            return False

    hold, touch = Hold(), Touch()
    native.setOnLongClickListener(hold)
    native.setOnTouchListener(touch)
    return hold, touch, retire
