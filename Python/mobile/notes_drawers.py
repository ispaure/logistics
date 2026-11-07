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
        self.action_choice = None
        self.action_overlay = None
        self.side = None
        self.wide = False
        self.wide_files_open = True
        self.files_bottom_extension = 0
        self.gestures = []
        self.opening_gestures = []
        self.retiring = []
        self.open_links = self.show_links
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
        from .fold_layout import division
        from .notes_gestures import install_opening_swipes
        install_opening_swipes(self)
        fold = division(self.app, self.view)
        vertical_fold = fold is not None and fold.vertical
        self.wide = vertical_fold or width >= 840  # 320 for Files, at least 520 for the document.
        # The host passes the document width minus its 24-unit inset. Leave
        # at least 44 units opposite the drawer for outside dismissal.
        drawer_width = min(320, max(1, width - 32))
        # UIKit reports the crease and its interaction margins in this row's
        # coordinates, including any offset from a system bar or safe area.
        files_width, gap = (fold.x, fold.width) if vertical_fold else (drawer_width, 0)
        previous_gap = self.policy.gap

        def apply():
            self.policy.sidebar_width = files_width
            self.policy.gap = gap
            if self.side != 'files':
                self.sidebar.style.width = files_width
            self.links.style.width = drawer_width
            self.view.style.gap = gap
            self.layout_files()

        if ((vertical_fold or previous_gap)
                and (self.expanded or (self.wide and self.wide_files_open))
                and (files_width, gap) != (self.policy.sidebar_width, previous_gap)):
            from .notes_motion import resize_panes
            resize_panes(self.view, apply)
        else:
            apply()
        if self.overlay is not None:
            self.overlay.reposition()
        if self.action_overlay is not None:
            self.action_overlay.reposition()

    def layout_files(self):
        expanded = self.wide and self.wide_files_open
        if expanded == self.expanded:
            return
        if self.side == 'files':
            self.show_detail()
            self.finish_dismissals()
        self.expanded = expanded
        self.extend_files_bottom(self.files_bottom_extension)
        if expanded:
            self.sidebar.style.width = self.policy.sidebar_width
            self.sidebar.style.flex = 0
            self.view.insert(0, self.sidebar)
        else:
            self.view.remove(self.sidebar)
            self.sidebar.style.flex = 1

    def set_files_scrolls(self, *scrolls):
        self.sidebar._bottom_scrolls = scrolls

    def extend_files_bottom(self, extension):
        self.files_bottom_extension = extension
        margin = -extension if self.expanded else 0
        if self.sidebar.style.margin_bottom == margin:
            return False
        from .scroll_edges import sync_bottom
        return sync_bottom(self.sidebar, inset=-margin)

    def toggle(self, widget=None, **kwargs):
        if self.expanded:
            self.wide_files_open = False
            self.layout_files()
            self.on_change()
        elif self.side == 'files':
            self.show_detail()
        else:
            self.show_sidebar()

    def show_sidebar(self):
        self.show('files')

    def show_links(self):
        self.show('links')

    def show(self, side):
        privacy = getattr(self.app, 'screen_privacy', None)
        if privacy is not None and privacy.sensitive() and (
                privacy.inactive or privacy.interrupted or privacy.captured or privacy.resume_locked):
            return
        if side == 'files' and self.wide:
            self.show_detail()
            self.wide_files_open = True
            self.layout_files()
            self.on_change()
            return
        if self.side == side:
            return
        self.show_detail()
        self.finish_dismissals()
        self.side = side
        self.on_change()
        panel = self.sidebar if side == 'files' else self.links
        if side == 'files':
            del panel.style.width
        self.overlay = SpeechOverlay(panel, self.view, self.app, leading=side == 'files',
                                     full_height=True, label='Files' if side == 'files' else 'Links',
                                     dim=True, edge_panel=True, android_radius=8,
                                     width_limit=352 if side == 'files' else 320,
                                     opposite_gutter=28 if side == 'files' else None)
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

    async def choose_action(self, dialog, window):
        drawer = self.overlay
        backend = type(self.sidebar._impl).__module__
        if drawer is None or not backend.startswith(('toga_iOS.', 'toga_android.')):
            return await window.dialog(dialog)
        if self.action_choice is not None:
            return 'cancel'

        result = self.action_choice = self.app.loop.create_future()
        def finish(value):
            if not result.done():
                result.set_result(value)

        from .appearance import surface
        content = toga.Box(style=Pack(direction='column', margin=12))
        content.add(toga.Label(dialog.title, style=Pack(font_weight='bold', margin_bottom=4)),
                    toga.Label(dialog.message, style=Pack(margin_bottom=8)))
        for label, value, role in dialog.choices:
            def select(widget, value=value, **kwargs):
                finish(value)
            content.add(surface(toga.Button(label, on_press=select, style=Pack(height=44)),
                                radius=8, background='transparent',
                                foreground='destructive' if role == 2 else 'text', outlined=False))
        panel = toga.ScrollContainer(content=content, horizontal=False)
        panel.overlay_height = 76 + 44 * len(dialog.choices)
        panel.hide = lambda: finish('cancel')
        surface(panel, radius=12, background='surface', outlined=False)
        if drawer.outside_tap is not None:
            drawer.outside_tap.enabled = False
        choice = None
        try:
            choice = self.action_overlay = SpeechOverlay(panel, self.view, self.app, dim=True, centered=True,
                                   label='File actions', android_radius=12)
            return await result
        finally:
            if choice is not None:
                choice.close()
            if drawer.outside_tap is not None:
                drawer.outside_tap.enabled = True
            self.action_choice = self.action_overlay = None

    def cancel_action(self):
        if self.action_choice is not None and not self.action_choice.done():
            self.action_choice.set_result('cancel')

    def swipe(self, direction):
        if self.action_choice is not None:
            return False
        if (self.side == 'files' and direction < 0) or (self.side == 'links' and direction > 0):
            self.show_detail()
            return True
        return False

    def open_swipe(self, direction):
        from .notes_gestures import opening_swipes_allowed
        if self.side is not None or not opening_swipes_allowed(self):
            return False
        if direction > 0:
            if self.expanded:
                return False
            self.show_sidebar()
        else:
            self.open_links()
        return True

    def finish_dismissals(self):
        for overlay, handle in self.retiring:
            handle.cancel()
            overlay.close()
        self.retiring.clear()

    def dispose(self):
        from .notes_gestures import clear_opening_swipes
        clear_opening_swipes(self)
        self.show_detail()
        self.finish_dismissals()

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
        self.cancel_action()
        if self.side is not None:
            self.on_close()
        self.side = None
        self.on_change()
        self.clear_gestures()
        overlay, self.overlay = self.overlay, None
        if overlay is not None:
            overlay.panel.overlay = None
            from .notes_motion import slide_out
            duration = slide_out(overlay, -1 if overlay.leading else 1, self.app)
            if duration:
                def finish():
                    overlay.close()
                    self.retiring.remove((overlay, handle))
                handle = self.app.loop.call_later(duration, finish)
                self.retiring.append((overlay, handle))
            else:
                overlay.close()


_swipe_class = None
