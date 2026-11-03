"""Compact Notes Library drawers, with persistent Files on wide allocations."""
from types import SimpleNamespace
import toga
from toga.style import Pack
from toga.style.pack import ROW
from .speech_overlay import SpeechOverlay


class NotesDrawers:
    expanded = False

    def __init__(self, files, article, links, *, app):
        self.app, self.sidebar, self.detail, self.links = app, files, article, links
        self.view = toga.Box(children=[article], style=Pack(direction=ROW, flex=1))
        self.policy = SimpleNamespace(sidebar_width=320, gap=0)
        self.overlay = None
        self.side = None
        self.gestures = []
        self.on_close = lambda: None
        self.on_change = lambda: None
        for panel in (files, links):
            panel.hide = self.show_detail
            panel.overlay = None
            panel.overlay_height = 480

    @property
    def sidebar_open(self):
        return self.side is not None

    def reflow(self, width):
        expanded = width >= 840  # 320 for Files, at least 520 for the document.
        if expanded != self.expanded:
            # Detach a floating Files panel before mounting it in the layout.
            if self.side == 'files':
                self.show_detail()
            self.expanded = expanded
            if expanded:
                self.sidebar.style.flex = 0
                self.view.insert(0, self.sidebar)
            else:
                self.view.remove(self.sidebar)
                self.sidebar.style.flex = 1
        # The host passes the document width minus its 24-unit inset. Leave
        # at least 44 units opposite the drawer for outside dismissal.
        self.policy.sidebar_width = min(320, max(1, width - 32))
        self.sidebar.style.width = max(1, self.policy.sidebar_width - 24)
        self.links.style.width = max(1, self.policy.sidebar_width - 24)
        if self.overlay is not None:
            self.overlay.reposition()

    def toggle(self, widget=None, **kwargs):
        self.show_detail() if self.side == 'files' else self.show_sidebar()

    def show_sidebar(self):
        self.show('files')

    def show_links(self):
        self.show('links')

    def show(self, side):
        if side == 'files' and self.expanded:
            self.show_detail()
            return
        if self.side == side:
            return
        self.show_detail()
        self.side = side
        self.on_change()
        panel = self.sidebar if side == 'files' else self.links
        self.overlay = SpeechOverlay(panel, self.view, self.app, leading=side == 'files',
                                     full_height=True, label='Files' if side == 'files' else 'Links',
                                     dim=True)
        self.overlay.chapter_owner = self.view
        panel.overlay = self.overlay
        self.install_swipe(panel)
        # Animate the native overlay container, not Toga's flattened Box layer.
        if (type(panel._impl).__module__.startswith(('toga_iOS.', 'toga_android.'))
                and self.app.preferences.values.get('android_eink') != 'true'):
            from commonUtils.ui.native.transitions import begin_page_slide, finish_page_slide
            native = (self.overlay.container.native if self.overlay.container is not None
                      and hasattr(self.overlay.container, 'native') else panel._impl.native)
            proxy_impl = type('DrawerImpl', (), {'__module__': type(panel._impl).__module__})()
            proxy_impl.native = native
            proxy = SimpleNamespace(_impl=proxy_impl)
            begin_page_slide(proxy, -1 if side == 'files' else 1)
            finish_page_slide(proxy, -1 if side == 'files' else 1)

    def swipe(self, direction):
        if (self.side == 'files' and direction < 0) or (self.side == 'links' and direction > 0):
            self.show_detail()
            return True
        return False

    def install_swipe(self, panel):
        backend = type(panel._impl).__module__
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, ObjCProtocol, SEL, objc_method
            # An overlay owns its recognizer target; release both on dismissal.
            global _swipe_class
            if _swipe_class is None:
                class LogisticsNotesDrawerSwipe(ObjCClass('NSObject'), protocols=(ObjCProtocol('UIGestureRecognizerDelegate'),)):
                    @objc_method
                    def gestureRecognizer_shouldRecognizeSimultaneouslyWithGestureRecognizer_(self, gesture, other) -> bool:
                        return True

                    @objc_method
                    def swipe_(self, gesture) -> None:
                        if self.owner is not None:
                            self.owner.swipe(1 if int(gesture.direction) == 1 else -1)
                _swipe_class = LogisticsNotesDrawerSwipe
            target = _swipe_class.alloc().init()
            target.owner = self
            native = self.overlay.container.native
            gesture = ObjCClass('UISwipeGestureRecognizer').alloc().initWithTarget(target, action=SEL('swipe:'))
            gesture.direction = 2 if self.side == 'files' else 1
            gesture.delegate = target
            native.addGestureRecognizer(gesture)
            self.gestures.append((native, gesture, target))
        elif backend.startswith('toga_android.'):
            from android.view import View
            from java import dynamic_proxy
            owner = self
            class Touch(dynamic_proxy(View.OnTouchListener)):
                start = None
                def onTouch(self, view, event):
                    action = event.getActionMasked()
                    if action == 0:
                        self.start = (event.getRawX(), event.getRawY(), event.getEventTime())
                    elif action == 2 and self.start is not None:
                        x, y, _ = self.start
                        dx, dy = event.getRawX()-x, event.getRawY()-y
                        density = view.getContext().getResources().getDisplayMetrics().density
                        if abs(dy)>10*density and abs(dx)<2*abs(dy):
                            self.start = None
                    elif action == 1 and self.start is not None:
                        x, y, time = self.start
                        self.start = None
                        dx, dy = event.getRawX()-x, event.getRawY()-y
                        density = view.getContext().getResources().getDisplayMetrics().density
                        if abs(dx)>60*density and abs(dx)>2*abs(dy) and event.getEventTime()-time<800:
                            return owner.swipe(1 if dx>0 else -1)
                    elif action in (3, 5):
                        self.start = None
                    return False
            # PopupWindow observes the complete stream before child controls
            # consume it. Per-widget listeners miss scrolls and native children.
            popup = self.overlay.popup
            listener = Touch()
            popup.setTouchInterceptor(listener)
            self.gestures.append((popup, None, listener))

    def clear_gestures(self):
        for native, gesture, target in self.gestures:
            if gesture is not None:
                native.removeGestureRecognizer(gesture)
                gesture.delegate = None
                target.owner = None
            else:
                native.setTouchInterceptor(None)
        self.gestures.clear()

    def refresh_gestures(self):
        # Both native backends observe the overlay container, so replacing
        # rows does not require replacing the active recognizer/touch stream.
        if self.overlay is not None and not self.gestures:
            self.install_swipe(self.sidebar if self.side == 'files' else self.links)

    def show_detail(self):
        if self.side is not None:
            self.on_close()
        self.side = None
        self.on_change()
        self.clear_gestures()
        overlay, self.overlay = self.overlay, None
        if overlay is not None:
            overlay.panel.overlay = None
            overlay.close()


_swipe_class = None
